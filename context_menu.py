"""桌宠的轻量控制菜单。"""

from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QMenu
from instance import is_running, signal


SIZES = {"小尺寸": 150, "中尺寸": 180, "大尺寸": 220}


def create_context_menu(pet):
    menu = QMenu(pet)
    menu.setStyleSheet("""
        QMenu { background: #252628; color: #eee; border: 1px solid #555;
                padding: 6px; font-family: 'Microsoft YaHei'; font-size: 12px; }
        QMenu::item { padding: 7px 24px; border-radius: 4px; }
        QMenu::item:selected { background: #444; }
        QMenu::item:disabled { color: #777; }
        QMenu::separator { height: 1px; background: #555; margin: 5px; }
    """)
    show = menu.addAction("使用详情", pet.show_info_panel)
    show.setEnabled(not pet.panel_requested)
    hide = menu.addAction("隐藏使用详情", pet.hide_info_panel)
    hide.setEnabled(pet.panel_requested)
    menu.addSeparator()
    group = QActionGroup(menu)
    group.setExclusive(True)
    for name, height in SIZES.items():
        action = menu.addAction(name)
        action.setCheckable(True)
        action.setChecked(pet.character_height == height)
        group.addAction(action)
        action.triggered.connect(lambda checked=False, height=height: pet.set_character_size(height))
    menu.addSeparator()
    on_top = menu.addAction("始终置顶")
    on_top.setCheckable(True)
    on_top.setChecked(pet.always_on_top)
    on_top.toggled.connect(pet.set_always_on_top)
    menu.addSeparator()
    if is_running('watcher'):
        def pause_session():
            signal('watcher.pause')
            pet.close()
        menu.addAction("本次会话不再自动启动", pause_session)
    menu.addAction("退出程序", pet.close)
    return menu
