"""与 Qt/API 查询无关的 usage 账本；只接受服务端返回的 token 数。"""

from collections.abc import Mapping
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json
import sqlite3
import threading
import time
import uuid
import math


@dataclass(frozen=True)
class QuotaChange:
    snapshot: object
    consumed: float

    def merged(self, other):
        if (self.snapshot.key != other.snapshot.key or self.snapshot.reset_time != other.snapshot.reset_time
                or self.snapshot.total != other.snapshot.total):
            return other
        return QuotaChange(other.snapshot, self.consumed + other.consumed)


@dataclass(frozen=True)
class UsageDelta:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    estimated_cost: Decimal | None = None
    last_update: float | None = None

    def merged(self, other):
        def optional(a, b):
            return None if a is None or b is None else a + b
        if not self.total_tokens:
            return other
        if not other.total_tokens:
            return self
        return UsageDelta(self.input_tokens + other.input_tokens,
                          self.output_tokens + other.output_tokens,
                          self.total_tokens + other.total_tokens,
                          optional(self.cached_tokens, other.cached_tokens),
                          optional(self.reasoning_tokens, other.reasoning_tokens),
                          optional(self.estimated_cost, other.estimated_cost),
                          max(self.last_update or 0, other.last_update or 0))


@dataclass(frozen=True)
class UsageSnapshot(UsageDelta):
    session_total: int = 0
    today_total: int = 0
    recent_rate: float = 0.0  # 最近五分钟 token 数折算为 tokens/hour


def as_dict(value):
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    raise ValueError("usage 必须是字典或 SDK usage 对象")


def parse_usage(value, estimated_cost=None, timestamp=None):
    usage = as_dict(value)
    def count(name, source=usage, optional=False):
        value = source.get(name)
        if value is None and optional:
            return None
        if type(value) is not int or value < 0:
            raise ValueError(f"无效 usage 字段：{name}")
        return value
    incoming, outgoing, total = (count(name) for name in ("input_tokens", "output_tokens", "total_tokens"))
    if incoming + outgoing != total:
        raise ValueError("total_tokens 与 Input/Output 不一致")
    cached = count("cached_tokens", usage.get("input_tokens_details") or {}, True)
    reasoning = count("reasoning_tokens", usage.get("output_tokens_details") or {}, True)
    if (cached or 0) > incoming or (reasoning or 0) > outgoing:
        raise ValueError("usage 细分 token 超过对应总量")
    cost = Decimal(str(estimated_cost)) if estimated_cost is not None else None
    if cost is not None and (not cost.is_finite() or cost < 0):
        raise ValueError("费用必须是非负有限数值")
    return UsageDelta(incoming, outgoing, total, cached, reasoning, cost, timestamp)


