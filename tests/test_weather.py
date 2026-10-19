import unittest
from unittest.mock import Mock
from urllib.parse import urlparse, parse_qs
from dataclasses import replace
from PySide6.QtWidgets import QApplication
from weather_provider import WeatherProvider, WeatherSnapshot, parse_weather, select_location, clothing


class WeatherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_rules_use_apparent_rain_and_wind(self):
        s=WeatherSnapshot('Test',15,3,18,2,60,0,30,61,'2026-09-22T12:00','Europe/Amsterdam',1)
        self.assertIn('厚外套',clothing(s))
        self.assertIn('带伞',clothing(s))
        self.assertIn('防风',clothing(s))
        for temp, expected in ((7,'外套和长袖'),(15,'薄外套'),(25,'短袖'),(30,'透气')):
            self.assertIn(expected,clothing(replace(s,temperature=temp,apparent=temp)))

    def test_country_disambiguation(self):
        data={'results':[{'name':'Breda','country':'United States','country_code':'US'},
                         {'name':'Breda','country':'The Netherlands','country_code':'NL'}]}
        self.assertEqual(select_location(data,'Breda, Netherlands')['country_code'],'NL')
        with self.assertRaises(ValueError): select_location(data,'Breda, XX')

    def test_weihai_alias_and_coordinate_request(self):
        city = dict(name='Weihai', country='China', country_code='CN', admin1='Shandong',
                    latitude=37.50914, longitude=122.11356, timezone='Asia/Shanghai')
        for original in ('威海', "Wei'hai,China", 'Weihai'):
            p = WeatherProvider(original)
            p.client.get = Mock()
            p.refresh()
            if original != 'Weihai':
                p.geocoded({'generationtime_ms': 1}, None)
                query = parse_qs(urlparse(p.client.get.call_args.args[0]).query)
                self.assertEqual(query['name'], ['Weihai'])
            p.geocoded({'results': [dict(city, admin1='Other'), city]}, None)
            query = parse_qs(urlparse(p.client.get.call_args.args[0]).query)
            self.assertEqual(query['latitude'], ['37.50914'])
            self.assertEqual(query['longitude'], ['122.11356'])
            self.assertEqual(query['timezone'], ['Asia/Shanghai'])
            self.assertEqual(p.city_metadata['admin1'], 'Shandong')
            p.stop()
        with self.assertRaises(ValueError):
            select_location({'results': [dict(city, admin1='Other')]}, '威海')

    def test_network_error_not_retried_as_alias_and_logged(self):
        p = WeatherProvider('威海')
        p.client.get = Mock()
        p.refresh()
        with self.assertLogs('companion.weather', level='ERROR') as logs:
            p.geocoded(None, 'TimeoutError: timed out')
        self.assertIn('TimeoutError: timed out', '\n'.join(logs.output))
        self.assertEqual(p.client.get.call_count, 1)
        self.assertFalse(p.busy)
        p.stop()

    def test_parse_missing_data_fails_instead_of_zero(self):
        with self.assertRaises(KeyError): parse_weather({'current':{},'daily':{}},'Test')

    def test_empty_city_no_request_failure_keeps_last_success(self):
        p=WeatherProvider()
        calls=[]
        p.client.get=lambda *args:calls.append(args)
        emitted=[]
        p.updated.connect(lambda data,error:emitted.append((data,error)))
        p.start()
        self.assertEqual(calls,[])
        self.assertFalse(p.timer.isActive())
        self.assertIn('设置所在城市',emitted[-1][1])
        marker=object()
        p.snapshot=marker
        p.received(None,'network failure')
        self.assertIs(emitted[-1][0],marker)
        self.assertEqual(emitted[-1][1],'天气数据暂不可用')
        self.assertEqual(p.timer.interval(),20*60000)
        p.stop()
