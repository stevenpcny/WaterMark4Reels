from __future__ import annotations

import csv
import json
import mimetypes
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


JOB_REPORT_NAME = ".reels-watermark-job.json"
CSV_REPORT_NAME = "处理结果.csv"


def verify_output_folder_writable(output_dir: Path) -> tuple[bool, str]:
    """
    Check writability using a normal visible temp file.

    Some folders can reject dotfiles like `.write_test` while still allowing
    regular output files, so this mirrors the actual export path more closely.
    """
    output_dir = Path(output_dir)
    test_path = None
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix="reels-write-test-",
            suffix=".tmp",
            dir=output_dir,
            delete=False,
            encoding="utf-8",
        ) as test_file:
            test_file.write("ok")
            test_path = Path(test_file.name)
        test_path.unlink()
        return True, ""
    except Exception as e:
        if test_path and test_path.exists():
            try:
                test_path.unlink()
            except OSError:
                pass
        return False, str(e)


def build_process_items(
    mapping_entries: list[dict],
    matched_files_for_row: Callable[[int, str], list[Path]],
    output_name_for: Callable[[str, str, Path, int, int], str],
    review_id_for: Callable[[int, Path, str], str],
    review_statuses: dict,
    out_path: Path,
    *,
    review_only_confirmed: bool = True,
) -> list[dict]:
    """Build the queue of videos that are allowed to be processed."""
    items = []
    for row_index, row in enumerate(mapping_entries):
        seq = row["seq"]
        new_name = row["name"]
        matched_files = matched_files_for_row(row_index, seq)
        if not matched_files:
            continue
        for i, vf in enumerate(matched_files, 1):
            output_name = output_name_for(seq, new_name, vf, len(matched_files), i)
            review_id = review_id_for(row_index, vf, output_name)
            review_status = review_statuses.get(review_id)
            if review_status == "problem":
                continue
            if review_only_confirmed and review_status != "confirmed":
                continue
            items.append({
                "row_index": row_index,
                "row": row,
                "video_file": vf,
                "output_file": Path(out_path) / output_name,
                "review_id": review_id,
            })
    return items


def caption_path_for(output_file: Path) -> Path:
    return Path(output_file).with_suffix(".txt")


def process_item_complete(item: dict, create_caption_files: bool = False) -> bool:
    output_file = Path(item["output_file"])
    if not output_file.exists():
        return False
    caption = item.get("row", {}).get("caption", "").strip()
    if create_caption_files and caption:
        return caption_path_for(output_file).exists()
    return True


def split_existing_process_items(
    items: Iterable[dict],
    create_caption_files: bool = False,
) -> tuple[list[dict], list[dict]]:
    pending, skipped = [], []
    for item in items:
        if process_item_complete(item, create_caption_files):
            skipped.append(item)
        else:
            pending.append(item)
    return pending, skipped


def detect_existing_outputs(items: Iterable[dict], create_caption_files: bool = False) -> list[str]:
    existing = []
    seen = set()
    for item in items:
        output_file = Path(item["output_file"])
        candidates = [output_file]
        caption = item.get("row", {}).get("caption", "").strip()
        if create_caption_files and caption:
            candidates.append(caption_path_for(output_file))
        for path in candidates:
            if path.exists() and path.name not in seen:
                existing.append(path.name)
                seen.add(path.name)
    return existing


def write_caption_file(output_file: Path, caption: str) -> tuple[bool, str]:
    caption = (caption or "").strip()
    if not caption:
        return True, ""
    caption_file = caption_path_for(output_file)
    try:
        caption_file.write_text(caption + "\n", encoding="utf-8")
        return True, caption_file.name
    except Exception as e:
        return False, f"写入失败：{e}"


def burn_subtitles_for_output(
    output_file: Path,
    *,
    burn_subtitles: bool = False,
    model_size: str = "base",
) -> tuple[bool, str]:
    if not burn_subtitles:
        return True, ""
    try:
        from subtitle import add_subtitles, transcribe_words

        words = transcribe_words(str(output_file), model_size=model_size)
        add_subtitles(str(output_file), words, str(output_file))
        return True, ""
    except Exception as e:
        return False, str(e)


def make_result_row(
    item: dict,
    *,
    success: bool,
    error: str = "",
    caption_file_name: str = "",
    has_captions: bool = False,
    skipped: bool = False,
) -> dict:
    result_row = {
        "原文件": Path(item["video_file"]).name,
        "输出文件": Path(item["output_file"]).name,
    }
    if has_captions:
        result_row["英文文案文件"] = caption_file_name or "—"
    if skipped:
        result_row["结果"] = "⏭️ 已跳过（输出已存在）"
    else:
        result_row["结果"] = "✅ 成功" if success else f"❌ {error}"
    return result_row


def result_to_job_record(item: dict, result_row: dict) -> dict:
    result_text = result_row.get("结果", "")
    status = "success" if "✅" in result_text else "skipped" if "⏭️" in result_text else "failed"
    caption_name = result_row.get("英文文案文件", "")
    output_file = Path(item["output_file"])
    caption_file = str(caption_path_for(output_file)) if isinstance(caption_name, str) and caption_name.endswith(".txt") else ""
    return {
        "status": status,
        "result": result_text,
        "original_file": str(item["video_file"]),
        "output_file": str(output_file),
        "caption_file": caption_file,
        "row_index": item.get("row_index"),
        "seq": item.get("row", {}).get("seq", ""),
        "title": item.get("row", {}).get("name", ""),
        "message": result_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def write_job_report(output_dir: Path, records: list[dict]) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    job_path = output_dir / JOB_REPORT_NAME
    csv_path = output_dir / CSV_REPORT_NAME

    job_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
    }
    job_path.write_text(json.dumps(job_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = [
        "status",
        "result",
        "original_file",
        "output_file",
        "caption_file",
        "row_index",
        "seq",
        "title",
        "message",
        "timestamp",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key, "") for key in fieldnames})

    return job_path, csv_path


def successful_upload_file_names(results: Iterable[dict]) -> list[str]:
    names = []
    seen = set()
    for result in results:
        if "✅" not in result.get("结果", ""):
            continue
        for key in ("输出文件", "英文文案文件", "文案文件"):
            value = result.get(key, "")
            if isinstance(value, str) and value and value != "—" and not value.startswith("写入失败"):
                if value not in seen:
                    names.append(value)
                    seen.add(value)
    return names


def infer_mime_type(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".txt":
        return "text/plain"
    video_mimes = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
    }
    if suffix in video_mimes:
        return video_mimes[suffix]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"
