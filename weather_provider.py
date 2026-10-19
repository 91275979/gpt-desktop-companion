"""Open-Meteo 天气适配；不访问 UI，不调用大模型。"""
from dataclasses import dataclass
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time
from urllib.parse import urlencode
from PySide6.QtCore import QObject, Signal, QTimer
from http_client import JsonClient, number
from ip_location_provider import IP_LOCATION_URL, parse_ip_location


def weather_logger():
    logger = logging.getLogger('companion.weather')
    if not logger.handlers:
        path = Path(__file__).resolve().parent / 'data' / 'weather.log'
        try:
            path.parent.mkdir(exist_ok=True)
            handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding='utf-8')
        except OSError:
            handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def is_weihai(location):
    city = location.split(',')[0].strip().casefold().replace("'", '').replace('’', '')
    return city in {'weihai', '威海', '威海市', '山东威海', '山东省威海市'}


@dataclass(frozen=True)
class WeatherSnapshot:
    location: str
    temperature: float
    apparent: float
    high: float
    low: float
    rain_probability: float
    precipitation: float
    wind: float
    code: int
    observed_at: str
    timezone: str
    fetched_at: float


def conditions(code):
    if code == 0: return '晴'
    if code in (1,2,3): return '少云 / 多云' if code != 3 else '阴'
    if code in (45,48): return '雾'
    if code in (51,53,55): return '毛毛雨'
    if code in (56,57,66,67): return '冻雨'
    if code in (61,63,65): return {61:'小雨',63:'中雨',65:'大雨'}[code]
    if code in (71,73,75,77,85,86): return '降雪'
    if code in (80,81,82): return '阵雨'
    if code in (95,96,99): return '雷雨'
    return '未知天气'


def clothing(snapshot):
    temp = min(snapshot.temperature, snapshot.apparent)
    if temp < 5: text = '建议穿厚外套，注意保暖。'
    elif temp < 12: text = '建议穿外套和长袖。'
    elif temp < 20: text = '建议穿薄外套和长袖。'
    elif temp <= 28: text = '建议穿短袖或薄衣。'
    else: text = '建议穿轻薄透气的衣物。'
    if snapshot.rain_probability >= 40 or snapshot.precipitation > 0 or snapshot.code >= 51:
        text += '出门带伞，鞋子注意防水。'
    if snapshot.wind >= 25:
        text += '风较大，注意防风。'
    return text


def select_location(data, location):
    def normalize(value):
        return str(value).strip().casefold().removeprefix('the ')
    parts = [normalize(part) for part in location.split(',') if part.strip()]
    results = data.get('results', [])
    for candidate in results:
        if is_weihai(location) and not (
            normalize(candidate.get('country_code', '')) == 'cn'
            and normalize(candidate.get('admin1', '')) in {'shandong', '山东省', '山东'}
            and normalize(candidate.get('name', '')) in {'weihai', '威海', '威海市'}
        ):
            continue
        fields = {normalize(candidate.get(k, '')) for k in ('country', 'country_code', 'admin1', 'admin2', 'name')}
        if all(part in fields for part in parts[1:]):
            return candidate
    raise ValueError('找不到指定城市；请使用城市及英文国家名')


def parse_weather(data, location):
    current, daily = data['current'], data['daily']
    snapshot = WeatherSnapshot(location, number(current['temperature_2m']), number(current['apparent_temperature']),
        number(daily['temperature_2m_max'][0]), number(daily['temperature_2m_min'][0]),
        number(daily['precipitation_probability_max'][0]), number(current['precipitation']),
        number(current['wind_speed_10m']), int(number(current['weather_code'])),
        str(current['time']), str(data['timezone']), time.time())
    if not 0 <= snapshot.rain_probability <= 100 or snapshot.wind < 0:
        raise ValueError('天气数值越界')
    return snapshot


