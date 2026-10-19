import random
import time
import unittest
from dataclasses import replace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from PySide6.QtWidgets import QApplication
from ip_location_provider import IP_LOCATION_URL, parse_ip_location
from weather_provider import WeatherProvider, WeatherSnapshot
from interaction_manager import InteractionManager, weather_dialogue


def snapshot():
    return WeatherSnapshot('Test City', 12, 9, 16, 7, 60, 0, 28, 61,
                           '2026-09-30T10:00', 'Asia/Tokyo', time.time())


class WeatherLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_ip_to_coordinates_refreshes_each_round_and_retains_on_failure(self):
        provider = WeatherProvider('Weihai', auto_location=True)
        provider.client.get = Mock()
        provider.start()
        self.assertEqual(provider.client.get.call_args.args[0], IP_LOCATION_URL)
        self.assertTrue(provider.timer.isActive())
        provider.ip_located(dict(success=True,city='Tokyo',country='Japan',region='Tokyo',
            latitude=35.68,longitude=139.69,timezone={'id':'Asia/Tokyo'}), None)
        url = provider.client.get.call_args.args[0]
        params = parse_qs(urlparse(url).query)
        self.assertIn('api.open-meteo.com', url)
        self.assertEqual(params['latitude'], ['35.68'])
        self.assertEqual(params['longitude'], ['139.69'])
        self.assertEqual(params['timezone'], ['Asia/Tokyo'])
        provider.snapshot = snapshot()
        provider.busy = False
        provider.refresh()
        self.assertEqual(provider.client.get.call_args.args[0], IP_LOCATION_URL)
        emitted = []
        provider.updated.connect(lambda data,error: emitted.append((data,error)))
        provider.ip_located(None, 'timeout')
        self.assertIs(emitted[-1][0], provider.snapshot)
        self.assertEqual(emitted[-1][1], 'IP 定位暂不可用')
        self.assertFalse(provider.busy)
        provider.stop()

    def test_invalid_ip_data_rejected(self):
        for data in (None, {'success':False}, {'success':True,'latitude':99,'longitude':1}):
            with self.assertRaises((ValueError,KeyError)):
                parse_ip_location(data)

    def test_reminder_deferred_rate_limited_and_does_not_count_as_click(self):
        now = [0.0]
        manager = InteractionManager(random.Random(2), clock=lambda: now[0])
        weather = snapshot()
        manager.receive_weather(weather)
        self.assertIsNone(manager.automatic_weather_dialogue(blocked=True))
        self.assertIsNone(manager.last_weather_reminder)
        result = manager.automatic_weather_dialogue()
        self.assertIn('外套和长袖', result.text)
        self.assertIn('带伞', result.text)
        self.assertIn('防风', result.text)
        self.assertEqual(result.expression, 'thinking')
        self.assertIsNone(manager.last_click_time)
        self.assertEqual(manager.last_interaction_time, 0)
        manager.receive_weather(weather)
        now[0] = 1801
        self.assertIsNone(manager.automatic_weather_dialogue())
        manager.receive_weather(replace(weather, apparent=30, temperature=31))
        self.assertIn('透气', manager.automatic_weather_dialogue().text)
        manager.receive_weather(weather, 'network error')
        self.assertIsNone(manager.automatic_weather_dialogue())
        manager.receive_weather(replace(weather, fetched_at=time.time()-3601))
        self.assertIsNone(manager.automatic_weather_dialogue())

    def test_fast_click_mode_never_overridden_by_weather(self):
        manager = InteractionManager()
        manager.receive_weather(snapshot())
        manager.click()
        result = manager.click(snapshot())
        self.assertTrue(manager.fast_click_mode)
        self.assertNotEqual(result.category, 'weather')
        self.assertIsNone(manager.automatic_weather_dialogue())

    def test_left_click_weather_category_uses_actual_conditions(self):
        manager = InteractionManager()
        manager.rng.choices = Mock(return_value=['weather'])
        weather = snapshot()
        result = manager.click(weather)
        self.assertEqual(result.text, weather_dialogue(weather))
        self.assertIn('9℃', result.text)
