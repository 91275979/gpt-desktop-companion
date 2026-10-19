"""真实等待 30 秒验证启动空闲、情绪恢复后睡眠及点击唤醒，不修改用户配置。"""
import json
import time
from pathlib import Path
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from main import DesktopPet


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    pets, results, failures = {}, {}, []
    try:
        for name in ('startup', 'after_anger'):
            pet = DesktopPet()
            pet.setWindowTitle('Sleep check: ' + name)
            pets[name] = pet
            pet.show()
        pets['startup'].move(pets['after_anger'].x()-pets['startup'].width()-20,
                             pets['after_anger'].y())
        app.processEvents()
        angry = pets['after_anger']
        for _ in range(25):
            QTest.mouseClick(angry, Qt.MouseButton.LeftButton,
                             pos=angry.character_rect.center().toPoint())
            QTest.qWait(20)
        assert angry.interactions.anger_level == 5
        assert pets['startup'].interactions.last_click_time is None
        started = time.monotonic()
        output = Path(__file__).resolve().parent / 'data'
        output.mkdir(exist_ok=True)
        print('Waiting on real 30-second clocks: startup and after_anger.', flush=True)

        def check():
            try:
                for name, pet in pets.items():
                    if name in results or pet.animation.state.value != 'sleep':
                        continue
                    idle = pet.interactions.idle_seconds()
                    assert idle >= 30, (name, idle)
                    assert pet.animation.displayed_state == 'sleep'
                    assert not pet.interactions.fast_click_mode
                    assert pet.interactions.anger_level == 0
                    pet.grab().save(str(output / f'sleep-{name}.png'))
                    before = pet.animation.frame_elapsed
                    # 验证睡眠持续播放，不被 idle/blink 覆盖。
                    QTest.qWait(350)
                    assert pet.animation.state.value == 'sleep'
                    assert pet.animation.frame_elapsed > before
                    QTest.mouseClick(pet, Qt.MouseButton.LeftButton,
                                     pos=pet.character_rect.center().toPoint())
                    assert pet.greeting_visible
                    assert pet.animation.state.value != 'sleep'
                    assert pet.interactions.idle_seconds() < 1
                    results[name] = {'sleep_after_idle_seconds': round(idle, 3),
                                     'animated': True, 'click_woke': True}
                    print(json.dumps({name: results[name]}), flush=True)
                if len(results) == len(pets):
                    app.quit()
                elif time.monotonic()-started > 40:
                    raise AssertionError('Sleep timeout: ' + str(list(results)))
            except Exception as exc:
                failures.append(repr(exc))
                app.quit()

        timer = QTimer()
        timer.setInterval(100)
        timer.timeout.connect(check)
        timer.start()
        app.exec()
        timer.stop()
        assert not failures, failures
        assert len(results) == 2, results
        (output / 'sleep-check.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print('PASS: both real-time sleep paths and click wake-up.', flush=True)
    finally:
        for pet in pets.values():
            pet.close()
            pet.tracker.close()


if __name__ == '__main__':
    main()
