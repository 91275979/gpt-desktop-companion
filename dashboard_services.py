"""Dashboard 数据源装配，启动和退出由主程序调用。"""
from PySide6.QtCore import QObject, Signal
from weather_provider import WeatherProvider
from market_provider import MarketProvider
from settings import save_settings


class DashboardServices(QObject):
    weather_updated = Signal(object, str)

    def __init__(self, panel, settings, parent=None):
        super().__init__(parent)
        self.panel, self.settings = panel, settings
        self.config_path = getattr(parent, 'config_path', None)
        self._create_weather()
        panel.page_widgets['weather'].city_requested.connect(self.set_city)
        panel.page_widgets['weather'].ip_requested.connect(self.use_ip)
        self.markets = MarketProvider(settings['market_refresh_minutes'],self)
        panel.page_widgets['markets'].color_scheme = settings['market_color_scheme']
        self.markets.updated.connect(panel.page_widgets['markets'].update_markets)

    def _create_weather(self):
        automatic = self.settings.get('weather_location_mode', 'ip') == 'ip'
        self.weather = WeatherProvider(self.settings['weather_location'],
            self.settings['weather_refresh_minutes'], self, auto_location=automatic)
        page = self.panel.page_widgets['weather']
        self.weather.updated.connect(page.update_weather)
        self.weather.updated.connect(self.weather_updated.emit)
        page.set_location('' if automatic else self.settings['weather_location'])
        page.set_location_mode(automatic)

    def use_ip(self):
        if self.config_path is None or not save_settings(self.config_path, {'weather_location_mode':'ip'}):
            self.panel.page_widgets['weather'].fields['status'].setText('定位设置保存失败')
            return
        self.settings['weather_location_mode'] = 'ip'
        if self.weather.auto_location:
            self.weather.refresh()
            return
        self.weather.stop()
        self.weather.deleteLater()
        self._create_weather()
        self.weather_updated.emit(None, '正在切换到 IP 定位')
        self.weather.start()

    def set_city(self, city):
        city = city.strip()
        if not city or len(city)>200:
            return
        page = self.panel.page_widgets['weather']
        if self.config_path is None or not save_settings(self.config_path, {'weather_location':city, 'weather_location_mode':'manual'}):
            page.fields['status'].setText('城市保存失败，请检查配置文件的写入权限')
            return
        self.settings['weather_location'] = city
        self.settings['weather_location_mode'] = 'manual'
        self.weather.stop()  # 丢弃旧城市仍在途的请求，避免覆盖新城市。
        self.weather.deleteLater()
        self._create_weather()
        page.set_location(city,loading=True)
        self.weather_updated.emit(None, '正在切换城市')
        self.weather.start()

    def start(self):
        self.weather.start()
        self.markets.start()

    def stop(self):
        self.weather.stop()
        self.markets.stop()
