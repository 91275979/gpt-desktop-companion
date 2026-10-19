"""额度来源适配层：只读取/归一化数据，不计算消耗、不操作 UI。"""

from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal
from codex_quota import CodexQuotaClient


@dataclass(frozen=True)
class QuotaSnapshot:
    total: float | None
    used: float
    remaining: float | None
    percentage: float | None  # 已用百分比，0～100；不是剩余百分比。
    reset_time: int | None
    fetched_at: float
    unit: str = "percent"  # percent / tokens / currency；禁止根据百分比猜 token。
    period: str = "5h"
    source: str = "codex"

    @property
    def key(self):
        return (self.source, self.period, self.unit)


@dataclass(frozen=True)
class QuotaUpdate:
    snapshots: tuple[QuotaSnapshot, ...] = ()
    error: str | None = None


def normalize_codex(snapshot):
    if snapshot.error:
        return QuotaUpdate(error="额度数据暂不可用")
    values = []
    for period, window in (("5h", snapshot.five_hour), ("week", snapshot.weekly)):
        if window is not None:
            used = 100 - window.remaining_percent
            values.append(QuotaSnapshot(100, used, window.remaining_percent, used,
                                        window.resets_at, snapshot.updated_at,
                                        period=period))
    if not values:
        return QuotaUpdate(error="额度数据暂不可用")
    return QuotaUpdate(tuple(values))


class CodexQuotaProvider(QObject):
    """可替换为其他项目的 provider，向外只发送 QuotaUpdate。"""
    updated = Signal(object)

    def __init__(self, parent=None, client=None):
        super().__init__(parent)
        self.client = client if client is not None else CodexQuotaClient(self)
        self.client.timer.setInterval(2000)
        self.client.updated.connect(lambda snapshot: self.updated.emit(normalize_codex(snapshot)))

    @property
    def timer(self):
        return self.client.timer

    def start(self):
        self.client.start()

    def stop(self):
        self.client.stop()

    def refresh(self):
        self.client.refresh()
