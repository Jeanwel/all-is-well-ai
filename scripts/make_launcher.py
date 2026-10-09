"""Creates a one-click 'start-demo' launcher on the Desktop that runs this project's run.py."""
import os
import platform
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def make() -> str:
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        onedrive = Path.home() / "OneDrive" / "Desktop"  # common on Windows
        desktop = onedrive if onedrive.exists() else ROOT
    system = platform.system()
    if system == "Windows":
        p = desktop / "start-demo.bat"
        p.write_text(f'@echo off\r\ntitle All Is Well AI\r\ncd /d "{ROOT}"\r\n"{ROOT}\\.venv\\Scripts\\python.exe" run.py\r\npause\r\n')
    else:
        p = desktop / ("start-demo.command" if system == "Darwin" else "start-demo.sh")
        p.write_text(f'#!/bin/bash\ncd "{ROOT}"\n"{ROOT}/.venv/bin/python" run.py\n')
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return f"Double-click {p} to start the demo."


if __name__ == "__main__":
    print(make())
