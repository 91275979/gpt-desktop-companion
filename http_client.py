"""公开 JSON API 的后台请求；默认验证 TLS，限时限体积，退出时丢弃结果。"""
import json
import threading
import time
import urllib.request
from PySide6.QtCore import QObject, Signal, Qt


class JsonClient(QObject):
    completed = Signal(int, object, str)

    def __init__(self, parent=None, logger=None):
        super().__init__(parent)
        self.pending = {}
        self.closed = False
        self.last_error = ''
        self.sequence = 0
        self.logger = logger
        self.completed.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    def get(self, url, callback):
        if self.closed:
            return
        self.sequence += 1
        token = self.sequence
        self.pending[token] = callback
        def work():
            data, error = None, ''
            started, status = time.monotonic(), None
            try:
                if self.logger:
                    self.logger.info('GET %s timeout=20s', url)
                request = urllib.request.Request(url, headers={'User-Agent':'GPTCompanion/1.0 (personal dashboard)'})
                with urllib.request.urlopen(request, timeout=20) as response:
                    status = response.status
                    raw = response.read(2_000_001)
                    if len(raw) > 2_000_000:
                        raise ValueError('Response too large')
                    data = json.loads(raw)
                    if self.logger:
                        self.logger.info('HTTP %s elapsed=%.2fs JSON=valid keys=%s', status,
                            time.monotonic()-started, list(data) if isinstance(data, dict) else type(data).__name__)
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'
                if self.logger:
                    self.logger.exception('GET failed HTTP=%s elapsed=%.2fs timeout=%s url=%s',
                        getattr(exc, 'code', status), time.monotonic()-started,
                        isinstance(getattr(exc, 'reason', exc), TimeoutError), url)
            if not self.closed:
                try:
                    self.completed.emit(token, data, error)
                except RuntimeError:
                    pass  # Qt 已经退出，不再向销毁的界面交付。
        threading.Thread(target=work, name='dashboard-http', daemon=True).start()

    def _deliver(self, token, data, error):
        callback = self.pending.pop(token, None)
        if not self.closed and callback:
            self.last_error = error
            callback(data, error or None)

    def close(self):
        self.closed = True
        self.pending.clear()


def number(value):
    import math
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('缺少有效数值')
    return float(value)
