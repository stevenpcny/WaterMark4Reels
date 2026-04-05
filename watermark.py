from __future__ import annotations

import os
import re
import subprocess
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


FONT_DIRS = [
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
    str(Path.home() / "Library/Fonts"),
]

COLOR_MAP = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "yellow": (255, 230, 0),
    "red": (220, 30, 30),
}


def _ffmpeg_bin() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in ["/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]:
        if os.path.isfile(candidate):
            return candidate
    return "ffmpeg"


def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None or any(
        os.path.isfile(p) for p in ["/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]
    )


@lru_cache(maxsize=1)
def check_videotoolbox() -> bool:
    """检测当前 FFmpeg 是否支持 Apple VideoToolbox（GPU 编码）"""
    try:
        result = subprocess.run(
            [_ffmpeg_bin(), "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        return "h264_videotoolbox" in result.stdout
    except Exception:
        return False


# ── Fix #2: 字体扫描结果缓存，进程级别只扫描一次 ──
@lru_cache(maxsize=1)
def get_available_fonts() -> dict:
    """扫描系统字体目录，返回 {显示名: 字体文件路径} 映射（结果缓存）"""
    fonts = {}
    for font_dir in FONT_DIRS:
        p = Path(font_dir)
        if not p.exists():
            continue
        for f in p.iterdir():
            if f.suffix.lower() in {".ttf", ".otf", ".ttc"}:
                fonts[f.stem] = str(f)
    return dict(sorted(fonts.items()))


# ── Fix #6: 视频尺寸获取失败时明确返回错误，不再静默兜底 ──
def _get_video_size(input_path: str) -> tuple:
    """
    用 ffprobe 获取视频宽高，返回 (width, height) 或 (None, error_msg)
    """
    ffmpeg = _ffmpeg_bin()
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    if not os.path.isfile(ffprobe):
        ffprobe = shutil.which("ffprobe") or ffprobe

    cmd = [
        ffprobe,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(input_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        parts = result.stdout.strip().split(",")
        if len(parts) >= 2:
            w, h = int(parts[0]), int(parts[1])
            if w > 0 and h > 0:
                return w, h
        return None, f"无法读取视频尺寸（ffprobe 输出：{result.stdout.strip() or result.stderr.strip()[:100]}）"
    except subprocess.TimeoutExpired:
        return None, "读取视频信息超时"
    except Exception as e:
        return None, str(e)


def _make_watermark_overlay(
    width: int,
    height: int,
    text: str,
    position: str,
    font_size: int,
    opacity: float,
    font_color: str,
    font_path: Optional[str] = None,
    custom_x: Optional[int] = None,
    custom_y: Optional[int] = None,
) -> str:
    """用 Pillow 生成透明背景的水印 PNG，返回临时文件路径"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = None
    if font_path and os.path.isfile(font_path):
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception:
            font = None
    if font is None:
        for fallback in [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]:
            if os.path.isfile(fallback):
                try:
                    font = ImageFont.truetype(fallback, font_size)
                    break
                except Exception:
                    continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    margin = 20

    if position == "自定义" and custom_x is not None and custom_y is not None:
        x, y = custom_x, custom_y
    elif position == "左上":
        x, y = margin, margin
    elif position == "右上":
        x, y = width - tw - margin, margin
    elif position == "左下":
        x, y = margin, height - th - margin
    elif position == "居中":
        x, y = (width - tw) // 2, (height - th) // 2
    else:
        x, y = width - tw - margin, height - th - margin

    rgb = COLOR_MAP.get(font_color, (255, 255, 255))
    alpha = int(opacity * 255)
    shadow_alpha = min(alpha, 180)
    draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, shadow_alpha))
    draw.text((x, y), text, font=font, fill=(*rgb, alpha))

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(tmp.name, "PNG")
    tmp.close()
    return tmp.name


# ── Fix #4: 友好化 FFmpeg 错误信息 ──
def _friendly_error(stderr: str) -> str:
    """将 FFmpeg 的原始 stderr 转换为用户可读的提示"""
    s = stderr.lower()
    if "no such file" in s or "not found" in s:
        return "找不到视频文件，请检查路径是否正确"
    if "invalid data" in s or "moov atom not found" in s:
        return "视频文件已损坏或格式不支持"
    if "permission denied" in s:
        return "没有读取/写入权限，请检查文件夹权限设置"
    if "no space left" in s:
        return "磁盘空间不足，请清理磁盘后重试"
    if "encoder" in s and "not found" in s:
        return "FFmpeg 缺少编码器，请重新安装 FFmpeg"
    if "timeout" in s:
        return "处理超时，视频可能过大"
    # 提取最后一行有意义的错误
    lines = [l.strip() for l in stderr.strip().splitlines() if l.strip()]
    for line in reversed(lines):
        if any(kw in line.lower() for kw in ["error", "invalid", "failed", "cannot"]):
            return line[:120]
    return stderr.strip()[-200:] if stderr.strip() else "未知错误"


def generate_preview(
    input_path: str,
    output_image: str,
    text: str,
    position: str = "右下",
    font_size: int = 24,
    opacity: float = 0.7,
    font_color: str = "white",
    font_path: Optional[str] = None,
    custom_x: Optional[int] = None,
    custom_y: Optional[int] = None,
) -> tuple:
    """截取第一帧并叠加水印，生成预览图"""
    size = _get_video_size(input_path)
    # Fix #6: 尺寸获取失败时返回错误
    if size[0] is None:
        return False, f"无法获取视频信息：{size[1]}"

    w, h = size
    overlay_path = _make_watermark_overlay(
        w, h, text, position, font_size, opacity, font_color, font_path, custom_x, custom_y
    )
    try:
        cmd = [
            _ffmpeg_bin(),
            "-i", str(input_path),
            "-i", overlay_path,
            "-filter_complex", "overlay=0:0",
            "-frames:v", "1",
            "-y",
            str(output_image),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False, _friendly_error(result.stderr)
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "预览生成超时（超过30秒），视频可能过大"
    except Exception as e:
        return False, str(e)
    finally:
        os.unlink(overlay_path)


def add_watermark(
    input_path: str,
    output_path: str,
    text: str,
    position: str = "右下",
    font_size: int = 24,
    opacity: float = 0.7,
    font_color: str = "white",
    font_path: Optional[str] = None,
    quality: int = 18,
    custom_x: Optional[int] = None,
    custom_y: Optional[int] = None,
    encoder: str = "cpu",
) -> tuple:
    """给视频添加文字水印（Pillow 生成水印层，FFmpeg overlay 合成）"""
    size = _get_video_size(input_path)
    if size[0] is None:
        return False, f"无法获取视频信息：{size[1]}"

    w, h = size
    overlay_path = _make_watermark_overlay(
        w, h, text, position, font_size, opacity, font_color, font_path, custom_x, custom_y
    )
    try:
        # 编码器参数
        if encoder == "gpu" and check_videotoolbox():
            # Apple VideoToolbox：用码率控制，GPU 加速
            bitrate = _crf_to_bitrate(quality, w, h)
            codec_args = ["-c:v", "h264_videotoolbox", "-b:v", bitrate]
        else:
            # libx264：CPU 精确质量控制
            codec_args = ["-c:v", "libx264", "-crf", str(quality), "-preset", "slow"]

        cmd = [
            _ffmpeg_bin(),
            "-i", str(input_path),
            "-i", overlay_path,
            "-filter_complex", "overlay=0:0",
            *codec_args,
            "-c:a", "copy",
            "-y",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            return False, _friendly_error(result.stderr)
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "处理超时（超过10分钟），视频可能过大"
    except Exception as e:
        return False, str(e)
    finally:
        os.unlink(overlay_path)


def _crf_to_bitrate(crf: int, width: int, height: int) -> str:
    """将 CRF 值近似转换为 VideoToolbox 码率（基于分辨率）"""
    pixels = width * height
    # 基准：1080x1920 @ CRF18 ≈ 8Mbps
    base = 8_000_000 * (pixels / (1080 * 1920))
    # CRF 每增加 6，码率约减半
    factor = 2 ** ((18 - crf) / 6)
    kbps = int(base * factor / 1000)
    kbps = max(1000, min(kbps, 20_000))
    return f"{kbps}k"


def parse_mapping(text: str) -> dict:
    """解析粘贴的 Google Sheets 数据（Tab 或逗号分隔）"""
    mapping = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if "\t" in line:
            parts = line.split("\t", 1)
        elif "," in line:
            parts = line.split(",", 1)
        else:
            continue
        if len(parts) == 2:
            seq = parts[0].strip()
            name = parts[1].strip()
            if seq and name:
                mapping[seq] = name
    return mapping


def find_video_files(folder: str) -> dict:
    """扫描文件夹中的视频文件，返回 {文件名（无扩展名）: 路径} 映射"""
    video_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    folder_path = Path(folder)
    videos = {}
    if not folder_path.exists():
        return videos
    for f in folder_path.iterdir():
        if f.suffix.lower() in video_extensions:
            videos[f.stem] = f
    return videos


def match_video(seq: str, videos: dict) -> Optional[Path]:
    """
    将表格序号/关键词匹配到视频文件（精确 > 前缀 > 包含）
    """
    if seq in videos:
        return videos[seq]

    seq_lower = seq.lower()

    for stem, path in videos.items():
        stem_lower = stem.lower()
        for sep in ("_", " ", "-", "."):
            if stem_lower.startswith(seq_lower + sep):
                return path

    pattern = re.compile(r"(?<![a-zA-Z0-9])" + re.escape(seq_lower) + r"(?![a-zA-Z0-9])")
    for stem, path in videos.items():
        if pattern.search(stem.lower()):
            return path

    return None


def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name.strip()
