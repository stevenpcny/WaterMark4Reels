from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
import imagehash


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".tif", ".tiff"}
FRAME_TIMESTAMPS = [0.5, 1.5, 3.0]  # 中点会动态追加


def find_image_files(folder: str | Path) -> list[Path]:
    if not folder:
        return []
    p = Path(folder)
    if not p.is_dir():
        return []
    return sorted(
        [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
    )


def _hash_pair(im: Image.Image) -> tuple[str, str]:
    return str(imagehash.phash(im)), str(imagehash.dhash(im))


def hash_image(path: Path) -> tuple[str, str] | None:
    try:
        with Image.open(path) as im:
            return _hash_pair(im.convert("RGB"))
    except Exception:
        return None


def probe_duration(video_path: Path) -> float | None:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10, text=True, check=True)
        return float(r.stdout.strip())
    except Exception:
        return None


def hash_video_frames(video_path: Path, work_dir: Path) -> list[tuple[str, str]]:
    """抽多帧 → 算 pHash + dHash。失败的帧跳过。"""
    work_dir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(video_path)
    timestamps = list(FRAME_TIMESTAMPS)
    if duration:
        mid = duration / 2.0
        if mid not in timestamps and mid > 0.5:
            timestamps.append(mid)
        timestamps = [t for t in timestamps if t < max(0.3, duration - 0.2)]
        if not timestamps:
            timestamps = [max(0.1, duration / 2.0)]

    hashes = []
    for i, t in enumerate(timestamps):
        frame_path = work_dir / f"{video_path.stem}__f{i}.jpg"
        cmd = [
            "ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video_path),
            "-vframes", "1", "-q:v", "3", str(frame_path),
            "-loglevel", "error",
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=30, check=True)
            if frame_path.exists() and frame_path.stat().st_size > 0:
                h = hash_image(frame_path)
                if h:
                    hashes.append(h)
        except Exception:
            continue
        finally:
            try:
                frame_path.unlink(missing_ok=True)
            except Exception:
                pass
    return hashes


def _hamming(a: str, b: str) -> int:
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


def best_distance(
    video_hashes: list[tuple[str, str]],
    image_hash: tuple[str, str],
) -> int:
    if not video_hashes or not image_hash:
        return 999
    img_p, img_d = image_hash
    best = 999
    for ph, dh in video_hashes:
        best = min(best, _hamming(ph, img_p), _hamming(dh, img_d))
    return best


def assign_videos_to_images(
    video_hashes: dict[str, list[tuple[str, str]]],
    image_hashes: dict[str, tuple[str, str]],
    auto_threshold: int = 18,
    review_threshold: int = 24,
) -> dict:
    """
    贪心全局分配：所有 (视频, 图片) 配对按距离升序，依次分配。
    Returns: {
        "assignments": {video_id: {"image": str|None, "distance": int|None, "status": "auto"|"review"|"unmatched"}},
        "conflicts":   [{"image": str, "candidates": [{"video": vid, "distance": int}, ...]}],
    }
    """
    pairs = []
    for vid, vhashes in video_hashes.items():
        for img, ihash in image_hashes.items():
            d = best_distance(vhashes, ihash)
            pairs.append((d, vid, img))
    pairs.sort()

    wanted_by: dict[str, list[tuple[str, int]]] = {}
    for d, vid, img in pairs:
        if d <= review_threshold:
            wanted_by.setdefault(img, []).append((vid, d))

    assigned: dict[str, tuple[str, int]] = {}
    used_images: set[str] = set()
    used_videos: set[str] = set()
    for d, vid, img in pairs:
        if vid in used_videos or img in used_images:
            continue
        if d > review_threshold:
            continue
        assigned[vid] = (img, d)
        used_videos.add(vid)
        used_images.add(img)

    assignments = {}
    for vid in video_hashes:
        if vid in assigned:
            img, d = assigned[vid]
            assignments[vid] = {
                "image": img,
                "distance": d,
                "status": "auto" if d <= auto_threshold else "review",
            }
        else:
            assignments[vid] = {"image": None, "distance": None, "status": "unmatched"}

    conflicts = []
    for img, cands in wanted_by.items():
        cands_sorted = sorted(cands, key=lambda x: x[1])
        if len(cands_sorted) > 1:
            conflicts.append({
                "image": img,
                "candidates": [{"video": v, "distance": d} for v, d in cands_sorted],
            })
    return {"assignments": assignments, "conflicts": conflicts}


def copy_image_with_new_name(
    src_image: Path,
    dest_folder: Path,
    new_stem: str,
) -> Path:
    """复制图片到目标文件夹，保留原扩展名，文件名用新 stem。"""
    dest_folder.mkdir(parents=True, exist_ok=True)
    dest = dest_folder / f"{new_stem}{src_image.suffix.lower()}"
    shutil.copy2(src_image, dest)
    return dest


def copy_all_images_preserve_names(
    src_folder: Path,
    dest_folder: Path,
) -> dict[str, Path]:
    """批量复制原文件夹中所有图片到目标文件夹，保留原名。
    返回 {原始绝对路径: 目标路径}。已存在的目标文件会被覆盖以确保是最新拷贝。
    """
    dest_folder.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, Path] = {}
    for src in find_image_files(src_folder):
        dest = dest_folder / src.name
        shutil.copy2(src, dest)
        mapping[str(src)] = dest
    return mapping


def rename_in_folder(
    folder_file: Path,
    new_stem: str,
) -> Path:
    """把目标文件夹里已经存在的文件改名为 new_stem + 原扩展名。"""
    new_path = folder_file.with_name(f"{new_stem}{folder_file.suffix.lower()}")
    if new_path == folder_file:
        return folder_file
    folder_file.rename(new_path)
    return new_path


def make_frame_workdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="watermark_frames_"))
