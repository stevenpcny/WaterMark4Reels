from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Optional

from watermark import (
    match_all_videos as _match_all_videos,
    parse_mapping_rows as _parse_mapping_rows,
    sanitize_filename,
    text_similarity,
)


def parse_mapping_rows(text: str) -> list[dict]:
    """Parse pasted Google Sheets rows into seq/name/caption dictionaries."""
    return _parse_mapping_rows(text)


def match_all_videos(seq: str, videos: Mapping[str, Path]) -> list[Path]:
    """Return all video files matching a sequence or keyword."""
    return _match_all_videos(seq, videos)


def _file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0


def sort_video_files(videos: Mapping[str, Path] | Iterable[Path], mode: str = "文件名 A-Z") -> list[Path]:
    """Sort videos the same way the UI offers for order-based matching."""
    paths = list(videos.values()) if isinstance(videos, Mapping) else list(videos)
    if mode == "修改时间：旧到新":
        return sorted(paths, key=lambda p: (_file_mtime(Path(p)), Path(p).name.lower()))
    if mode == "修改时间：新到旧":
        return sorted(paths, key=lambda p: (_file_mtime(Path(p)), Path(p).name.lower()), reverse=True)
    return sorted(paths, key=lambda p: Path(p).name.lower())


def mapping_entries_for_mode(
    rows: list[dict],
    *,
    match_by_voice: bool = False,
    match_by_order: bool = False,
) -> list[dict]:
    """Preserve pasted row order for voice/order matching; otherwise sort by seq."""
    if match_by_voice or match_by_order:
        return rows
    return [
        {"seq": row["seq"], "name": row["name"], "caption": row.get("caption", "")}
        for row in sorted(rows, key=lambda row: row["seq"])
    ]


def build_output_stem(seq: str, chinese_title: str, naming_rule: str, max_bytes: int = 160) -> str:
    title = (chinese_title or "").strip() or seq
    if naming_rule == "序号-中文标题":
        raw = f"{seq}-{title}"
    elif naming_rule == "中文标题":
        raw = title
    elif naming_rule == "中文标题-序号":
        raw = f"{title}-{seq}"
    else:
        raw = f"水印-{seq}-{title}"
    return sanitize_filename(raw, max_bytes=max_bytes)


def build_output_name(
    seq: str,
    chinese_title: str,
    video_file: Path,
    matched_count: int,
    match_index: int,
    naming_rule: str,
    max_bytes: int = 160,
) -> str:
    output_stem = build_output_stem(seq, chinese_title, naming_rule, max_bytes=max_bytes)
    if matched_count == 1:
        return f"{output_stem}{Path(video_file).suffix}"
    return f"{output_stem}-{match_index}{Path(video_file).suffix}"


def review_id_for(row_index: int, video_file: Path, output_name: str) -> str:
    return f"{row_index}:{Path(video_file).name}:{output_name}"


def matched_files_for_row(
    row_index: int,
    seq: str,
    videos: Mapping[str, Path],
    ordered_video_files: list[Path],
    *,
    match_by_voice: bool = False,
    match_by_order: bool = False,
    voice_assignments: Optional[Mapping[int, int]] = None,
) -> list[Path]:
    if match_by_voice:
        video_index = (voice_assignments or {}).get(row_index)
        if video_index is None or video_index >= len(ordered_video_files):
            return []
        return [ordered_video_files[video_index]]
    if match_by_order:
        return [ordered_video_files[row_index]] if row_index < len(ordered_video_files) else []
    return match_all_videos(seq, videos)


def assign_voice_matches(
    transcripts: Mapping[int, str],
    rows: list[dict],
    threshold: float,
) -> tuple[dict[int, int], dict[int, float]]:
    """Greedily assign videos to rows by transcript/caption similarity."""
    candidate_scores = []
    for video_index, transcript in transcripts.items():
        for row_index, row in enumerate(rows):
            target_text = row.get("caption", "").strip()
            if not target_text:
                continue
            score = text_similarity(transcript, target_text)
            candidate_scores.append((score, video_index, row_index))

    assigned_videos = set()
    assigned_rows = set()
    assignments: dict[int, int] = {}
    scores: dict[int, float] = {}
    for score, video_index, row_index in sorted(candidate_scores, reverse=True):
        if score < threshold:
            continue
        if video_index in assigned_videos or row_index in assigned_rows:
            continue
        assigned_videos.add(video_index)
        assigned_rows.add(row_index)
        assignments[row_index] = video_index
        scores[row_index] = score

    return assignments, scores
