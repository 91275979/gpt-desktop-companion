"""复用 CodexQuotaWidget 的只读 app-server 协议，不接触登录凭据。"""

from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
from pathlib import Path
import shutil
import time

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


@dataclass(frozen=True)
class QuotaWindow:
    remaining_percent: float
    resets_at: int | None


@dataclass(frozen=True)
class QuotaSnapshot:
    five_hour: QuotaWindow | None = None
    weekly: QuotaWindow | None = None
    updated_at: float | None = None
    error: str | None = None


def parse_quota(result):
    # 不能假设 primary 总是五小时：以实际窗口分钟数区分。
    buckets = result.get("rateLimitsByLimitId")
    if isinstance(buckets, dict) and buckets:
        bucket = buckets.get("codex", {})
    else:
        bucket = result.get("rateLimits") or {}
    windows = {}
    for key in ("primary", "secondary"):
        value = bucket.get(key)
        if not isinstance(value, dict):
            continue
        duration, used = value.get("windowDurationMins"), value.get("usedPercent")
        if duration not in (300, 10080) or type(used) not in (int, float) or not math.isfinite(used):
            continue
        reset = value.get("resetsAt")
        if type(reset) is not int or not 0 <= reset <= 253402300799:
            reset = None
        windows[duration] = QuotaWindow(max(0, min(100, 100 - used)), reset)
    return QuotaSnapshot(windows.get(300), windows.get(10080), time.time())


def find_codex():
    configured = os.environ.get("CODEX_EXECUTABLE")
    if configured and Path(configured).is_file():
        return configured
    installed = shutil.which("codex.exe")
    if installed:
        return installed
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
    candidates = list(root.glob("*/codex.exe"))
    return str(max(candidates, key=lambda path: path.stat().st_mtime)) if candidates else None


def window_text(title, window):
    if window is None:
        return f"{title}：不可用"
    reset = datetime.fromtimestamp(window.resets_at).strftime("%m-%d %H:%M") if window.resets_at is not None else "未知"
    return f"{title}：剩余 {window.remaining_percent:g}%\n重置 {reset}"


class CodexQuotaClient(QObject):
    updated = Signal(object)
    REFRESH_MS = 60000

    def __init__(self, parent=None, executable=None):
        super().__init__(parent)
        self.executable = executable
        self.snapshot = QuotaSnapshot()
        self.process = QProcess(self)
        self.process.setStandardErrorFile(QProcess.nullDevice())
        self.process.started.connect(self._initialize)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.errorOccurred.connect(lambda error: self._fail("无法启动或连接 Codex，请确认已安装并登录"))
        self.process.finished.connect(self._finished)
        self.timer = QTimer(self)
        self.timer.setInterval(self.REFRESH_MS)
        self.timer.timeout.connect(self.refresh)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(lambda: self._fail("Codex 配额读取超时，稍后重试"))
        self.buffer = b""
        self.ready = False
        self.pending = None
        self.sequence = 0
        self.stopped = True

    def start(self):
        self.stopped = False
        self.timer.start()
        self.refresh()

    def refresh(self):
        if self.stopped or self.pending is not None:
            return
        if self.process.state() == QProcess.ProcessState.NotRunning:
            executable = self.executable or find_codex()
            if not executable:
                self._fail("未找到 Codex，请安装并登录，或配置 CODEX_EXECUTABLE")
                return
            self.ready = False
            self.buffer = b""
            self.process.start(executable, ["app-server", "--listen", "stdio://"])
            self.timeout.start(15000)
        elif self.ready:
            self._request("account/rateLimits/read")

    def _send(self, message):
        self.process.write((json.dumps(message) + "\n").encode("utf-8"))

    def _request(self, method, params=None):
        self.sequence += 1
        self.pending = (self.sequence, method)
        message = {"id": self.sequence, "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)
        self.timeout.start(15000)

    def _initialize(self):
        self._request("initialize", {"clientInfo": {"name": "gpt_desktop_pet", "title": "GPT Desktop Pet", "version": "1.0"}})

    def _read(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        if len(self.buffer) > 2_000_000:
            self._fail("Codex 返回数据过大")
            return
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                message = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            self._handle(message)

    def _handle(self, message):
        if not isinstance(message, dict) or self.pending is None or message.get("id") != self.pending[0]:
            return
        method = self.pending[1]
        self.pending = None
        self.timeout.stop()
        if "error" in message:
            self._fail("配额接口暂不可用，请确认 Codex 已登录 ChatGPT 账户")
            return
        if method == "initialize":
            self._send({"method": "initialized", "params": {}})
            self.ready = True
            self.refresh()
        else:
            try:
                self.snapshot = parse_quota(message["result"])
            except (KeyError, TypeError, AttributeError):
                self._fail("Codex 返回的配额格式无法识别")
                return
            self.updated.emit(self.snapshot)

    def _fail(self, reason):
        if self.stopped:
            return
        self.timeout.stop()
        self.pending = None
        self.ready = False
        self.snapshot = QuotaSnapshot(self.snapshot.five_hour, self.snapshot.weekly, self.snapshot.updated_at, reason)
        self.updated.emit(self.snapshot)
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _finished(self, *args):
        self.ready = False
        self.pending = None
        if not self.stopped and self.snapshot.error is None:
            self._fail("Codex 连接已断开，稍后重试")

    def stop(self):
        self.stopped = True
        self.timer.stop()
        self.timeout.stop()
        self.pending = None
        self.process.kill()
        self.process.waitForFinished(1000)
