from __future__ import annotations

import os
import re
import csv
import io
import subprocess
import shutil
import sys
import tempfile
from difflib import SequenceMatcher
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
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    base_dirs = []
    if getattr(sys, "frozen", False):
        base_dirs.append(Path(sys.executable).resolve().parent)
    base_dirs.extend([Path(__file__).resolve().parent, Path.cwd()])
    for base in base_dirs:
        for candidate in [
            base / exe_name,
            base / "bin" / exe_name,
            base / "ffmpeg" / exe_name,
            base / "ffmpeg" / "bin" / exe_name,
        ]:
            if candidate.is_file():
                return str(candidate)
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in ["/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]:
        if os.path.isfile(candidate):
            return candidate
    return "ffmpeg"


def _ffprobe_bin() -> str:
    ffmpeg = _ffmpeg_bin()
    if os.path.basename(ffmpeg).lower() in {"ffmpeg", "ffmpeg.exe"}:
        ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
        candidate = Path(ffmpeg).with_name(ffprobe_name)
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("ffprobe")
    if found:
        return found
    return "ffprobe.exe" if os.name == "nt" else "ffprobe"


def check_ffmpeg() -> bool:
    ffmpeg = _ffmpeg_bin()
    return shutil.which(ffmpeg) is not None or os.path.isfile(ffmpeg)


@lru_cache(maxsize=1)
def check_videotoolbox() -> bool:
    """检测当前 FFmpeg 是否支持 Apple VideoToolbox（GPU 编码）"""
    if sys.platform != "darwin":
        return False
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
    cmd = [
        _ffprobe_bin(),
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


def _get_video_duration(input_path: str) -> float:
    cmd = [
        _ffprobe_bin(),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return max(0.1, float(result.stdout.strip()))
    except Exception:
        return 10.0


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


def _transcription_timeout(duration: int) -> int:
    """Timeout for audio extraction; full-video jobs need a wider window."""
    return max(1800, duration + 120) if duration <= 0 else max(180, duration + 120)


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
    volume: float = 1.0,
) -> tuple:
    """给视频添加文字水印。"""
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
            bitrate = _crf_to_bitrate(quality, w, h)
            codec_args = ["-c:v", "h264_videotoolbox", "-b:v", bitrate]
        else:
            codec_args = ["-c:v", "libx264", "-crf", str(quality), "-preset", "slow"]

        # 音量滤镜（volume=1.0 表示原始音量，不做任何处理）
        if abs(volume - 1.0) > 0.01:
            audio_args = ["-af", f"volume={volume:.2f}"]
        else:
            audio_args = ["-c:a", "copy"]

        filter_complex = "[0:v][1:v]overlay=0:0[v]"
        input_args = ["-i", str(input_path), "-i", overlay_path]
        map_args = ["-map", "[v]", "-map", "0:a?"]

        cmd = [
            _ffmpeg_bin(),
            *input_args,
            "-filter_complex", filter_complex,
            *map_args,
            *codec_args,
            *audio_args,
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


def generate_audio_preview(
    input_path: str,
    output_audio: str,
    volume: float = 1.0,
    duration: int = 8,
) -> tuple:
    """提取视频前 N 秒音频并调整音量，用于试听。返回 (True, "") 或 (False, 错误信息)"""
    try:
        audio_filter = f"volume={volume:.2f}"
        cmd = [
            _ffmpeg_bin(),
            "-i", str(input_path),
            "-t", str(duration),
            "-af", audio_filter,
            "-vn",
            "-ar", "44100",
            "-ac", "2",
            "-y",
            str(output_audio),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False, _friendly_error(result.stderr)
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "试听生成超时"
    except Exception as e:
        return False, str(e)


def transcribe_video_openai(
    input_path: str,
    api_key: str,
    start: int = 0,
    duration: int = 90,
    model: str = "gpt-4o-mini-transcribe",
) -> tuple:
    """提取视频音频并用 OpenAI 转文字，返回 (True, text) 或 (False, error)。"""
    api_key = (api_key or "").strip()
    if not api_key:
        return False, "请先填写 OpenAI API Key"

    try:
        from openai import OpenAI
    except ImportError:
        return False, "缺少 openai 依赖，请重新安装 requirements.txt"

    audio_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = tmp.name

        start = max(0, int(start or 0))
        duration = max(0, int(duration or 0))
        cmd = [_ffmpeg_bin()]
        if start > 0:
            cmd.extend(["-ss", str(start)])
        cmd.extend([
            "-i", str(input_path),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
        ])
        if duration and duration > 0:
            cmd.extend(["-t", str(duration)])
        cmd.extend(["-y", audio_path])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_transcription_timeout(duration))
        if result.returncode != 0:
            return False, _friendly_error(result.stderr)

        client = OpenAI(api_key=api_key)
        with open(audio_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                response_format="text",
                language="en",
            )

        text = transcription if isinstance(transcription, str) else getattr(transcription, "text", "")
        return True, (text or "").strip()
    except subprocess.TimeoutExpired:
        return False, "音频提取超时"
    except Exception as e:
        return False, str(e)
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
            except OSError:
                pass


@lru_cache(maxsize=2)
def _local_whisper_model(model_size: str):
    from faster_whisper import WhisperModel

    model_source = _bundled_whisper_model_path(model_size) or model_size
    return WhisperModel(model_source, device="cpu", compute_type="int8")


def _bundled_whisper_model_path(model_size: str) -> str:
    model_dir_name = f"faster-whisper-{model_size}"
    base_dirs = []
    if getattr(sys, "frozen", False):
        base_dirs.append(Path(sys.executable).resolve().parent)
    base_dirs.extend([Path(__file__).resolve().parent, Path.cwd()])

    for base in base_dirs:
        candidate = base / "models" / model_dir_name
        if (candidate / "model.bin").is_file() and (candidate / "config.json").is_file():
            return str(candidate)
    return ""


def transcribe_video_local_whisper(
    input_path: str,
    start: int = 0,
    duration: int = 90,
    model_size: str = "base",
) -> tuple:
    """提取视频音频并用本地 Whisper 转英文，返回 (True, text) 或 (False, error)。"""
    model_size = (model_size or "base").strip().lower()
    if model_size not in {"base", "small"}:
        return False, "本地 Whisper 模型只能选择 base 或 small"

    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False, "缺少 faster-whisper 依赖，请重新安装 requirements.txt"

    audio_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = tmp.name

        start = max(0, int(start or 0))
        duration = max(0, int(duration or 0))
        cmd = [_ffmpeg_bin()]
        if start > 0:
            cmd.extend(["-ss", str(start)])
        cmd.extend([
            "-i", str(input_path),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
        ])
        if duration and duration > 0:
            cmd.extend(["-t", str(duration)])
        cmd.extend(["-y", audio_path])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_transcription_timeout(duration))
        if result.returncode != 0:
            return False, _friendly_error(result.stderr)

        model = _local_whisper_model(model_size)
        segments, _info = model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        return True, text.strip()
    except subprocess.TimeoutExpired:
        return False, "音频提取超时"
    except Exception as e:
        return False, str(e)
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
            except OSError:
                pass


def _normalize_match_text(text: str) -> str:
    """保留英文和数字，去掉空格标点，便于比较口播和英文文案。"""
    return "".join(ch.lower() for ch in (text or "") if ch.isalnum())


def _word_tokens(text: str) -> list:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _char_ngrams(text: str, size: int = 2) -> set:
    if len(text) <= size:
        return {text} if text else set()
    return {text[i:i + size] for i in range(len(text) - size + 1)}


def text_similarity(left: str, right: str) -> float:
    """返回 0~1 的文本相似度，用于英文语音识别结果和英文文案匹配。"""
    a = _normalize_match_text(left)
    b = _normalize_match_text(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.98

    sequence_score = SequenceMatcher(None, a, b).ratio()
    a_grams = _char_ngrams(a)
    b_grams = _char_ngrams(b)
    gram_score = len(a_grams & b_grams) / len(a_grams | b_grams) if a_grams and b_grams else 0.0

    left_words = _word_tokens(left)
    right_words = _word_tokens(right)
    word_score = 0.0
    if left_words and right_words:
        left_set = set(left_words)
        right_set = set(right_words)
        # 视频只识别中间片段时，用 overlap coefficient 比完整文本 Jaccard 更宽容。
        word_score = len(left_set & right_set) / min(len(left_set), len(right_set))

    return max(sequence_score, gram_score, word_score)


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


def _looks_like_sequence(value: str) -> bool:
    value = (value or "").strip()
    return bool(re.fullmatch(r"\d+(?:[.\-]\d+)*[A-Za-z]?", value))


def _looks_like_header(parts: list) -> bool:
    if parts and _looks_like_sequence(parts[0]):
        return False
    head = " ".join((part or "").strip().lower() for part in parts[:3])
    return any(word in head for word in ("序号", "编号", "中文", "英文", "chinese", "english"))


def parse_mapping_rows(text: str) -> list:
    """解析粘贴的 Google Sheets 数据，支持：序号 + 中文标题 + 英文文案。"""
    rows = []
    raw_text = (text or "").strip()
    if not raw_text:
        return rows

    delimiter = "\t" if "\t" in raw_text else ","
    try:
        parsed_rows = list(csv.reader(io.StringIO(raw_text), delimiter=delimiter))
    except csv.Error:
        parsed_rows = [line.split(delimiter) for line in raw_text.splitlines()]

    for raw_parts in parsed_rows:
        parts = [str(part).strip() for part in raw_parts]
        parts = [part for part in parts if part]
        if not parts:
            continue
        if _looks_like_header(parts):
            continue

        first = parts[0]
        starts_new_row = _looks_like_sequence(first) or len(parts) >= 3

        if starts_new_row and len(parts) >= 2:
            seq = first
            name = parts[1]
            caption = delimiter.join(parts[2:]).strip() if len(parts) >= 3 else ""
            if seq and name:
                rows.append({"seq": seq, "name": name, "caption": caption})
            continue

        # 容错：英文文案单元格里的换行如果没有被表格软件正确加引号，
        # 会被拆成新行。非序号开头的行并回上一条英文文案。
        if rows:
            continuation = delimiter.join(parts).strip()
            if continuation:
                old_caption = rows[-1].get("caption", "")
                rows[-1]["caption"] = (old_caption + "\n" + continuation).strip()

    return rows


def parse_mapping(text: str) -> dict:
    """解析粘贴的 Google Sheets 数据（Tab 或逗号分隔）"""
    mapping = {}
    for row in parse_mapping_rows(text):
        mapping[row["seq"]] = row["name"]
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
    将表格序号/关键词匹配到视频文件（精确 > 前缀 > 包含），只返回第一个
    """
    results = match_all_videos(seq, videos)
    return results[0] if results else None


def match_all_videos(seq: str, videos: dict) -> list:
    """
    返回所有匹配给定序号/关键词的视频列表（按文件名排序）。
    优先级：精确匹配 > 前缀匹配 > 包含匹配；同级多个全部返回。
    """
    seq_lower = seq.lower()

    # 1. 精确匹配
    exact = [path for stem, path in videos.items() if stem.lower() == seq_lower]
    if exact:
        return sorted(exact, key=lambda p: p.stem)

    # 2. 前缀匹配（stem 以 seq + 分隔符开头）
    prefix_matches = []
    for stem, path in videos.items():
        stem_lower = stem.lower()
        for sep in ("_", " ", "-", "."):
            if stem_lower.startswith(seq_lower + sep):
                prefix_matches.append(path)
                break
    if prefix_matches:
        return sorted(prefix_matches, key=lambda p: p.stem)

    # 3. 包含匹配（seq 作为完整词出现在 stem 中）
    pattern = re.compile(r"(?<![a-zA-Z0-9])" + re.escape(seq_lower) + r"(?![a-zA-Z0-9])")
    contains_matches = [path for stem, path in videos.items() if pattern.search(stem.lower())]
    return sorted(contains_matches, key=lambda p: p.stem)


def sanitize_filename(name: str, max_bytes: int = 160) -> str:
    """清理文件名中的非法字符，并限制长度，兼顾 macOS 和 Windows。"""
    for ch in '<>:"/\\|?*\n\r\t':
        name = name.replace(ch, "_")
    name = re.sub(r"\s+", " ", name).strip(" ._")

    # 按字节截断（中文字符占 3 字节），保留完整字符不截断半个
    encoded = name.encode("utf-8")
    if len(encoded) > max_bytes:
        truncated = encoded[:max_bytes]
        # 确保截断点是合法 UTF-8 字符边界
        name = truncated.decode("utf-8", errors="ignore")
    name = name.strip(" ._")

    reserved = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    if not name:
        return "未命名"
    if name.upper() in reserved:
        return f"{name}_"
    return name
