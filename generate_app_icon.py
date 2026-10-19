"""从现有透明角色帧生成 Windows 快捷方式图标。"""
from pathlib import Path
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'assets' / 'characters' / 'animations' / 'happy' / '000.png'
OUTPUT = ROOT / 'assets' / 'characters' / 'gpt_companion.ico'


def main():
    source = QImage(str(SOURCE)).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    if source.isNull():
        raise SystemExit(f'无法读取 {SOURCE}')
    canvas = QImage(256, 256, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.GlobalColor.transparent)
    scaled = source.scaled(238, 238, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(QRectF((256-scaled.width())/2, 256-scaled.height()-5,
                             scaled.width(), scaled.height()), scaled)
    painter.end()
    if not canvas.save(str(OUTPUT), 'ICO'):
        raise SystemExit('Qt 无法写入 ICO 文件')
    print(OUTPUT)


if __name__ == '__main__':
    main()
