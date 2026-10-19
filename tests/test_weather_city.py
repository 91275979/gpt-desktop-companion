import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from main import DesktopPet
from settings import load_settings,save_settings
from markets_page import get_market_color,market_change_text


class CityAndColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_save_city_refresh_immediately_and_preserve_other_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            save_settings(path,{'market_color_scheme':'global','watchlist':['AAPL']})
            pet=DesktopPet(config_path=path)
            try:
                page=pet.panel.page_widgets['weather']
                self.assertEqual(page.city_button.text(),'手动城市')
                old=pet.dashboard_services.weather
                self.assertTrue(old.auto_location)
                with patch('weather_provider.WeatherProvider.start') as start:
                    page.city_requested.emit("Xi'an, China")
                    start.assert_called_once()
                self.assertTrue(old.client.closed)
                self.assertEqual(load_settings(path)['weather_location'],"Xi'an, China")
                self.assertEqual(load_settings(path)['weather_location_mode'], 'manual')
                self.assertFalse(pet.dashboard_services.weather.auto_location)
                self.assertEqual(load_settings(path)['watchlist'],['AAPL'])
                self.assertEqual(page.city_button.text(),'更改城市')
                self.assertEqual(page.fields['current'].text(),'—')
                self.assertEqual(pet.panel.page_widgets['markets'].color_scheme,'global')
                pet.save_preferences()
                self.assertEqual(load_settings(path)['weather_location'],"Xi'an, China")
            finally:
                pet.close();pet.tracker.close()
            reopened=DesktopPet(config_path=path)
            self.assertEqual(reopened.dashboard_services.weather.location,"Xi'an, China")
            self.assertFalse(reopened.dashboard_services.weather.auto_location)
            with patch('weather_provider.WeatherProvider.start') as start:
                reopened.panel.page_widgets['weather'].ip_requested.emit()
                start.assert_called_once()
            self.assertTrue(reopened.dashboard_services.weather.auto_location)
            self.assertEqual(load_settings(path)['weather_location_mode'], 'ip')
            reopened.close();reopened.tracker.close()

    def test_failed_save_does_not_change_provider_or_request(self):
        with tempfile.TemporaryDirectory() as folder:
            pet=DesktopPet(config_path=Path(folder)/'config.json')
            try:
                old=pet.dashboard_services.weather
                with patch('dashboard_services.save_settings',return_value=False):
                    pet.dashboard_services.set_city('Tokyo')
                self.assertIs(pet.dashboard_services.weather,old)
                self.assertIn('保存失败',pet.panel.page_widgets['weather'].fields['status'].text())
            finally:
                pet.close();pet.tracker.close()

    def test_color_schemes_and_near_zero_display(self):
        self.assertEqual(get_market_color(.62),'#E25555')
        self.assertEqual(get_market_color(-.38),'#3FAE74')
        self.assertEqual(get_market_color(.62,'global'),'#3FAE74')
        self.assertEqual(get_market_color(-.38,'global'),'#E25555')
        self.assertEqual(get_market_color(0),'#A4A4AA')
        self.assertEqual(market_change_text(-.001),'— 0.00%')
        self.assertEqual(market_change_text(.62),'▲ +0.62%')