class UsageTracker:
    """线程安全。consume_delta 是 UI 的单一消费者；snapshot 不消耗增量。"""

    def __init__(self, db_path=":memory:", clock=time.time):
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS usage_events (response_id TEXT UNIQUE, session TEXT, timestamp REAL, day TEXT, usage TEXT, cost TEXT)")
        self._db.execute("CREATE INDEX IF NOT EXISTS usage_time ON usage_events(timestamp)")
        self._db.commit()
        self._lock = threading.RLock()
        self._clock = clock
        self._session = uuid.uuid4().hex
        self._pending = UsageDelta()
        self._quota = {}
        self._quota_available = set()
        self._quota_history = {}
        self._quota_pending = {}
        self.quota_error = None

    def record_quota(self, update):
        """首次成功只建基线，周期改变/下降只更新基线，不产生负消耗。"""
        with self._lock:
            if update.error or not update.snapshots:
                self.quota_error = "额度数据暂不可用"
                return
            for snapshot in update.snapshots:
                values = (snapshot.used, snapshot.fetched_at, snapshot.total,
                          snapshot.remaining, snapshot.percentage)
                if (any(value is not None and (type(value) not in (int, float)
                        or not math.isfinite(value) or value < 0) for value in values)
                        or snapshot.used is None or snapshot.fetched_at is None
                        or snapshot.percentage is not None and snapshot.percentage > 100):
                    self.quota_error = "额度数据暂不可用"
                    return
            self.quota_error = None
            self._quota_available = {snapshot.key for snapshot in update.snapshots}
            for snapshot in update.snapshots:
                key = snapshot.key
                previous = self._quota.get(key)
                if previous and snapshot.fetched_at <= previous.fetched_at:
                    continue
                self._quota[key] = snapshot
                history = self._quota_history.setdefault(key, deque())
                if previous is None:
                    continue
                if (previous.reset_time != snapshot.reset_time or snapshot.used < previous.used
                        or previous.total != snapshot.total):
                    history.clear()
                    self._quota_pending.pop(key, None)
                    continue
                increase = snapshot.used - previous.used
                if increase > 1e-8:
                    history.append((snapshot.fetched_at, increase))
                    change = QuotaChange(snapshot, increase)
                    if key in self._quota_pending:
                        change = self._quota_pending[key].merged(change)
                    self._quota_pending[key] = change
                # 每次快照清除过期数据，内存不随运行时间无限增长。
                while history and history[0][0] <= snapshot.fetched_at - 60:
                    history.popleft()

    def consume_quota_changes(self):
        with self._lock:
            changes = list(self._quota_pending.values())
            self._quota_pending.clear()
            return changes

    def quota_details(self):
        with self._lock:
            now = self._clock()
            rows = []
            for key, snapshot in self._quota.items():
                recent = sum(amount for stamp, amount in self._quota_history.get(key, ()) if now - 60 < stamp <= now)
                stale = self.quota_error is not None or key not in self._quota_available
                rows.append((snapshot, recent, stale))
            return rows

    def record_response(self, response, estimated_cost=None):
        if isinstance(response, Mapping):
            usage, response_id = response.get("usage"), response.get("id")
        else:
            usage, response_id = getattr(response, "usage", None), getattr(response, "id", None)
        if usage is None:
            return False  # 不猜测缺失的 usage，也不把它记为零费用。
        return self.record_usage(usage, response_id=response_id, estimated_cost=estimated_cost)

    def record_usage(self, usage, *, response_id=None, estimated_cost=None):
        now = self._clock()
        raw = as_dict(usage)
        event = parse_usage(raw, estimated_cost, now)
        with self._lock:
            cursor = self._db.execute("INSERT OR IGNORE INTO usage_events VALUES (?, ?, ?, ?, ?, ?)",
                (response_id, self._session, now, datetime.fromtimestamp(now).date().isoformat(),
                 json.dumps(raw), str(event.estimated_cost) if event.estimated_cost is not None else None))
            self._db.commit()
            if not cursor.rowcount:
                return False  # 同一 response ID 只记一次。
            self._pending = self._pending.merged(event)
            return True

    def consume_delta(self):
        with self._lock:
            delta, self._pending = self._pending, UsageDelta()
            return delta

    def snapshot(self):
        now = self._clock()
        day = datetime.fromtimestamp(now).date().isoformat()
        session = UsageDelta()
        today, recent = 0, 0
        with self._lock:
            rows = self._db.execute("SELECT session, timestamp, day, usage, cost FROM usage_events WHERE session=? OR day=? OR timestamp>=?",
                                    (self._session, day, now - 300)).fetchall()
        for session_id, stamp, event_day, raw, cost in rows:
            event = parse_usage(json.loads(raw), cost, stamp)
            if session_id == self._session:
                session = session.merged(event)
            if event_day == day:
                today += event.total_tokens
            if now - 300 <= stamp <= now:
                recent += event.total_tokens
        return UsageSnapshot(**vars(session), session_total=session.total_tokens,
                             today_total=today, recent_rate=recent * 12)

    def close(self):
        with self._lock:
            self._db.close()
