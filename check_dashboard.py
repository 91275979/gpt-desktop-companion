"""真实数据和页面烟雾检查；测试城市仅作用于本进程，不写入用户配置。"""
import argparse
from pathlib import Path
import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from main import DesktopPet
from weather_provider import WeatherProvider
from market_provider import MarketProvider


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--weather-location',default='')
    parser.add_argument('--page',choices=('weather','markets'),default='weather')
    args=parser.parse_args()
    app=QApplication(sys.argv)
    pet=DesktopPet()
    pet.show()
    pet.show_info_panel()
    pet.panel.set_page(args.page,animate=False)
    provider=WeatherProvider(args.weather_location) if args.page=='weather' else MarketProvider()
    if args.page=='weather':
        provider.updated.connect(pet.panel.page_widgets['weather'].update_weather)
    else:
        provider.updated.connect(pet.panel.page_widgets['markets'].update_markets)
    result=[1]
    def finish():
        pet.panel.set_page(args.page,animate=False)
        app.processEvents()
        path=Path(__file__).resolve().parent/'data'/f'dashboard-{args.page}.png'
        path.parent.mkdir(exist_ok=True)
        pet.panel.grab().save(str(path))
        provider.stop()
        pet.close()
        pet.tracker.close()
        app.quit()
    def received(snapshot,error):
        result[0]=int(bool(error))
        print('Weather:',error or f'{snapshot.location}, {snapshot.temperature} C, {snapshot.observed_at}',flush=True)
        if error: print('Network diagnostic:',provider.client.last_error,flush=True)
        QTimer.singleShot(500,finish)
    def markets_received(update):
        if not provider.pending:
            result[0]=int(bool(update.failed))
            print('Markets: success=',len(update.quotes),'failed=',len(update.failed),flush=True)
            for item in update.quotes: print(item.name,item.price,item.change,item.percent,flush=True)
            QTimer.singleShot(500,finish)
    provider.updated.connect(received if args.page=='weather' else markets_received)
    QTimer.singleShot(0,provider.start)
    QTimer.singleShot(40000,finish)
    app.exec()
    return result[0]


if __name__=='__main__':
    sys.exit(main())
