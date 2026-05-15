# 🎬 WaterMark4Reels

批量给 Reels 视频打文字水印 + 自动重命名的本地工具。所有处理在本地完成，视频不会上传到任何服务器。

![Python](https://img.shields.io/badge/Python-3.9+-blue) ![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

---

## 功能特点

- **批量打水印** — 一次处理多个视频，水印文字、位置、字体、颜色、透明度全部可调
- **自动重命名** — 从 Google Sheets 粘贴三列数据（序号 + 中文标题 + 英文文案），自动匹配视频并用中文标题命名
- **语音识别配对** — 可先识别每个视频里的英文语音，再和表格英文文案自动匹配，解决无字幕视频难以编号的问题
- **免费本地识别** — 支持本地 Whisper `base` / `small` 模型，不需要 API Key
- **按顺序配对** — 视频没有字幕、文件名也没有序号时，可按视频文件顺序和表格行顺序直接配对，不用先手工改名
- **文案对照** — 预览视频和英文文案的对应关系，并自动生成同名 `.txt` 英文文案文件
- **GPU 加速** — 支持 Apple VideoToolbox 硬件编码，速度比纯 CPU 快 3-5 倍
- **画质控制** — CRF 18~28 可选，CRF 18 几乎无损
- **预设管理** — 保存 3 组参数预设，关闭后重新打开自动恢复上次设置
- **水印预览** — 处理前实时预览水印效果
- **本地运行** — 视频文件不离开你的电脑

---

## 使用要求

- macOS 10.13 或更高版本
- Windows 10/11（Windows 版请看 `windows/README-Windows.md`）
- Python 3.9+
- FFmpeg（macOS 首次启动可自动安装；Windows 需安装到 PATH 或放入 `ffmpeg\bin`）
- OpenAI API Key（仅选择 OpenAI API 识别时需要；本地 Whisper 不需要）

---

## 安装与启动

### 方式一：双击 .app 图标（推荐）

1. 下载或克隆本仓库
2. 双击 `Reels水印工具.app`
3. 首次启动会自动检测并安装缺失的依赖（Python 包、FFmpeg）
4. 浏览器自动打开工具界面

> ⚠️ `.app` 必须与 `app.py` 等文件放在同一个文件夹中，不能单独移走。

### 方式二：命令行启动

```bash
# 安装依赖
pip3 install -r requirements.txt

# 启动
python3 start.py
```

### Windows 版

Windows 启动和打包脚本在 `windows/` 目录：

- `windows/start-windows.bat`：Windows 上双击运行源码版
- `windows/build_windows.bat`：Windows 上生成 `dist/ReelsWatermarkTool/ReelsWatermarkTool.exe`

`build_windows.bat` 会自动准备并内置 Windows 版 FFmpeg 和本地 Whisper `base` 模型。

详细步骤见 `windows/README-Windows.md`。

---

## 使用方法

**① 导入视频**
- 直接拖拽视频文件到页面，或输入视频文件夹路径
- 指定原视频所在目录（用于确定默认输出位置）

**② 粘贴 Google Sheets 数据**
- 在 Google Sheets 中复制三列：第一列序号，第二列中文标题，第三列英文文案
- 粘贴到工具中，选择配对方式：
  - **语音识别自动配对**：识别视频中间片段的英文语音，和第三列英文文案计算匹配度，达到阈值才算成功
  - **按视频顺序配对**：表格第 1 行配第 1 个视频，第 2 行配第 2 个视频，适合视频没有字幕、无法提前编号的情况
  - **按序号/关键词匹配**：沿用原方式，表格第一列需要能匹配到视频文件名
- 语音识别方式可选：
  - **免费本地 Whisper base**：更快、更省资源，适合先跑一遍
  - **免费本地 Whisper small**：更准一些，但更慢
  - **OpenAI API**：更快更稳，但需要 API Key
- 可设置识别开始/结束位置、匹配度阈值，并在处理前审定输出视频命名规则
- 处理成功后会生成同名 `.txt` 英文文案文件，例如 `水印-1-中文标题.mp4` 对应 `水印-1-中文标题.txt`

**③ 调整水印参数**（侧边栏）
- 水印文字、位置（右下/左下/右上/左上/居中/自定义坐标）
- 字体、字号、透明度、颜色
- 输出画质、编码方式（CPU / GPU）

**④ 预览 → 开始处理**

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `app.py` | Streamlit 主界面 |
| `watermark.py` | 水印处理核心（FFmpeg + Pillow）|
| `presets.py` | 预设管理 |
| `start.py` | 启动入口 |
| `Reels水印工具.app` | macOS 应用图标 |
| `启动水印工具.command` | 备用启动脚本 |

---

## License

MIT
