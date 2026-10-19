from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QInputDialog, QLineEdit
from weather_provider import conditions, clothing


class ClickableLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class WeatherPage(QWidget):
    city_requested = Signal(str)
    ip_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        body = QVBoxLayout(self)
        body.setContentsMargins(0,0,0,0)
        body.setSpacing(4)
        self.location = ''
        self.city_button = QPushButton('手动城市')
        self.city_button.setStyleSheet('QPushButton {background:#343538;color:#eee;border:1px solid #555;border-radius:7px;padding:5px;} QPushButton:hover {background:#444;}')
        self.city_button.clicked.connect(self.edit_city)
        self.ip_button = QPushButton('按 IP 定位')
        self.ip_button.setStyleSheet(self.city_button.styleSheet())
        self.ip_button.clicked.connect(self.ip_requested.emit)
        self.fields = {}
        temperature_row = QHBoxLayout()
        temperature_row.setSpacing(7)
        for key, text, size in (('title','Weather',15),('location','尚未设置城市',12),
                               ('icon','',22),('current','—',20),('details','',11),('advice','',10),
                               ('status','点击上方按钮设置所在城市',9),
                               ('source','来源：Open-Meteo · 天气模型数据',9)):
            label = ClickableLabel(text) if key == 'location' else QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet(f'font-size:{size}px; color:{"#f2f2f2" if size>=16 else "#aaa"};')
            if key in ('icon', 'current'):
                temperature_row.addWidget(label)
                if key == 'current':
                    temperature_row.addStretch()
                    body.addLayout(temperature_row)
            else:
                body.addWidget(label)
            self.fields[key] = label
            if key == 'location':
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                label.setToolTip('点击更改城市')
                label.clicked.connect(self.edit_city)
                buttons = QHBoxLayout()
                buttons.addWidget(self.city_button)
                buttons.addWidget(self.ip_button)
                body.addLayout(buttons)
        self.fields['icon'].setStyleSheet("font-family:'Segoe UI Symbol';font-size:25px;color:#bbc5cb;")
        self.fields['advice'].hide()
        self.fields['source'].hide()
        self._set_location_buttons_visible(True)
        body.addStretch()

    def _set_location_buttons_visible(self, visible):
        self.city_button.setVisible(visible)
        self.ip_button.setVisible(visible)

    def edit_city(self):
        dialog = QInputDialog(self)
        dialog.setWindowTitle('设置所在城市')
        dialog.setLabelText("城市，可附国家名称\n例如 Tokyo, Japan 或 Xi'an, China")
        dialog.setTextValue(self.location)
        dialog.setOkButtonText('保存')
        dialog.setCancelButtonText('取消')
        dialog.setMinimumWidth(300)
        dialog.setStyleSheet('QInputDialog {background:#252628;color:#eee;} QLabel {color:#ddd;} QLineEdit {background:#343538;color:white;border:1px solid #666;border-radius:6px;padding:7px;} QPushButton {background:#414246;color:white;border:none;border-radius:6px;padding:7px 18px;}')
        entry = dialog.findChild(QLineEdit)
        if entry: entry.setMaxLength(200)
        if dialog.exec():
            city = dialog.textValue().strip()
            if city:
                self.city_requested.emit(city)
            else:
                self.fields['status'].setText('请输入城市名称')
        dialog.deleteLater()

    def set_location(self, location, loading=False):
        self.location = location
        self.city_button.setText('更改城市' if location else '手动城市')
        self.fields['location'].setText(location or '尚未设置城市')
        for key in ('icon','details','advice'): self.fields[key].clear()
        for key in ('icon','current','details'): self.fields[key].setVisible(bool(location))
        self.fields['advice'].hide()
        self.fields['current'].setText('—')
        self.fields['status'].setText('正在获取天气…' if loading else ('等待天气更新' if location else '点击上方按钮设置所在城市'))
        self._set_location_buttons_visible(not bool(location))

    def set_location_mode(self, automatic):
        if automatic:
            self._set_location_buttons_visible(False)
            self.city_button.setText('手动城市')
        self.ip_button.setText('刷新 IP' if automatic else '按 IP 定位')
        self.fields['source'].setText(('定位：公网 IP（可能为 VPN 出口）\n' if automatic else '定位：手动城市\n')
                                      + '天气：Open-Meteo')
        if automatic:
            self.fields['location'].setText('按当前公网 IP 定位')
            self.fields['status'].setText('正在定位并获取天气…')

    def update_weather(self, snapshot, error=''):
        self.fields['status'].setText(error)
        if snapshot is None:
            return
        s = snapshot
        for key in ('icon','current','details'): self.fields[key].show()
        self.fields['location'].setText(s.location)
        self.fields['icon'].setText(weather_icon(s.code))
        self.fields['current'].setText(f'当前 {s.temperature:g}°C')
        self.fields['details'].setText('天气：'+conditions(s.code))
        self.fields['advice'].setText('今日穿衣建议\n'+clothing(s))
        self.fields['advice'].hide()
        self.fields['status'].setText(error+' · 保留上次数据' if error else '')
        self.fields['status'].setVisible(bool(error))
        self._set_location_buttons_visible(False)


def weather_icon(code):
    if code == 0: symbol = '☀'
    elif code in (71,73,75,77,85,86): symbol = '❄'
    elif code in (95,96,99): symbol = 'ϟ'
    elif code in (51,53,55,56,57,61,63,65,66,67,80,81,82): symbol = '☂'
    else: symbol = '☁'
    return symbol+'\ufe0e'  # 文本呈现，避免系统自动换成鲜艳彩色 emoji。
