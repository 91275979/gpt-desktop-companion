import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QPoint
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from main import DesktopPet
from settings import load_settings, save_settings


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_right_click_arrows_and_geometry_share_state(self):
        pet = DesktopPet()
        try:
            self.assertEqual(pet.panel.effect.opacity(),1)
            pet.show()
            self.app.processEvents()
            def right():
                # 动画帧会改变边缘轮廓，每次右键重新命中当前可见角色。
                point = next(QPoint(x,y) for y in range(80,pet.height(),4) for x in range(10,pet.width(),4)
                             if pet.contains_pet(QPoint(x,y)))
                pet.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, pet.mapToGlobal(point)))
                QTest.qWait(210)
            right()
            self.assertTrue(pet.panel_requested)
            self.assertEqual(pet.panel.page, 'usage')
            rect = pet.panel.geometry()
            right()
            self.assertEqual(pet.panel.page, 'weather')
            # 没有天气数据时不会伪造穿衣建议。
            self.assertFalse(pet.greeting_visible)
            pet.panel.next_button.click()
            QTest.qWait(210)
            self.assertEqual(pet.panel.page, 'markets')
            self.assertEqual(pet.panel.stack.currentIndex(), 2)
            right()
            self.assertEqual(pet.panel.page, 'usage')
            self.assertEqual(pet.panel.geometry(), rect)
            self.assertFalse(pet.greeting_visible)
            pet.hide_info_panel()
            pet.panel.set_page('markets')
            right()
            self.assertEqual(pet.panel.page, 'usage')
        finally:
            pet.close()
            pet.tracker.close()

    def test_page_and_provider_settings_survive_window_save(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.json'
            save_settings(path, {'weather_location':'Breda, Netherlands','watchlist':['AAPL'], 'custom':123})
            pet = DesktopPet(config_path=path)
            pet.panel.set_page('markets', animate=False)
            pet.close()
            pet.tracker.close()
            settings = load_settings(path)
            self.assertEqual(settings['dashboard_page'], 'markets')
            self.assertEqual(settings['weather_location'], 'Breda, Netherlands')
            self.assertEqual(settings['watchlist'], ['AAPL'])
