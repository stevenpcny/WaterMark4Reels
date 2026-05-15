# Windows 版打包与使用

## 先说明

真正的 Windows `.exe` 需要在 Windows 电脑上打包。PyInstaller 不能在 macOS 上直接生成可靠的 Windows exe。

本目录已经准备好两种方式：

- `start-windows.bat`：不打包，直接在 Windows 上双击运行源码版。
- `启动水印工具-Windows.bat`：同上，中文文件名版本。
- `build_windows.bat`：在 Windows 上生成文件夹版 exe。

## 方式一：直接运行源码版

1. 安装 Windows 版 Python 3.10 或 3.11。
2. 安装时勾选 `Add python.exe to PATH`。
3. 安装 FFmpeg，并加入 PATH；或者把 `ffmpeg.exe` 和 `ffprobe.exe` 放到项目目录：

```text
ffmpeg\bin\ffmpeg.exe
ffmpeg\bin\ffprobe.exe
```

4. 双击：

```text
windows\start-windows.bat
```

首次运行会自动创建 `.venv-win` 并安装依赖。

## 方式二：生成 Windows exe

在 Windows 电脑上双击：

```text
windows\build_windows.bat
```

脚本会自动准备便携版资产：

- Windows 版 FFmpeg essentials build
- 本地 Whisper `base` 模型：`Systran/faster-whisper-base`

完成后生成：

```text
dist\ReelsWatermarkTool\ReelsWatermarkTool.exe
```

分发时复制整个文件夹：

```text
dist\ReelsWatermarkTool
```

不要只复制单个 exe，因为依赖文件在同一个文件夹里。

## FFmpeg

打包脚本会自动把项目目录下的 `ffmpeg` 文件夹复制到 exe 目录。

如果项目目录里还没有 FFmpeg，`build_windows.bat` 会自动下载 Windows essentials build。

推荐下载：

```text
https://www.gyan.dev/ffmpeg/builds/
```

下载后把 `bin` 里的 `ffmpeg.exe` 和 `ffprobe.exe` 放到：

```text
ffmpeg\bin
```

## Google Drive

如果要使用 Google Drive 上传功能，请把 `credentials.json` 手动放到 exe 同级目录：

```text
dist\ReelsWatermarkTool\credentials.json
```

授权 token 和工具设置会保存到：

```text
%APPDATA%\ReelsWatermarkTool
```

## 本地 Whisper

`build_windows.bat` 会自动下载并内置 `base` 模型：

```text
models\faster-whisper-base
```

用户拿到便携版后，选择 `base` 模型时不需要再次联网下载。

如果选择 `small` 模型，第一次使用仍然会联网下载，除非你以后也把 `small` 模型同样内置。
