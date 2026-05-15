@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "LOG=%ROOT%\windows-build.log"

echo === Reels Watermark Tool Windows Build === > "%LOG%"
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

if not exist ".venv-build-win\Scripts\python.exe" (
    echo 正在创建打包环境...
    %PY% -m venv ".venv-build-win" >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo 创建打包环境失败，请查看 %LOG%
        pause
        exit /b 1
    )
)

call ".venv-build-win\Scripts\activate.bat"

echo 正在安装打包依赖...
python -m pip install --upgrade pip >> "%LOG%" 2>&1
python -m pip install -r requirements.txt pyinstaller >> "%LOG%" 2>&1
if errorlevel 1 (
    echo 依赖安装失败，请查看 %LOG%
    pause
    exit /b 1
)

echo 正在准备便携版 FFmpeg 和 Whisper base 模型...
powershell -NoProfile -ExecutionPolicy Bypass -File "windows\prepare_portable_assets.ps1" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo 便携版资产准备失败，请查看 %LOG%
    pause
    exit /b 1
)

echo 正在生成 Windows 文件夹版 exe...
pyinstaller --clean --noconfirm "windows\ReelsWatermarkTool.spec" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo 打包失败，请查看 %LOG%
    pause
    exit /b 1
)

if exist "ffmpeg\bin\ffmpeg.exe" (
    xcopy "ffmpeg" "dist\ReelsWatermarkTool\ffmpeg" /E /I /Y >> "%LOG%" 2>&1
)

if exist "models\faster-whisper-base\model.bin" (
    xcopy "models" "dist\ReelsWatermarkTool\models" /E /I /Y >> "%LOG%" 2>&1
)

echo.
echo 打包完成：
echo %ROOT%\dist\ReelsWatermarkTool\ReelsWatermarkTool.exe
echo.
echo 分发时请复制整个 dist\ReelsWatermarkTool 文件夹，不要只复制 exe。
echo 已内置 FFmpeg 和 faster-whisper base 模型。
echo 如果要使用 Google Drive，请把 credentials.json 手动放到 exe 同级目录。
pause

endlocal
