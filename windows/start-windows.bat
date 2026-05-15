@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "LOG=%ROOT%\windows-start.log"

echo === Reels Watermark Tool Windows Start === > "%LOG%"
echo Project: %ROOT%>> "%LOG%"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PY=python"
    ) else (
        echo 未找到 Python。请先安装 Python 3.10 或 3.11。>> "%LOG%"
        start "" "https://www.python.org/downloads/windows/"
        echo.
        echo 未找到 Python。请先安装 Python 3.10 或 3.11，安装时勾选 Add python.exe to PATH。
        pause
        exit /b 1
    )
)

if not exist ".venv-win\Scripts\python.exe" (
    echo 正在创建 Windows 虚拟环境...
    %PY% -m venv ".venv-win" >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo 创建虚拟环境失败，请查看 %LOG%
        pause
        exit /b 1
    )
)

call ".venv-win\Scripts\activate.bat"

echo 正在安装/检查依赖，请稍候...
python -m pip install --upgrade pip >> "%LOG%" 2>&1
python -m pip install -r requirements.txt >> "%LOG%" 2>&1
if errorlevel 1 (
    echo Python 依赖安装失败，请查看 %LOG%
    pause
    exit /b 1
)

set "LOCAL_FFMPEG=%ROOT%\ffmpeg\bin"
if exist "%LOCAL_FFMPEG%\ffmpeg.exe" (
    set "PATH=%LOCAL_FFMPEG%;%PATH%"
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo.
    echo 未检测到 FFmpeg。
    echo 请安装 FFmpeg 并加入 PATH，或者把 ffmpeg.exe 和 ffprobe.exe 放到：
    echo %ROOT%\ffmpeg\bin
    echo.
    echo 推荐下载：https://www.gyan.dev/ffmpeg/builds/
    pause
    exit /b 1
)

set "REELS_OPEN_BROWSER=1"
set "REELS_STREAMLIT_PORT=8501"

echo 正在启动工具...
python start.py

endlocal
