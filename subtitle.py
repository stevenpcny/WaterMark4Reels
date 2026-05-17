from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from subtitle_styles import HORMOZI
from watermark import (
    _ffmpeg_bin,
    _ffprobe_bin,
    _friendly_error,
    _local_whisper_model,
    _transcription_timeout,
)


def _probe(video_path: str) -> tuple[int, int, float]:
    result = subprocess.run(
        [
            _ffprobe_bin(),
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "default=nw=1:nk=1",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    lines = result.stdout.strip().splitlines()
    width = int(lines[0])
    height = int(lines[1])
    duration = 0.0
    if len(lines) > 2 and lines[2] and lines[2] != "N/A":
        duration = float(lines[2])
    return width, height, duration


def _group_words(
    words: list[dict],
    font: ImageFont.FreeTypeFont,
    max_width_px: int,
    max_words: int,
) -> list[list[dict]]:
    groups, cur = [], []
    for word in words:
        candidate = cur + [word]
        text = " ".join(x["word"] for x in candidate)
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        if len(candidate) > max_words or width > max_width_px:
            if cur:
                groups.append(cur)
            cur = [word]
        else:
            cur = candidate
    if cur:
        groups.append(cur)
    return groups


def _render_group_png(
    group: list[dict],
    highlight_idx: int,
    video_w: int,
    png_h: int,
    font: ImageFont.FreeTypeFont,
    style: dict,
) -> Image.Image:
    text = " ".join(w["word"] for w in group)
    bbox = font.getbbox(text)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    img = Image.new("RGBA", (video_w, png_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad_x = int(video_w * style["highlight_pad_x_ratio"])
    pad_y = int(video_w * style["highlight_pad_y_ratio"])
    radius = int(video_w * style["highlight_corner_ratio"])
    stroke_w = max(1, int(video_w * style["stroke_width_ratio"]))

    x_start = (video_w - text_w) // 2 - bbox[0]
    y = (png_h - text_h) // 2 - bbox[1]

    space_bbox = font.getbbox(" ")
    space_w = space_bbox[2] - space_bbox[0]
    x = x_start
    for i, word_info in enumerate(group):
        word = word_info["word"]
        word_bbox = font.getbbox(word)
        word_w = word_bbox[2] - word_bbox[0]

        if i == highlight_idx:
            box = (
                x + word_bbox[0] - pad_x,
                y + word_bbox[1] - pad_y,
                x + word_bbox[2] + pad_x,
                y + word_bbox[3] + pad_y,
            )
            draw.rounded_rectangle(box, radius=radius, fill=style["highlight_fill"])

        draw.text(
            (x, y),
            word,
            font=font,
            fill=style["fill"],
            stroke_width=stroke_w,
            stroke_fill=style["stroke_fill"],
        )
        x += word_w + space_w

    return img


def transcribe_words(video_path, model_size="base") -> list[dict]:
    audio_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = tmp.name

        cmd = [
            _ffmpeg_bin(),
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-y",
            audio_path,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_transcription_timeout(0),
        )
        if result.returncode != 0:
            raise RuntimeError(_friendly_error(result.stderr))

        model = _local_whisper_model((model_size or "base").strip().lower())
        segments, _info = model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
        )

        words = []
        for segment in segments:
            for word in segment.words or []:
                text = (word.word or "").strip()
                if not text:
                    continue
                words.append({
                    "word": text,
                    "start": float(word.start),
                    "end": float(word.end),
                })
        return words
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
            except OSError:
                pass


def add_subtitles(video_path, words, output_path, style=HORMOZI) -> None:
    output = Path(output_path)
    source = Path(video_path)

    clean_words = [
        {
            "word": str(word.get("word", "")).strip(),
            "start": float(word.get("start", 0.0)),
            "end": float(word.get("end", 0.0)),
        }
        for word in words
        if str(word.get("word", "")).strip()
    ]
    if not clean_words:
        if source.resolve() != output.resolve():
            shutil.copy2(source, output)
        return

    tmpdir = Path(tempfile.mkdtemp(prefix="subtitles_"))
    fd, temp_output = tempfile.mkstemp(
        prefix=f"{output.stem}.subtitles.",
        suffix=output.suffix or ".mp4",
        dir=str(output.parent),
    )
    os.close(fd)
    os.unlink(temp_output)

    try:
        video_w, video_h, _duration = _probe(str(source))
        font_size = int(video_h * style["font_size_ratio"])
        font = ImageFont.truetype(style["font_path"], font_size)
        max_width_px = int(video_w * style["max_width_ratio"])
        groups = _group_words(
            clean_words,
            font,
            max_width_px,
            style["max_words_per_group"],
        )

        text_bbox = font.getbbox("ApgyM")
        text_h = text_bbox[3] - text_bbox[1]
        pad_y = int(video_w * style["highlight_pad_y_ratio"])
        png_h = text_h + 2 * pad_y + 40

        flat = [
            (group_index, word_index, word)
            for group_index, group in enumerate(groups)
            for word_index, word in enumerate(group)
        ]
        overlays = []
        for i, (group_index, word_index, word) in enumerate(flat):
            start = word["start"]
            end = flat[i + 1][2]["start"] if i + 1 < len(flat) else word["end"]
            if end <= start:
                end = start + 0.05
            img = _render_group_png(
                groups[group_index],
                word_index,
                video_w,
                png_h,
                font,
                style,
            )
            png_path = tmpdir / f"g{group_index:03d}_w{word_index:02d}.png"
            img.save(png_path)
            overlays.append((png_path, start, end))

        y_pos = int(video_h * style["position_y_ratio"]) - png_h // 2

        cmd = [_ffmpeg_bin(), "-y", "-i", str(source)]
        for png_path, _start, _end in overlays:
            cmd.extend(["-i", str(png_path)])

        filters = []
        prev = "[0:v]"
        for i, (_png_path, start, end) in enumerate(overlays):
            input_index = i + 1
            out_label = f"[v{i}]" if i < len(overlays) - 1 else "[vout]"
            filters.append(
                f"{prev}[{input_index}:v]overlay=0:{y_pos}:"
                f"enable='between(t,{start:.3f},{end:.3f})'{out_label}"
            )
            prev = out_label

        cmd.extend([
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-preset",
            "medium",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            temp_output,
        ])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            raise RuntimeError(_friendly_error(result.stderr))
        os.replace(temp_output, output)
    finally:
        if os.path.exists(temp_output):
            try:
                os.unlink(temp_output)
            except OSError:
                pass
        shutil.rmtree(tmpdir, ignore_errors=True)
