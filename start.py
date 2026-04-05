"""
启动包装器：在 Streamlit 加载之前先切换工作目录，
解决 .app 双击启动时 os.getcwd() 权限报错的问题。
"""
import os
import sys

# 切换到本文件所在目录（即 app.py 所在目录）
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 用 streamlit 的内部 CLI 启动 app.py
sys.argv = ["streamlit", "run", "app.py", "--server.headless=true"]

from streamlit.web import cli as stcli
stcli.main()
