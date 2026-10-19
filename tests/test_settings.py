import json
from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication
from main import DesktopPet
from settings import load_settings, save_settings


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_missing_corrupt_and_invalid_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.json'
            self.assertEqual(load_settings(path)['character_size'], 180)
            for content in ('{', 'null', '[]', '{"character_size": 999, "always_on_top": "false", "position": {"x": true}}'):
                path.write_text(content)
                settings = load_settings(path)
                self.assertEqual(settings['character_size'], 180)
                self.assertTrue(settings['always_on_top'])
                self.assertIsNone(settings['position'])

    def test_reopen_restores_size_position_panel_and_topmost(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.json'
            first = DesktopPet(config_path=path)
            first.show()
            self.app.processEvents()
            self.assertEqual(first.character_height, 180)
            first.set_character_size(150)
            area = first.screen().availableGeometry()
            position = area.topLeft() + QPoint(70, 120)
            first.move(position)
            first.set_always_on_top(False)
            first.show_info_panel()
            first.close()
            first.tracker.close()
            saved = json.loads(path.read_text())
            self.assertTrue(saved['panel_visible'])
            second = DesktopPet(config_path=path)
            try:
                second.show()
                self.app.processEvents()
                self.assertEqual(second.character_height, 150)
                self.assertEqual(second.pos(), position)
                self.assertFalse(second.always_on_top)
                self.assertTrue(second.panel.isVisible())
                anchor = second.pos() + QPoint(second.width()//2, second.height()-20)
                for height in (220, 180, 150):
                    second.set_character_size(height)
                    self.assertEqual(second.pos() + QPoint(second.width()//2, second.height()-20), anchor)
                    for state in ('idle', 'blink', 'happy'):
                        second.set_character_state(state)
                        self.assertEqual(second.animation.base_rect.height(), height)
            finally:
                second.close()
                second.tracker.close()

    def test_offscreen_position_returns_to_work_area(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.json'
            save_settings(path, dict(character_size=220, position=dict(x=999999, y=999999)))
            pet = DesktopPet(config_path=path)
            try:
                pet.show()
                self.app.processEvents()
                self.assertEqual(pet.character_height, 220)
                self.assertTrue(pet.screen().availableGeometry().contains(pet.geometry()))
            finally:
                pet.close()
                pet.tracker.close()
