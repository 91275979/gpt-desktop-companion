"""由 Windows 隐藏启动；在 Qt 尚未加载时也能显示依赖错误。"""
import ctypes
import os
from pathlib import Path
import runpy
import sys


def main():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    try:
        import PySide6.QtWidgets  # noqa: F401
    except (ImportError, OSError):
        command = f'"{sys.executable}" -m pip install -r "{root / "requirements.txt"}"'
        ctypes.windll.user32.MessageBoxW(None,
            "缺少 PySide6 依赖或依赖无法加载。\n请在 PowerShell 中执行：\n\n& " + command,
            "GPT 桌宠 · 需要安装依赖", 0x10)
        return 1
    try:
        target = 'main.py'
        if '--watcher' in sys.argv:
            sys.argv.remove('--watcher')
            target = 'watcher.py'
        runpy.run_path(str(root / target), run_name="__main__")
    except SystemExit as exc:
        return exc.code or 0
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(None,
            f"桌宠启动或运行失败（{type(exc).__name__}）。\n"
            "请在项目目录运行 .venv\\Scripts\\python.exe main.py 查看详细错误。",
            "GPT 桌宠 · 启动失败", 0x10)
        return 1


if __name__ == "__main__":
    sys.exit(main())
