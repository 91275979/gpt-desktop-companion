"""独立额度 UI 验证：仅内存夹具，不连接真实 provider，不写入真实账本。"""
from dataclasses import replace
from pathlib import Path
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from main import DesktopPet
from quota_provider import QuotaSnapshot, QuotaUpdate


def main():
    app = QApplication(sys.argv)
    pet = DesktopPet(demo_usage=True, enable_quota=False)
    pet.show()
    pet.show_info_panel()
    now = time.time() - 4
    five = QuotaSnapshot(100, 9, 91, 9, int(now+3600), now)
    week = replace(five, used=33, remaining=67, percentage=33, period='week', reset_time=int(now+86400))
    pet.update_quota(QuotaUpdate((five, week)))

    def change():
        pet.update_quota(QuotaUpdate((replace(five, used=10, remaining=90, percentage=10, fetched_at=now+2),
                                     replace(week, used=34, remaining=66, percentage=34, fetched_at=now+2))))
        pet.settle_usage()

    def capture():
        target = Path(__file__).resolve().parent / 'data'
        target.mkdir(exist_ok=True)
        pet.usage_popup.grab().save(str(target/'quota-popup-demo.png'))
        pet.panel.grab().save(str(target/'quota-panel-demo.png'))
        assert len(pet.usage_popup.quota_changes) == 2
        assert not pet.panel.token_area.isVisible()
        print('Dual quota popup and panel verified (simulation only).', flush=True)

    def again():
        pet.update_quota(QuotaUpdate((replace(five, used=11, remaining=89, percentage=11, fetched_at=now+4),
                                     replace(week, used=34, remaining=66, percentage=34, fetched_at=now+4))))
        pet.settle_usage()
        pet.move(pet.x()-60, pet.y()-30)

    def finish():
        assert pet.usage_popup.phase == 'hidden'
        pet.close()
        pet.tracker.close()
        app.quit()

    QTimer.singleShot(300, change)
    QTimer.singleShot(900, capture)
    QTimer.singleShot(2300, again)
    QTimer.singleShot(5500, finish)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
