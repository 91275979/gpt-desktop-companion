import time
import unittest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication
from main import DesktopPet
from weather_provider import WeatherSnapshot


class CompactDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_weather_page_is_summary_and_right_click_speaks_advice(self):
        pet = DesktopPet()
        try:
            snapshot = WeatherSnapshot('Weihai, China', 12, 8, 15, 6, 70, 0, 30, 61,
                '2026-10-18T12:00', 'Asia/Shanghai', time.time())
            pet.dashboard_services.weather.snapshot = snapshot
            page = pet.panel.page_widgets['weather']
            page.update_weather(snapshot)
            self.assertEqual(page.fields['location'].text(), 'Weihai, China')
            self.assertEqual(page.fields['current'].text(), '当前 12°C')
            self.assertEqual(page.fields['details'].text(), '天气：小雨')
            self.assertFalse(page.fields['advice'].isVisible())
            pet.show()
            point = pet.character_rect.center().toPoint()
            event = lambda: QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, pet.mapToGlobal(point))
            pet.contextMenuEvent(event())
            pet.contextMenuEvent(event())
            self.assertEqual(pet.panel.page, 'weather')
            self.assertTrue(pet.greeting_visible)
            self.assertIn('外套', pet.greeting_text)
            self.assertIn('带伞', pet.greeting_text)
            self.assertEqual(pet.animation.state.value, 'thinking')
            self.assertIsNone(pet.interactions.last_click_time)
        finally:
            pet.close()
            pet.tracker.close()

    def test_panel_prefers_above_character(self):
        pet = DesktopPet()
        try:
            pet.move(700, 500)
            pet.panel.follow(pet)
            character_top = pet.y() + pet.character_rect.top()
            character_center_x = pet.x() + pet.character_rect.center().x()
            self.assertLess(pet.panel.geometry().bottom(), character_top)
            self.assertAlmostEqual(pet.panel.geometry().center().x(), character_center_x, delta=1)
        finally:
            pet.close()
            pet.tracker.close()


if __name__ == '__main__':
    unittest.main()
