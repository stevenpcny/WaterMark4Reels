# 🎬 WaterMark4Reels

批量给 Reels 视频打文字水印 + 自动重命名的 macOS 工具。所有处理在本地完成，视频不会上传到任何服务器。

![Python](https://img.shields.io/badge/Python-3.9+-blue) ![Platform](https://img.shields.io/badge/Platform-macOS-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

---

## 功能特点

- **批量打水印** — 一次处理多个视频，水印文字、位置、字体、颜色、透明度全部可调
- **自动重命名** — 从 Google Sheets 粘贴两列数据（序号 + 新文件名），自动匹配视频并重命名为 `水印-序号-新文件名.mp4`
- **GPU 加速** — 支持 Apple VideoToolbox 硬件编码，速度比纯 CPU 快 3-5 倍
- **画质控制** — CRF 18~28 可选，CRF 18 几乎无损
- **预设管理** — 保存 3 组参数预设，关闭后重新打开自动恢复上次设置
- **水印预览** — 处理前实时预览水印效果
- **本地运行** — 视频文件不离开你的电脑

---

## 使用要求

- macOS 10.13 或更高版本
- Python 3.9+
- FFmpeg（首次启动可自动安装）

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

---

## 使用方法

**① 导入视频**
- 直接拖拽视频文件到页面，或输入视频文件夹路径
- 指定原视频所在目录（用于确定默认输出位置）

**② 粘贴 Google Sheets 数据**
- 在 Google Sheets 中复制两列：第一列序号/关键词，第二列新文件名
- 粘贴到工具中，自动匹配视频文件

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
