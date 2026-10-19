"""GPT 桌宠主窗口及组件装配。"""

import sys
import argparse
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from character import CHARACTER_PATH, CharacterAnimation, CharacterAssets
from context_menu import create_context_menu
from panel import InfoPanel
from usage_tracker import UsageTracker
from usage_popup import UsagePopup
from quota_provider import CodexQuotaProvider
from settings import CONFIG_PATH, load_settings, save_settings
from instance import SingleInstance, PetLifecycle
from dashboard_services import DashboardServices
from interaction_manager import Interaction, InteractionManager, SLEEP_AFTER_IDLE, weather_dialogue


class DesktopPet(QWidget):
    closed = Signal()
    CHARACTER_HEIGHT = 180  # Qt 逻辑像素；Windows 显示缩放由 Qt 处理。
    HIT_ALPHA = 24  # 忽略近乎透明的阴影、边缘噪点。
    GREETING_TEXT = "主人好！"
    GREETING_DURATION_MS = 1500

    def __init__(self, character_path=CHARACTER_PATH, tracker=None, demo_usage=False, enable_quota=False, config_path=None, enable_services=False):
        super().__init__()
        self.config_path = config_path
        self._restoring = True
        self.tracker = tracker if tracker is not None else UsageTracker()
        self.demo_usage = demo_usage
        self.assets = CharacterAssets(character_path)
        self.character_image = self.assets.images["idle"]
        self.character_height = self.CHARACTER_HEIGHT
        self.always_on_top = True
        self.panel_requested = False
        self.setWindowTitle("GPT 桌宠 1.0")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        character_width = max(1, round(
            self.character_image.width() * self.CHARACTER_HEIGHT / self.character_image.height()
        ))
        # 各状态使用同一画布，预留气泡和呼吸边距。
        self.setFixedSize(max(160, character_width + 40), self.CHARACTER_HEIGHT + 100)
        self.character_rect = QRectF(
            (self.width() - character_width) / 2, 80, character_width, self.CHARACTER_HEIGHT
        )
        self.animation = CharacterAnimation(self.assets.images, self.character_rect, self,
                                            frames=self.assets.frames,
                                            frame_rates=self.assets.frame_rates)
        self.animation.changed.connect(self.update)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.greeting_visible = False
        self.interactions = InteractionManager()
        self.mood_timer = QTimer(self)
        self.mood_timer.setInterval(100)
        self.mood_timer.timeout.connect(self.update_mood)
        self.mood_timer.start()
        self.greeting_text = self.GREETING_TEXT
        self.greeting_timer = QTimer(self)
        self.greeting_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.greeting_timer.setSingleShot(True)
        self.greeting_timer.timeout.connect(self.hide_greeting)
        self._press_position = None
        self._window_position = QPoint()
        self._dragged = False
        self.panel = InfoPanel(self)
        self.panel.page_changed.connect(lambda _:self.save_preferences())
        self.quota_client = CodexQuotaProvider(self)
        self.quota_client.updated.connect(self.update_quota)
        if enable_quota:
            QTimer.singleShot(0, self.quota_client.start)
        self.usage_popup = UsagePopup(self, demo=demo_usage)
        self.usage_timer = QTimer(self)
        self.usage_timer.setInterval(2000)
        self.usage_timer.timeout.connect(self.settle_usage)
        self.usage_timer.start()
        self.panel.update_usage(self.tracker.snapshot(), self.demo_usage)
        self.panel.update_quota(self.tracker.quota_details(), self.tracker.quota_error)
        self.place_at_bottom_right()
        if config_path is not None:
            self.restore_preferences(load_settings(config_path))
        self._restoring = False
        self.dashboard_services = DashboardServices(self.panel, load_settings(config_path), self)
        self.dashboard_services.weather_updated.connect(self.interactions.receive_weather)
        if enable_services:
            QTimer.singleShot(0, self.dashboard_services.start)

    def restore_preferences(self, preferences):
        self.set_character_size(preferences["character_size"])
        self.set_always_on_top(preferences["always_on_top"])
        self.panel_requested = preferences["panel_visible"]
        self.panel.set_page(preferences['dashboard_page'], animate=False)
        self.place_at_bottom_right()
        pos = preferences["position"]
        if pos:
            candidate = self.geometry()
            candidate.moveTopLeft(QPoint(pos["x"], pos["y"]))
            if any(screen.availableGeometry().contains(candidate) for screen in QApplication.screens()):
                self.move(candidate.topLeft())

    def save_preferences(self):
        if self.config_path is None or self._restoring:
            return
        preferences = load_settings(self.config_path)
        preferences.update(dict(character_size=self.character_height,
                dashboard_page=self.panel.page,
                always_on_top=self.always_on_top, panel_visible=self.panel_requested,
                position=dict(x=self.x(), y=self.y())))
        if not save_settings(self.config_path, preferences):
            QMessageBox.warning(self, "设置未保存", "无法写入 config.json，请检查项目目录的写入权限。")

    def settle_usage(self):
        # 仅消费已收到的 usage；这里绝不发网络请求。
        if not self.isVisible():
            return
        delta = self.tracker.consume_delta()
        if delta.total_tokens > 0:
            self.usage_popup.push(delta)
        self.panel.update_usage(self.tracker.snapshot(), self.demo_usage)
        changes = self.tracker.consume_quota_changes()
        if changes:
            self.interactions.quota_changed()
            self.usage_popup.push_quotas(changes)
        self.panel.update_quota(self.tracker.quota_details(), self.tracker.quota_error)
        self.panel.follow(self)

    def update_quota(self, snapshot):
        self.tracker.record_quota(snapshot)
        self.panel.update_quota(self.tracker.quota_details(), self.tracker.quota_error)
        self.panel.follow(self)

    def show_info_panel(self):
        self.panel_requested = True
        self.panel.update_usage(self.tracker.snapshot(), self.demo_usage)
        self.panel.follow(self)
        self.panel.show()
        self.save_preferences()

    def hide_info_panel(self):
        self.panel_requested = False
        self.panel.hide()
        self.save_preferences()

    def moveEvent(self, event):
        if hasattr(self, "panel"):
            self.panel.follow(self)
        if hasattr(self, "usage_popup"):
            self.usage_popup.follow()
        super().moveEvent(event)

    def set_character_size(self, height):
        # 保持角色脚底中心不动，状态缓存和动画相位不变。
        anchor = self.pos() + QPoint(self.width() // 2, self.height() - 20)
        width = max(1, round(self.character_image.width() * height / self.character_image.height()))
        self.character_height = height
        self.setFixedSize(max(160, width + 40), height + 100)
        self.character_rect = QRectF((self.width() - width) / 2, 80, width, height)
        self.animation.base_rect = QRectF(self.character_rect)
        self.move(anchor - QPoint(self.width() // 2, self.height() - 20))
        self.panel.follow(self)
        self.usage_popup.follow()
        self.update()
        self.save_preferences()

    def set_always_on_top(self, enabled):
        self.always_on_top = enabled
        position = self.pos()
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.panel.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.usage_popup.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.move(position)
        if visible:
            self.show()
        self.save_preferences()

    def closeEvent(self, event):
        self.dashboard_services.stop()
        self.save_preferences()
        self.panel_requested = False
        self.panel.close()
        self.greeting_timer.stop()
        self.mood_timer.stop()
        self.animation.stop()
        self.usage_timer.stop()
        self.usage_popup.dismiss()
        self.quota_client.stop()
        super().closeEvent(event)
        self.closed.emit()

    def place_at_bottom_right(self):
        # availableGeometry 排除任务栏，并保留屏幕的实际坐标原点。
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(
                max(area.left(), area.right() + 1 - self.width() - 24),
                max(area.top(), area.bottom() + 1 - self.height() - 24),
            )

    def contains_pet(self, position):
        return self.animation.contains(position, self.HIT_ALPHA)

    def showEvent(self, event):
        self.animation.start()
        if self.panel_requested:
            self.panel.follow(self)
            self.panel.show()
        if self.usage_popup.phase != "hidden":
            self.usage_popup.follow()
            self.usage_popup.show()
        super().showEvent(event)

    def hideEvent(self, event):
        self.animation.stop()
        self.panel.hide()
        self.usage_popup.hide()
        super().hideEvent(event)

    def set_character_state(self, state):
        self.animation.set_state(state)

    def hide_greeting(self):
        self.greeting_visible = False
        self.update()

    def perform_interaction(self):
        services = self.dashboard_services
        result = self.interactions.click(services.weather.snapshot, services.markets.quotes.values())
        self.show_dialogue(result, persistent=self.interactions.fast_click_mode)

    def show_dialogue(self, result, persistent=False):
        self.animation.interact(result.expression, result.duration_ms, persistent=persistent)
        self.greeting_text = result.text
        self.greeting_visible = True
        self.greeting_timer.start(result.duration_ms)
        self.update()

    def show_weather_advice(self):
        snapshot = self.dashboard_services.weather.snapshot
        if snapshot is None or self.interactions.fast_click_mode:
            return
        # 右键查看 Weather 属于一次明确互动：唤醒但不计入左键连击。
        self.interactions.last_interaction_time = self.interactions.clock()
        self.show_dialogue(Interaction(weather_dialogue(snapshot), 'thinking', 4500, 'weather'))

    def update_mood(self):
        was_active = self.interactions.fast_click_mode
        self.interactions.advance()
        if (not self.interactions.fast_click_mode
                and self.interactions.idle_seconds() >= SLEEP_AFTER_IDLE):
            # 睡眠是持久状态；下一次左键互动会通过 interact() 唤醒。
            if self.animation.state.value != "sleep":
                self.animation.interact("sleep", 0, persistent=True)
            return
        if was_active and self.animation.state.value != self.interactions.expression:
            self.animation.set_state(self.interactions.expression)
        reminder = self.interactions.automatic_weather_dialogue(blocked=(
            not self.isVisible() or self.greeting_visible or self.animation.held
            or self.animation.state.value == 'sleep'))
        if reminder is not None:
            self.show_dialogue(reminder)

    def enterEvent(self, event):
        self.animation.set_hovered(self.contains_pet(event.position()))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.animation.set_hovered(False)
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.greeting_visible:
            bubble = QRectF(4, 4, self.width() - 8, 64)
            painter.setPen(QPen(QColor("#555555"), 1))
            painter.setBrush(QColor(32, 33, 35, 240))
            painter.drawRoundedRect(bubble, 14, 14)
            painter.setPen(QColor("#FFFFFF"))
            text_rect = bubble.adjusted(8, 3, -8, -3)
            flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
            font = QFont("Microsoft YaHei", 12)
            while font.pointSize() > 9 and QFontMetricsF(font).boundingRect(text_rect, flags, self.greeting_text).height() > text_rect.height():
                font.setPointSize(font.pointSize()-1)
            painter.setFont(font)
            painter.drawText(text_rect, flags, self.greeting_text)

        self.animation.paint(painter)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.contains_pet(event.position()):
            self._press_position = event.globalPosition().toPoint()
            self._window_position = self.pos()
            self._dragged = False
            self.animation.hold()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self.animation.set_hovered(self.contains_pet(event.position()))
        if self._press_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._press_position
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._dragged = True
            if self._dragged:
                self.move(self._window_position + delta)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._press_position is not None:
            delta = event.globalPosition().toPoint() - self._press_position
            clicked = (
                not self._dragged
                and delta.manhattanLength() < QApplication.startDragDistance()
                and self.contains_pet(event.position())
            )
            self.animation.release(False)
            self.animation.set_hovered(self.contains_pet(event.position()))
            if clicked:
                self.perform_interaction()
            elif self._dragged:
                self.save_preferences()
            self._press_position = None
            self._dragged = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.contains_pet(event.position()):
            # Qt 用双击事件代替第二次按下；仍按普通左键处理，释放时立即互动。
            self.mousePressEvent(event)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if not self.contains_pet(event.pos()):
            event.ignore()
            return
        if not self.panel_requested:
            self.panel.set_page('usage', animate=False)
            self.show_info_panel()
        else:
            self.panel.cycle()
        if self.panel.page == 'weather':
            self.show_weather_advice()
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-usage", action="store_true", help="使用内存模拟数据演示浮动提示，不调用 API")
    parser.add_argument("--demo-seconds", type=float, help="演示模式运行指定秒数后退出")
    parser.add_argument("--no-quota", action="store_true", help="不连接 Codex 配额接口")
    args = parser.parse_args()
    guard = SingleInstance('pet')
    if not guard.acquired:
        return 0
    app = QApplication(sys.argv)
    tracker = UsageTracker(":memory:" if args.demo_usage else Path(__file__).resolve().parent / "data" / "usage.sqlite3")
    try:
        pet = DesktopPet(tracker=tracker, demo_usage=args.demo_usage,
                         enable_quota=not args.no_quota and not args.demo_usage,
                         config_path=None if args.demo_usage else CONFIG_PATH,
                         enable_services=not args.demo_usage)
    except ValueError as error:
        QMessageBox.warning(None, "角色素材需要准备", str(error))
        tracker.close()
        return 1
    pet.show()
    lifecycle = PetLifecycle(pet)
    pet.closed.connect(app.quit)
    if args.demo_usage:
        def sample(incoming, outgoing, key, cost):
            tracker.record_usage({"input_tokens": incoming, "output_tokens": outgoing,
                                  "total_tokens": incoming + outgoing}, response_id=key, estimated_cost=cost)
        QTimer.singleShot(300, lambda: sample(820, 464, "demo-1", "0.00328"))
        QTimer.singleShot(2600, lambda: sample(120, 80, "demo-2", "0.00056"))
        QTimer.singleShot(9000, lambda: sample(350, 150, "demo-3", "0.0013"))
        if args.demo_seconds is not None:
            QTimer.singleShot(max(1, int(args.demo_seconds * 1000)), pet.close)
    try:
        return app.exec()
    finally:
        lifecycle.close()
        tracker.close()
        guard.close()


if __name__ == "__main__":
    sys.exit(main())
