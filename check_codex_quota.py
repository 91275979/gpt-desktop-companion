"""只读连接测试，不读取密钥、不发送模型请求。"""
import sys
import argparse
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QTimer
from quota_provider import CodexQuotaProvider
from usage_tracker import UsageTracker


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=1, choices=range(1, 6))
    parser.add_argument('--gui', action='store_true', help='显示真实额度详情，检查后自动退出')
    args = parser.parse_args()
    if args.gui:
        from PySide6.QtWidgets import QApplication
        from main import DesktopPet
        app = QApplication(sys.argv)
    else:
        app = QCoreApplication(sys.argv)
    tracker = UsageTracker()
    pet = DesktopPet(tracker=tracker) if args.gui else None
    client = pet.quota_client if pet else CodexQuotaProvider()
    if pet:
        pet.show()
        pet.show_info_panel()
    exit_code = [1]
    count = [0]
    last_stamp = [None]

    def finish():
        if pet:
            pet.settle_usage()
            target = Path(__file__).resolve().parent / 'data' / 'quota-panel-check.png'
            target.parent.mkdir(exist_ok=True)
            pet.panel.grab().save(str(target))
            print('浮窗状态：', pet.usage_popup.phase)
            print('面板截图：', target)
            pet.close()
        client.stop()
        app.quit()

    def received(update):
        count[0] += 1
        if not pet:
            tracker.record_quota(update)
        print('读取', count[0], '状态：', update.error or '读取成功')
        for snapshot in update.snapshots:
            print(f'{snapshot.period}: used={snapshot.used:g}%, remaining={snapshot.remaining:g}%')
        if update.snapshots:
            stamp = update.snapshots[0].fetched_at
            if last_stamp[0] is not None:
                print(f'快照间隔：{stamp - last_stamp[0]:.2f}s')
            last_stamp[0] = stamp
        print('Tracker 快照数：', len(tracker.quota_details()))
        exit_code[0] = int(update.error is not None)
        if update.error or count[0] >= args.samples:
            client.stop()
            QTimer.singleShot(300, finish)

    client.updated.connect(received)
    QTimer.singleShot(0, client.start)
    QTimer.singleShot(20000, finish)
    app.exec()
    client.stop()
    tracker.close()
    return exit_code[0]


if __name__ == "__main__":
    sys.exit(main())
