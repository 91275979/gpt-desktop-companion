"""实际 Qt 窗口：测量左键释放至台词更新、首次绘制完成的耗时。"""
import json
import time
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from main import DesktopPet
from interaction_manager import ANGER_LINES


class MeasuredPet(DesktopPet):
    pending_stamp = None

    def mouseReleaseEvent(self, event):
        self.pending_stamp = time.perf_counter()
        super().mouseReleaseEvent(event)
        self.update_samples.append((time.perf_counter()-self.pending_stamp)*1000)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.pending_stamp is not None and self.greeting_visible:
            self.paint_samples.append((time.perf_counter()-self.pending_stamp)*1000)
            self.pending_stamp = None


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    pet = MeasuredPet()
    pet.update_samples, pet.paint_samples = [], []
    try:
        pet.show()
        QTest.qWait(100)
        for count in range(1, 26):
            QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=pet.character_rect.center().toPoint())
            assert pet.greeting_visible and pet.interactions.click_count == count
            if count >= 5:
                assert pet.greeting_text in ANGER_LINES[pet.interactions.anger_level]
            QTest.qWait(40)
        assert len(pet.paint_samples) == 25
        assert pet.interactions.anger_level == 5
        assert pet.animation.state == 'strong_angry'
        assert not pet.panel_requested
        path = Path(__file__).resolve().parent/'data'/'interaction-latency.json'
        report = {'samples': 25, 'release_to_text_ms': pet.update_samples,
                  'release_to_paint_ms': pet.paint_samples,
                  'max_text_ms': max(pet.update_samples), 'max_paint_ms': max(pet.paint_samples)}
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if not isinstance(v,list)}), flush=True)
        pet.grab().save(str(path.with_suffix('.png')))
        QTest.qWait(2800)
        assert not pet.greeting_visible
        assert pet.interactions.anger_level == 5
        assert pet.animation.state == 'strong_angry'
        QTest.qWait(1300)
        assert 0 < pet.interactions.anger_level < 5
        QTest.qWait(2200)
        assert not pet.interactions.fast_click_mode
        assert pet.animation.state == 'idle'
    finally:
        pet.close()
        pet.tracker.close()


if __name__ == '__main__':
    main()
