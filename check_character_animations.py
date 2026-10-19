"""验证导入的动画素材和真实窗口绘制；不修改配置或连接网络。"""
import json
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from main import DesktopPet
from character import CharacterState


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    pet = DesktopPet()
    try:
        assert not pet.assets.unavailable, pet.assets.unavailable
        assert not pet.assets.invalid_animations, pet.assets.invalid_animations
        pet.show()
        app.processEvents()
        results = {}
        output = Path(__file__).resolve().parent / 'data' / 'animation-check'
        output.mkdir(parents=True, exist_ok=True)
        for state in CharacterState:
            name = state.value
            frames = pet.assets.frames[name]
            assert len(frames) == 12
            assert all(frame.size() == frames[0].size() for frame in frames)
            assert all(frame.hasAlphaChannel() for frame in frames)
            assert any(frame != frames[0] for frame in frames[1:]), name
            pet.set_character_state(name)
            assert pet.animation.displayed_state == name
            pet.grab().save(str(output / f'{name}.png'))
            QTest.qWait(100)
            results[name] = {'frames': len(frames), 'fps': pet.assets.frame_rates[name]}
        print(json.dumps(results), flush=True)
        print('PASS: all 10 states load and render without fallback.', flush=True)
    finally:
        pet.close()
        pet.tracker.close()


if __name__ == '__main__':
    main()
