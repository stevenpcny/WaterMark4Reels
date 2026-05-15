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
- **文案对照** — 预览视频和英文文案的对应关系；英文文案仅用于配对和复核
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
- 英文文案用于配对和人工复核，处理后默认不再生成同名 `.txt` 文件

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

---



### 第二轮体验优化

- 拖拽上传的视频会在当前会话里保留，新上传不会冲掉旧列表；需要重来时点击“清空已上传视频”。
- 切换文件夹或上传新视频时，人工复核状态和手动匹配记录会保留；切回原视频集合时可继续使用。
- 语音识别结果按当前表格、视频集合和识别参数缓存，切换后再切回不会立刻丢失。
- 增加“手动匹配 / 修正错配”，未识别出来或识别错的视频可以手动指定对应文件。
- 英文文案仅用于匹配和复核，批量处理后不再自动生成同名 `.txt` 文件。
- 成品默认建议放入单独的“打好水印”文件夹，并支持在 Google Drive 区域选择一个本地成品文件夹上传。
- 复核视频和水印预览合并到右侧检查区域，避免页面上同时出现两个大预览窗口。
- 检查视频支持标准/大/超大布局、播放器宽度调整、选中下一个视频后自动播放、预加载和自定义拖动预览条。

## Codex 5.5 隔离开发版说明

这个目录是从原项目复制出来的独立开发副本，默认用于验证工程化改造，不会读取或覆盖原目录里的 `presets.json`、`token.json`、`credentials.json` 或其他本地设置。

推荐用独立端口启动，避免和原版本冲突：

```bash
REELS_STREAMLIT_PORT=8502 python3 start.py
```

本版本新增了：

- `matching.py`：表格解析、视频排序、配对、输出命名、语音匹配分配等纯逻辑。
- `processing.py`：处理队列、跳过已存在输出、文案写入、处理报告、上传 MIME 判断。
- `ui_styles.py`：Streamlit 全局样式，让 `app.py` 更专注于界面流程。
- `tests/`：核心纯逻辑测试。
- `requirements-dev.txt`：开发/测试依赖。
- `DEVELOPMENT.md`：开发和验收说明。

批量处理完成后，输出目录会额外生成：

- `.reels-watermark-job.json`：机器可读任务记录。
- `处理结果.csv`：人工可读处理结果表。

再次运行同一批任务时，默认会跳过已经存在且完整的输出文件；如果你明确关闭“跳过已存在的输出文件”，仍可使用覆盖确认走旧流程。
