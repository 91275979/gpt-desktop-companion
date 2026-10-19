"""固定尺寸的三页 Dashboard；页面只展示数据。"""
from PySide6.QtCore import QRectF, Qt, QPropertyAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                               QPushButton, QStackedWidget, QGraphicsOpacityEffect, QScrollArea)
from PySide6.QtWidgets import QSizePolicy
from usage_page import UsagePage
from weather_page import WeatherPage
from markets_page import MarketsPage


class InfoPanel(QWidget):
    page_changed = Signal(str)
    PAGES = ('usage', 'weather', 'markets')
    PAGE_HEIGHTS = {'usage': 180, 'weather': 165, 'markets': 215}
    # Markets 使用最大高度；较短页面会按内容自动收紧。
    WIDTH, HEIGHT, GAP = 230, 180, 10
    BACKGROUND_ALPHA = 222

    def __init__(self, owner):
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.owner, self.page = owner, 'usage'
        self.setWindowTitle('GPT Companion · Dashboard')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setStyleSheet("""
            QLabel {color:#eee; background:transparent; font-family:'Microsoft YaHei'; font-size:11px;}
            QPushButton {color:#bbb; background:transparent; border:none; border-radius:5px; padding:2px;}
            QPushButton:hover {background:#444; color:white;}
            QScrollArea {border:none; background:transparent;}
            QScrollBar:vertical {width:4px; background:#28292b;}
            QScrollBar::handle:vertical {background:#666; border-radius:2px; min-height:20px;}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0px;}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 7, 11, 8)
        layout.setSpacing(2)
        header = QHBoxLayout()
        self.header_title = QLabel('GPT Companion')
        self.header_title.setStyleSheet('font-size:13px; font-weight:600;')
        self.header_title.setFixedWidth(112)
        header.addWidget(self.header_title)
        header.addStretch(1)
        self.settings_button = QPushButton('⋯')
        self.settings_button.setToolTip('设置 / 退出')
        self.settings_button.setFixedSize(23, 22)
        self.settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.settings_button)
        close = QPushButton('×')
        close.setFixedSize(20, 22)
        close.clicked.connect(owner.hide_info_panel)
        header.addWidget(close)
        layout.addLayout(header)
        nav = QHBoxLayout()
        nav.setSpacing(2)
        self.previous_button, self.next_button = QPushButton('‹'), QPushButton('›')
        self.previous_button.clicked.connect(lambda:self.cycle(-1))
        self.next_button.clicked.connect(lambda:self.cycle(1))
        self.dots = QLabel('●  ○  ○')
        self.dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dots.setStyleSheet('font-size:9px; color:#bbb;')
        self.dots.setToolTip('Usage · Weather · Markets')
        nav.addWidget(self.previous_button)
        nav.addWidget(self.dots, 1)
        nav.addWidget(self.next_button)
        layout.addLayout(nav)
        self.stack = QStackedWidget()
        self.stack.setMinimumWidth(0)
        self.stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.stack, 1)
        self.usage = UsagePage(self)
        self.page_widgets = {'usage': self.usage}
        for page in self.PAGES:
            if page == 'weather':
                self.page_widgets[page] = WeatherPage(self)
            elif page == 'markets':
                self.page_widgets[page] = MarketsPage(self)
            scroll = QScrollArea()
            scroll.setMinimumWidth(0)
            scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            if page == 'usage':
                scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.viewport().setStyleSheet('background:transparent;')
            scroll.setWidget(self.page_widgets[page])
            self.page_widgets[page].setStyleSheet('background:transparent;')
            self.stack.addWidget(scroll)
        for attr in ('cards', 'quota_five', 'quota_week', 'recent_label', 'quota_status',
                     'token_area', 'token_unavailable', 'values', 'subtitle'):
            setattr(self, attr, getattr(self.usage, attr))
        self.effect = QGraphicsOpacityEffect(self.stack)
        self.effect.setOpacity(1)
        self.stack.setGraphicsEffect(self.effect)
        self.fade = QPropertyAnimation(self.effect, b'opacity', self)
        self.fade.setDuration(80)
        self.fade.finished.connect(self.finish_transition)
        self.transition = 'idle'
        self.open_fade = QPropertyAnimation(self, b'windowOpacity', self)
        self.open_fade.setDuration(160)

    def update_quota(self, details, error=None):
        self.usage.update_quota(details, error)

    def update_usage(self, snapshot, demo=False):
        self.usage.update_usage(snapshot, demo)

    def set_page(self, page, animate=True):
        if page not in self.PAGES:
            return
        self.page = page
        self.setFixedHeight(self.PAGE_HEIGHTS[page])
        self.follow(self.owner)
        self.dots.setText('  '.join('●' if value == page else '○' for value in self.PAGES))
        self.fade.stop()
        if animate and self.isVisible():
            self.transition = 'out'
            self.fade.setStartValue(self.effect.opacity())
            self.fade.setEndValue(.55)
            self.fade.start()
        else:
            self.transition = 'idle'
            self.stack.setCurrentIndex(self.PAGES.index(page))
            self.effect.setOpacity(1)
        self.page_changed.emit(page)

    def finish_transition(self):
        if self.transition == 'out':
            self.stack.setCurrentIndex(self.PAGES.index(self.page))
            self.transition = 'in'
            self.fade.setStartValue(.55)
            self.fade.setEndValue(1)
            self.fade.start()
        else:
            self.transition = 'idle'

    def cycle(self, direction=1):
        self.set_page(self.PAGES[(self.PAGES.index(self.page)+direction) % 3])

    def open_settings(self):
        from context_menu import create_context_menu
        menu = create_context_menu(self.owner)
        menu.exec(self.settings_button.mapToGlobal(self.settings_button.rect().bottomLeft()))
        menu.deleteLater()

    def showEvent(self, event):
        self.setWindowOpacity(0)
        self.open_fade.setStartValue(0)
        self.open_fade.setEndValue(1)
        self.open_fade.start()
        super().showEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 24))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(2,3,-1,-1),13,13)
        painter.setPen(QPen(QColor(160, 160, 165, 70), .7))
        # 微透出桌面背景，同时保留文字的对比度。
        painter.setBrush(QColor(30, 31, 33, self.BACKGROUND_ALPHA))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-2.5,-3.5), 13, 13)

    def follow(self, owner):
        screen = QApplication.screenAt(owner.geometry().center()) or owner.screen()
        area = screen.availableGeometry()
        preferred_height = self.PAGE_HEIGHTS.get(self.page, self.HEIGHT)
        self.setFixedHeight(min(preferred_height, area.height()-16))
        # 以角色实际绘制区域为锚点；主窗口顶部还预留了台词区，不能按窗口边缘定位。
        character = getattr(owner, 'character_rect', None)
        if character is not None:
            anchor_left = owner.x() + round(character.left())
            anchor_top = owner.y() + round(character.top())
            anchor_bottom = owner.y() + round(character.bottom())
            anchor_center_x = owner.x() + round(character.center().x())
        else:
            anchor_left = owner.x()
            anchor_top = owner.y()
            anchor_bottom = owner.geometry().bottom()
            anchor_center_x = owner.geometry().center().x()
        # 优先紧贴角色头顶中央，接近屏幕顶部时再放到角色下方。
        x = anchor_center_x-self.width()//2
        x = max(area.left(), min(x, area.right()+1-self.width()))
        y = anchor_top-self.height()-self.GAP
        if y < area.top():
            y = anchor_bottom+1+self.GAP
        self.move(x, max(area.top(), min(y, area.bottom()+1-self.height())))
