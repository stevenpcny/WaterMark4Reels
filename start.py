import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


def _app_dir() -> Path:
    """返回 app.py 所在目录；PyInstaller 打包后使用解包目录。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _open_browser_when_ready(url: str) -> None:
    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=1)
            webbrowser.open(url)
            return
        except Exception:
            time.sleep(0.5)


APP_DIR = _app_dir()
APP_PY = APP_DIR / "app.py"
PORT = os.environ.get("REELS_STREAMLIT_PORT", "8501")
URL = f"http://localhost:{PORT}"

# 切换到 app.py 所在目录，避免双击启动时工作目录错误。
os.chdir(str(APP_DIR))

if os.environ.get("REELS_OPEN_BROWSER") == "1" or getattr(sys, "frozen", False):
    threading.Thread(target=_open_browser_when_ready, args=(URL,), daemon=True).start()

# 用 streamlit 的内部 CLI 启动 app.py
sys.argv = [
    "streamlit",
    "run",
    str(APP_PY),
    "--server.headless=true",
    "--server.fileWatcherType=none",
    f"--server.port={PORT}",
]

from streamlit.web import cli as stcli
stcli.main()
