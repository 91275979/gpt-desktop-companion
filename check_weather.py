"""通过正式 provider 验证真实天气；不修改配置，不启动其他数据源。"""
import json
import sys
from PySide6.QtCore import QCoreApplication, QTimer
from weather_provider import WeatherProvider


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    app = QCoreApplication(sys.argv)
    locations = sys.argv[1:] or ['威海', 'Weihai', 'Beijing', 'Tokyo', "Wei'hai,China"]
    providers, results = [], []

    def received(provider, snapshot, error):
        result = {'input': provider.location, 'geocoding': provider.city_metadata,
                  'success': snapshot is not None and not error, 'error': error}
        if snapshot:
            result.update(temperature=snapshot.temperature, observed_at=snapshot.observed_at)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        results.append(result)
        provider.stop()
        if len(results) == len(locations):
            app.quit()

    for location in locations:
        provider = WeatherProvider(location)
        provider.updated.connect(lambda snapshot, error, p=provider: received(p, snapshot, error))
        providers.append(provider)
        QTimer.singleShot(0, provider.refresh)
    QTimer.singleShot(65000, app.quit)
    app.exec()
    for provider in providers:
        provider.stop()
    return int(len(results) != len(locations) or any(not r['success'] for r in results))


if __name__ == '__main__':
    sys.exit(main())
