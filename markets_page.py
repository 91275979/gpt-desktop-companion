from datetime import datetime,timezone,timedelta
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QFrame,QHBoxLayout
from market_provider import INDICES


def market_direction(change_percent):
    value = round(change_percent, 2)
    return (value > 0) - (value < 0)


def get_market_color(change_percent, scheme='cn'):
    direction = market_direction(change_percent)
    if direction == 0:
        return '#A4A4AA'
    up, down = ('#3FAE74', '#E25555') if scheme == 'global' else ('#E25555', '#3FAE74')
    return up if direction > 0 else down


def market_change_text(change_percent):
    direction = market_direction(change_percent)
    if direction == 0:
        return '— 0.00%'
    return f'{"▲" if direction > 0 else "▼"} {change_percent:+.2f}%'



class MarketsPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(4)
        title=QLabel('Markets')
        title.setStyleSheet('font-size:15px; font-weight:600;')
        layout.addWidget(title)
        self.rows={}
        self.color_scheme="cn"
        columns = QHBoxLayout()
        columns.setSpacing(5)
        group_layouts = {}
        for group, heading in (('美国','US'),('中国','CN')):
            column = QVBoxLayout()
            column.setSpacing(4)
            label=QLabel(heading)
            label.setStyleSheet('color:#999;font-size:9px;')
            column.addWidget(label)
            group_layouts[group] = column
            columns.addLayout(column, 1)
        for symbol,name,group in INDICES:
            card=QFrame()
            card.setFixedHeight(34)
            card.setObjectName('marketCard')
            card.setStyleSheet('QFrame#marketCard {background:rgba(255,255,255,9); border:1px solid #414245; border-radius:8px;}')
            body=QVBoxLayout(card)
            body.setContentsMargins(6,2,6,2)
            body.setSpacing(0)
            top=QHBoxLayout()
            top.setSpacing(2)
            name_label=QLabel('Nasdaq' if symbol=='^IXIC' else 'Dow Jones' if symbol=='^DJI' else name)
            name_label.setToolTip(name)
            name_label.setStyleSheet('font-size:8px; color:#bbb;')
            value=QLabel('—')
            value.setStyleSheet('font-size:10px; font-weight:600; color:#f4f4f4;')
            top.addWidget(name_label)
            top.addStretch()

            change=QLabel('—')
            change.setStyleSheet('font-size:8px; color:#ccc;')
            stamp=QLabel('')
            stamp.setStyleSheet('font-size:8px; color:#999;')
            top.addWidget(change)
            body.addLayout(top)
            body.addWidget(value)
            stamp.hide()
            group_layouts[group].addWidget(card)
            self.rows[symbol]=(value,change,stamp)
        layout.addLayout(columns)
        self.status=QLabel('来源：Yahoo Finance · 行情可能延迟')
        self.status.setWordWrap(True)
        self.status.setStyleSheet('color:#999;font-size:10px;')
        self.status.hide()
        layout.addStretch()

    def update_markets(self,update):
        for q in update.quotes:
            value,change,stamp=self.rows[q.symbol]
            value.setText(f'{q.price:,.2f}')
            change.setText(market_change_text(q.percent))
            change.setStyleSheet(f'font-size:8px; font-weight:600; color:{get_market_color(q.percent,self.color_scheme)};')
            value.setToolTip(f'较前收 {q.change:+,.2f}')
            date=datetime.fromtimestamp(q.market_time,timezone(timedelta(seconds=q.offset))).strftime('%m-%d %H:%M')
            stamp.setText(f'{date} {q.timezone_name} · '+('旧数据' if q.symbol in update.failed else q.state))
        for symbol in update.failed:
            if symbol not in {q.symbol for q in update.quotes}:
                self.rows[symbol][2].setText('行情数据暂不可用')
        self.status.setText(('部分行情暂不可用 · 保留上次数据\n' if update.failed else '')+
                            '来源：Yahoo Finance · 行情可能延迟')