class WeatherProvider(QObject):
    updated = Signal(object, str)

    def __init__(self, location='', minutes=20, parent=None, auto_location=False):
        super().__init__(parent)
        self.location, self.snapshot, self.coordinates = location.strip(), None, None
        self.auto_location = auto_location
        self.logger = weather_logger()
        self.client = JsonClient(self, logger=self.logger)
        self.city_metadata = None
        self.geocode_queries = []
        self.busy = False
        self.timer = QTimer(self)
        self.timer.setInterval(max(15, min(30, minutes))*60000)
        self.timer.timeout.connect(self.refresh)

    def start(self):
        self.refresh()
        if self.location or self.auto_location:
            self.timer.start()

    def fail(self, message='天气数据暂不可用'):
        self.busy = False
        self.updated.emit(self.snapshot, message)

    def refresh(self):
        if self.busy or self.client.closed:
            return
        if self.auto_location:
            self.busy = True
            # 每轮天气刷新重新定位，网络/VPN 切换后不沿用旧坐标。
            self.client.get(IP_LOCATION_URL, self.ip_located)
            return
        if not self.location:
            self.updated.emit(None, '点击“设置所在城市”开始查看天气')
            return
        self.busy = True
        self.logger.info('Weather refresh original_input=%r', self.location)
        if self.coordinates:
            self.fetch_forecast()
        else:
            original = self.location.split(',')[0].strip()
            self.geocode_queries = [original]
            if is_weihai(self.location) and original != 'Weihai':
                self.geocode_queries.append('Weihai')
            self.search_city()

    def ip_located(self, data, error):
        try:
            if error:
                raise ValueError(error)
            location = parse_ip_location(data)
            self.coordinates = (location.latitude, location.longitude)
            self.display_location = f'{location.city}, {location.country}'
            self.city_metadata = dict(name=location.city, country=location.country,
                admin1=location.region, latitude=location.latitude,
                longitude=location.longitude, timezone=location.timezone, source='public_ip')
            self.logger.info('IP location selected %s', self.city_metadata)
        except (ValueError, KeyError, TypeError, AttributeError):
            self.logger.exception('IP location failed')
            self.fail('IP 定位暂不可用')
            return
        self.fetch_forecast()

    def search_city(self):
        query = self.geocode_queries.pop(0)
        self.logger.info('Geocoding query=%r', query)
        params = urlencode(dict(name=query,count=20,language='en',format='json'))
        self.client.get('https://geocoding-api.open-meteo.com/v1/search?'+params, self.geocoded)

    def geocoded(self, data, error):
        try:
            if error: raise ValueError(error)
            if not data.get('results') and self.geocode_queries:
                self.logger.info('Geocoding returned no results; trying city alias')
                self.search_city()
                return
            city = select_location(data, self.location)
            self.coordinates = (number(city['latitude']), number(city['longitude']))
            self.city_metadata = {key: city.get(key) for key in
                ('name', 'country', 'country_code', 'admin1', 'latitude', 'longitude', 'timezone')}
            self.logger.info('Geocoding selected %s', self.city_metadata)
            self.display_location = str(city['name']) + ', ' + str(city.get('country', ''))
        except (ValueError, KeyError, TypeError, AttributeError):
            self.logger.exception('Geocoding failed original_input=%r', self.location)
            self.fail()
            return
        self.fetch_forecast()

    def fetch_forecast(self):
        params = urlencode(dict(latitude=self.coordinates[0],longitude=self.coordinates[1],timezone=(self.city_metadata or {}).get('timezone') or 'auto',forecast_days=1,
            current='temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m',
            daily='temperature_2m_max,temperature_2m_min,precipitation_probability_max',wind_speed_unit='kmh',temperature_unit='celsius'))
        self.client.get('https://api.open-meteo.com/v1/forecast?'+params, self.received)

    def received(self, data, error):
        try:
            if error: raise ValueError(error)
            snapshot = parse_weather(data, self.display_location)
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            self.logger.exception('Forecast parsing/request failed original_input=%r coordinates=%s', self.location, self.coordinates)
            self.fail()
            return
        self.snapshot, self.busy = snapshot, False
        self.logger.info('Forecast parsed successfully location=%r observed_at=%s timezone=%s',
            snapshot.location, snapshot.observed_at, snapshot.timezone)
        self.updated.emit(snapshot, '')

    def stop(self):
        self.timer.stop()
        self.client.close()
