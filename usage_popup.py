"""只负责增量展示，不读取 API 或账本。"""

from PySide6.QtCore import QElapsedTimer, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from usage_tracker import UsageDelta


def cost_text(cost):
    if cost is None:
        return "费用未配置"
    if 0 < cost < 0.000001:
        return "估算 < $0.000001"
    return f"估算 ${cost:.6f}"


class UsagePopup(QWidget):
    def __init__(self, owner, demo=False):
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.owner = owner
        self.demo = demo
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(256, 124)
        self.delta = UsageDelta()
        self.quota_change = None
        self.quota_changes = {}
        self.phase = "hidden"
        self.phase_ms = 0.0
        self.opacity = 0.0
        self.offset = 6.0
        self.recover_from = (1.0, 0.0)
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)

    def push(self, delta):
        if delta.total_tokens <= 0:
            return
        self.delta = (self.delta.merged(delta) if self.phase != "hidden"
                      and self.quota_change is None else delta)
        self.quota_change = None
        self.quota_changes.clear()
        self.setFixedSize(256, 124)
        self._present()

    def push_quota(self, change):
        self.push_quotas([change])

    def push_quotas(self, changes):
        changes = [change for change in changes if change.consumed > 0]
        if not changes:
            return
        if self.phase == "hidden":
            self.quota_changes.clear()
        for change in changes:
            key = change.snapshot.key
            previous = self.quota_changes.get(key)
            self.quota_changes[key] = previous.merged(change) if previous else change
        self.quota_change = next(iter(self.quota_changes.values()))
        # 主气泡下方预留思考圆点，让提示像从角色头顶冒出的想法。
        self.setFixedSize(236, 126 + 66 * (len(self.quota_changes) - 1))
        self._present()

    def _present(self):
        if self.phase == "hidden":
            self.phase, self.phase_ms = "in", 0.0
            self.opacity, self.offset = 0.0, 5.0 if self.quota_changes else 6.0
        else:
            if self.phase == "out":
                self.recover_from = (self.opacity, self.offset)
                self.phase, self.phase_ms = "recover", 0.0
            elif self.phase == "hold":
                self.phase_ms = 0.0
        self.follow()
        self.show()
        if not self.timer.isActive():
            self.clock.start()
            self.timer.start()
        self.update()

    def _tick(self):
        self.advance(self.clock.restart())

    def advance(self, milliseconds):
        quota = bool(self.quota_changes)
        durations = ({"in": 180, "recover": 180, "hold": 1620, "out": 700} if quota
                     else {"in": 200, "recover": 200, "hold": 1600, "out": 600})
        while self.phase != "hidden" and milliseconds > 0:
            duration = durations[self.phase]
            step = min(milliseconds, duration - self.phase_ms)
            self.phase_ms += step
            milliseconds -= step
            t = self.phase_ms / duration
            ease = t * t * (3 - 2 * t)
            if self.phase == "in":
                self.opacity, self.offset = ease, (5 if quota else 6) * (1 - ease)
            elif self.phase == "recover":
                alpha, offset = self.recover_from
                self.opacity = alpha + (1 - alpha) * ease
                self.offset = offset * (1 - ease)
            elif self.phase == "hold":
                self.opacity, self.offset = 1.0, 0.0
            else:
                self.opacity, self.offset = 1 - ease, -(5 if quota else 4) * ease
            if self.phase_ms >= duration:
                self.phase = {"in": "hold", "recover": "hold", "hold": "out", "out": "hidden"}[self.phase]
                self.phase_ms = 0.0
        if self.phase == "hidden":
            self.dismiss()
        else:
            self.follow()
            self.update()

    def dismiss(self):
        self.timer.stop()
        self.phase = "hidden"
        self.delta = UsageDelta()
        self.quota_change = None
        self.quota_changes.clear()
        self.hide()

    def display_lines(self):
        if self.quota_change is not None:
            snapshot = self.quota_change.snapshot
            amount = self.quota_change.consumed
            period = {"5h": "5 小时", "week": "每周"}.get(snapshot.period, snapshot.period)
            if snapshot.unit == "tokens":
                title = f"- {amount:,.0f} tokens"
                remaining = f"剩余 {snapshot.remaining:,.0f} tokens" if snapshot.remaining is not None else "剩余额度未知"
            elif snapshot.unit == "percent":
                title = f"本轮消耗 {amount:.2f}%"
                remaining = f"剩余 {snapshot.remaining:.2f}%" if snapshot.remaining is not None else "剩余额度未知"
            else:
                title = f"本轮消耗 {amount:.2f}"
                remaining = f"剩余额度 {snapshot.remaining:.2f}" if snapshot.remaining is not None else "剩余额度未知"
            note = "变化单位：百分点" if snapshot.unit == "percent" else "真实额度变化"
            return title, f"{period} · {remaining}", note
        suffix = " · 模拟" if self.demo else ""
        return (f"{self.delta.total_tokens:,} tokens",
                f"Input {self.delta.input_tokens:,} · Output {self.delta.output_tokens:,}",
                cost_text(self.delta.estimated_cost) + suffix)

    def follow(self):
        owner = self.owner
        screen = QApplication.screenAt(owner.geometry().center()) or owner.screen()
        area = screen.availableGeometry()
        x = owner.x() + owner.width() // 2 - self.width() // 2
        # 对齐角色头顶；问候出现时为它让出空间。
        rect = getattr(owner, "character_rect", None)
        head = owner.y() + (rect.top() if rect is not None else 0)
        if getattr(owner, "greeting_visible", False):
            head = owner.y()
        y = round(head - self.height() - 10 + self.offset)
        self.move(max(area.left(), min(x, area.right() + 1 - self.width())),
                  max(area.top(), min(y, area.bottom() + 1 - self.height())))

    def paintEvent(self, event):
        if self.quota_changes:
            self.paint_quota()
            return
        title, detail, footer = self.display_lines()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self.opacity)
        bubble = QRectF(4, 3, 246, 100)
        self._paint_thought_shell(painter, bubble)
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.DemiBold))
        painter.drawText(QRectF(18, 12, 220, 29), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         title)
        painter.setFont(QFont("Microsoft YaHei", 9))
        painter.setPen(QColor("#C4C4C4"))
        painter.drawText(QRectF(18, 44, 220, 22), Qt.AlignmentFlag.AlignLeft,
                         detail)
        painter.setPen(QColor("#AAAAAA"))
        painter.drawText(QRectF(18, 72, 220, 20), Qt.AlignmentFlag.AlignLeft,
                         footer)

    def paint_quota(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self.opacity)
        rect = QRectF(self.rect()).adjusted(4, 3, -5, -22)
        self._paint_thought_shell(painter, rect)
        def line(text, y, size, color, bold=False, right=False):
            font = QFont("Microsoft YaHei")
            font.setPixelSize(size)
            font.setBold(bold)
            painter.setFont(font)
            painter.setPen(QColor(color))
            painter.drawText(QRectF(18, y, self.width()-36, 26),
                             (Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft)
                             | Qt.AlignmentFlag.AlignVCenter, text)
        line("✦  Codex Usage" + (" · 演示" if self.demo else ""), 10, 11, "#b8b8bc")
        changes = sorted(self.quota_changes.values(), key=lambda c: c.snapshot.period != "5h")
        for index, change in enumerate(changes):
            snapshot = change.snapshot
            label = {"5h": "5小时额度", "week": "每周额度"}.get(snapshot.period, snapshot.period)
            unit = "%" if snapshot.unit == "percent" else " tokens" if snapshot.unit == "tokens" else ""
            y = 39 + index * 66
            line(label, y, 12, "#b8b8bc")
            line(f"-{change.consumed:g}{unit}", y, 12, "#b8b8bc", right=True)
            remaining = f"{snapshot.remaining:g}{unit}" if snapshot.remaining is not None else "未知"
            line(f"剩余 {remaining}", y+24, 20, "#f3f3f4", True)

    def _paint_thought_shell(self, painter, rect):
        """绘制统一的想法气泡外壳；圆点朝向下方角色头顶。"""
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 34))
        painter.drawRoundedRect(rect.translated(1, 3), 17, 17)
        painter.setPen(QPen(QColor(195, 195, 200, 72), 0.7))
        painter.setBrush(QColor(30, 31, 33, 232))
        painter.drawRoundedRect(rect, 17, 17)

        # 两个由大到小的圆点形成“思考”尾巴，最小圆点最靠近角色。
        center_x = rect.center().x() + min(28, rect.width() * .12)
        for radius, dy, alpha in ((5.0, 7.0, 224), (2.8, 15.0, 188)):
            center_y = rect.bottom() + dy
            painter.setPen(QPen(QColor(195, 195, 200, min(alpha, 82)), 0.6))
            painter.setBrush(QColor(30, 31, 33, alpha))
            painter.drawEllipse(QRectF(center_x-radius, center_y-radius,
                                       radius*2, radius*2))
