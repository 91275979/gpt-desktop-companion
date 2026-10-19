"""独立后台监控器：2 秒检查，检测到手动退出后等待 3 秒，不接触角色动画。"""
import argparse
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import QCoreApplication, QTimer
from instance import SingleInstance, Event, is_running, signal

ROOT = Path(__file__).resolve().parent
# 经本机进程和 Get-StartApps 实际核验；版本号更新时仍匹配同一安装包。
PROCESS_NAME = 'ChatGPT.exe'
PACKAGE_PREFIX = 'OpenAI.Codex_'
PUBLISHER_SUFFIX = '__2p2nqsd0c76g0'


def matches_target(path):
    path = Path(path)
    return (path.name.lower() == PROCESS_NAME.lower() and path.parent.name.lower() == 'app'
            and path.parent.parent.name.lower().startswith(PACKAGE_PREFIX.lower())
            and path.parent.parent.name.lower().endswith(PUBLISHER_SUFFIX.lower())
            and path.parent.parent.parent.name.lower() == 'windowsapps')


class ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('th32ProcessID', w.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', w.DWORD),
                ('cntThreads', w.DWORD), ('th32ParentProcessID', w.DWORD),
                ('pcPriClassBase', w.LONG), ('dwFlags', w.DWORD), ('szExeFile', w.WCHAR * 260)]


def target_running():
    """仅候选同名进程查询路径，不每轮启动 PowerShell，不读取命令行/凭据。"""
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    k.CreateToolhelp32Snapshot.restype = w.HANDLE
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [w.HANDLE, ctypes.POINTER(ProcessEntry)]
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    k.CloseHandle.argtypes = [w.HANDLE]
    snapshot = k.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return None  # 无法确认时不把“失败”解释成应用退出。
    uncertain = False
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = k.Process32FirstW(snapshot, ctypes.byref(entry))
        if not more:
            return None
        while more:
            if entry.szExeFile.lower() == PROCESS_NAME.lower():
                process = k.OpenProcess(0x1000, False, entry.th32ProcessID)
                if process:
                    try:
                        size = w.DWORD(32768)
                        buffer = ctypes.create_unicode_buffer(size.value)
                        if k.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                            if matches_target(buffer.value):
                                return True
                        else:
                            uncertain = True
                    finally:
                        k.CloseHandle(process)
                else:
                    uncertain = True
            more = k.Process32NextW(snapshot, ctypes.byref(entry))
        return None if uncertain else False
    finally:
        k.CloseHandle(snapshot)


class Monitor:
    def __init__(self, detect=target_running, running=lambda: is_running('pet'),
                 start=None, stop=lambda: signal('pet.close'), clock=time.monotonic):
        self.detect, self.running, self.stop, self.clock = detect, running, stop, clock
        self.start = start or self.start_pet
        self.active = False
        self.suppressed = False
        self.missing_since = None
        self.starting_until = 0

    @staticmethod
    def start_pet():
        python = ROOT / '.venv' / 'Scripts' / 'python.exe'
        subprocess.Popen([str(python if python.exists() else sys.executable), str(ROOT/'launch.py')],
                         cwd=str(ROOT), creationflags=subprocess.CREATE_NO_WINDOW,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def tick(self, pause=False):
        now = self.clock()
        target = self.detect()
        if pause:
            self.suppressed = True
        if target is None:
            return
        pet = self.running()
        if not target:
            self.active, self.suppressed = False, False
            self.missing_since = None
            self.starting_until = 0
            if pet:
                self.stop()
            return
        newly_started = not self.active
        self.active = True
        if self.suppressed:
            if pet:
                self.stop()
            return
        if pet:
            self.missing_since = None
            self.starting_until = 0
            return
        if now < self.starting_until:
            return
        if self.missing_since is None:
            self.missing_since = now
        if newly_started or now-self.missing_since >= 3:
            # 给启动加载留出时间；失败后再试，不每 2 秒创建启动进程。
            self.starting_until = now+12
            try:
                self.start()
            except OSError:
                pass
            self.missing_since = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stop', action='store_true', help='停止监控，不关闭当前桌宠')
    args = parser.parse_args()
    if args.stop:
        signal('watcher.close')
        return 0
    guard = SingleInstance('watcher')
    if not guard.acquired:
        return 0
    app = QCoreApplication(sys.argv)
    stop_event, pause_event = Event('watcher.close'), Event('watcher.pause')
    monitor = Monitor()
    timer = QTimer()
    timer.setInterval(2000)
    retry = QTimer()
    retry.setSingleShot(True)
    def tick():
        if stop_event.consume():
            app.quit()
        else:
            monitor.tick(pause_event.consume())
            if (monitor.missing_since is not None and not monitor.suppressed
                    and monitor.starting_until <= monitor.clock()):
                retry.start(max(1, round((monitor.missing_since+3-monitor.clock())*1000)))
            else:
                retry.stop()
    timer.timeout.connect(tick)
    retry.timeout.connect(tick)
    timer.start()
    QTimer.singleShot(0, tick)
    try:
        return app.exec()
    finally:
        stop_event.close()
        pause_event.close()
        guard.close()


if __name__ == '__main__':
    sys.exit(main())
