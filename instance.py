"""Windows 会话内的单实例锁与正常退出信号；进程结束后句柄自动释放。"""
import ctypes
from ctypes import wintypes as w

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.CreateMutexW.argtypes = [w.LPVOID, w.BOOL, w.LPCWSTR]
kernel.CreateMutexW.restype = w.HANDLE
kernel.OpenMutexW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
kernel.OpenMutexW.restype = w.HANDLE
kernel.CreateEventW.argtypes = [w.LPVOID, w.BOOL, w.BOOL, w.LPCWSTR]
kernel.CreateEventW.restype = w.HANDLE
kernel.OpenEventW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
kernel.OpenEventW.restype = w.HANDLE
kernel.SetEvent.argtypes = [w.HANDLE]
kernel.ResetEvent.argtypes = [w.HANDLE]
kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
kernel.CloseHandle.argtypes = [w.HANDLE]


def name(role):
    return 'Local\\GPTDesktopCompanion.v1.' + role


class SingleInstance:
    def __init__(self, role):
        self.handle = kernel.CreateMutexW(None, False, name(role))
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.acquired = ctypes.get_last_error() != 183
        if not self.acquired:
            self.close()

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None


def is_running(role):
    handle = kernel.OpenMutexW(0x100000, False, name(role))
    if handle:
        kernel.CloseHandle(handle)
        return True
    return ctypes.get_last_error() == 5  # 无权访问时也不要重复启动。


class Event:
    def __init__(self, role):
        self.handle = kernel.CreateEventW(None, True, False, name(role))
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        kernel.ResetEvent(self.handle)

    def consume(self):
        signaled = kernel.WaitForSingleObject(self.handle, 0) == 0
        if signaled:
            kernel.ResetEvent(self.handle)
        return signaled

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None


def signal(role):
    handle = kernel.OpenEventW(2, False, name(role))
    if not handle:
        return False
    try:
        return bool(kernel.SetEvent(handle))
    finally:
        kernel.CloseHandle(handle)


class PetLifecycle:
    """将外部退出请求送到 Qt 主线程，走原有保存设置和资源清理。"""
    def __init__(self, pet):
        from PySide6.QtCore import QTimer
        self.event = Event('pet.close')
        self.timer = QTimer(pet)
        self.timer.setInterval(200)
        self.timer.timeout.connect(lambda: pet.close() if self.event.consume() else None)
        self.timer.start()

    def close(self):
        self.timer.stop()
        self.event.close()
