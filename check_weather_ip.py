"""真实公网 IP 定位、天气和角色自动提醒的窗口验证；不改用户配置。"""
import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from main import DesktopPet


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    pet = DesktopPet()
    pet.show()
    pet.show_info_panel()
    pet.panel.set_page('weather', animate=False)
    result = [1]

    def finish():
        pet.close()
        pet.tracker.close()
        app.quit()

    def verify():
        if pet.greeting_visible and pet.interactions.last_weather_reminder is not None:
            print('Automatic dialogue:', pet.greeting_text, flush=True)
            output = Path(__file__).resolve().parent/'data'
            output.mkdir(exist_ok=True)
            pet.grab().save(str(output/'weather-ip-dialogue.png'))
            pet.panel.grab().save(str(output/'weather-ip-panel.png'))
            result[0] = 0
            timer.stop()
            finish()

    def received(snapshot, error):
        if error:
            print('FAILED:', error, pet.dashboard_services.weather.client.last_error, flush=True)
            timer.stop()
            finish()
        else:
            print('IP location:', snapshot.location, 'timezone:', snapshot.timezone, flush=True)
            print('Weather:', snapshot.temperature, 'C; apparent:', snapshot.apparent, flush=True)

    pet.dashboard_services.weather_updated.connect(received)
    timer = QTimer()
    timer.setInterval(200)
    timer.timeout.connect(verify)
    timer.start()
    QTimer.singleShot(0, pet.dashboard_services.weather.start)
    QTimer.singleShot(55000, finish)
    app.exec()
    return result[0]


if __name__ == '__main__':
    sys.exit(main())
