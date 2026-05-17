from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from presets import DEFAULT_SETTINGS


PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "cli-config.json"
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
WATERMARK_KEYS = {
    "text",
    "position",
    "font_size",
    "opacity",
    "font_color",
    "quality",
    "encoder",
    "volume",
    "font_path",
    "custom_x",
    "custom_y",
}


class JsonArgumentParser(argparse.ArgumentParser):
    def print_help(self, file: Any | None = None) -> None:
        raise ValueError("help output is disabled because stdout must be JSON")

    def error(self, message: str) -> None:
        raise ValueError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if status:
            raise ValueError((message or "").strip() or f"argument parsing failed with status {status}")
        raise SystemExit(status)


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def default_config() -> dict[str, Any]:
    return {
        "text": DEFAULT_SETTINGS.get("watermark_text", "@YourAccount"),
        "position": DEFAULT_SETTINGS.get("position", "右下"),
        "font_size": DEFAULT_SETTINGS.get("font_size", 28),
        "opacity": DEFAULT_SETTINGS.get("opacity", 0.7),
        "font_color": DEFAULT_SETTINGS.get("font_color", "white"),
        "quality": 18,
        "encoder": DEFAULT_SETTINGS.get("encoder", "cpu"),
        "volume": DEFAULT_SETTINGS.get("volume", 1.0),
        "font_path": None,
        "custom_x": None,
        "custom_y": None,
    }


def load_config() -> dict[str, Any]:
    config = default_config()
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("cli-config.json must contain a JSON object")
        config.update({key: data.get(key) for key in WATERMARK_KEYS if key in data})
    else:
        save_config(config)
    return config


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_config_value(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in {"null", "none"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def list_video_paths(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise ValueError(f"folder not found: {folder}")
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS),
        key=lambda path: path.name.lower(),
    )


def command_list(args: argparse.Namespace) -> dict[str, Any]:
    from watermark import _ffprobe_bin, _get_video_duration, _get_video_size

    folder = resolve_path(args.folder)
    _ffprobe_bin()
    videos = []
    for path in list_video_paths(folder):
        width = None
        height = None
        size = _get_video_size(str(path))
        if size and size[0] is not None:
            width, height = size
        videos.append(
            {
                "path": str(path),
                "name": path.name,
                "size_mb": round(path.stat().st_size / (1024 * 1024), 1),
                "duration_s": round(float(_get_video_duration(str(path))), 1),
                "width": width,
                "height": height,
            }
        )
    return {"folder": str(folder), "videos": videos}


def extract_audio_segment(video_path: Path, start: int, end: int) -> str:
    from watermark import _ffmpeg_bin, _friendly_error

    if end <= start:
        raise ValueError("--end must be greater than --start")
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    audio_path = tmp.name
    tmp.close()
    cmd = [
        _ffmpeg_bin(),
        "-i",
        str(video_path),
        "-ss",
        str(max(0, start)),
        "-t",
        str(end - start),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-y",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=max(180, end - start + 120))
    if result.returncode != 0:
        try:
            Path(audio_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(_friendly_error(result.stderr))
    return audio_path


def transcribe_with_whisper(video_path: Path, model_size: str, start: int, end: int) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("缺少 faster-whisper 依赖，请重新安装 requirements.txt") from exc

    audio_path = extract_audio_segment(video_path, start, end)
    try:
        model = WhisperModel(model_size, device="cpu")
        segments, _info = model.transcribe(audio_path)
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
    finally:
        try:
            Path(audio_path).unlink(missing_ok=True)
        except OSError:
            pass


def transcribe_with_api(video_path: Path, api_key: str, start: int, end: int) -> str:
    if not api_key:
        raise RuntimeError("OpenAI API engine requires --api-key or OPENAI_API_KEY")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("缺少 openai 依赖，请重新安装 requirements.txt") from exc

    audio_path = extract_audio_segment(video_path, start, end)
    try:
        client = OpenAI(api_key=api_key)
        with open(audio_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file,
                response_format="text",
            )
        if isinstance(transcription, str):
            return transcription.strip()
        return str(getattr(transcription, "text", "") or "").strip()
    finally:
        try:
            Path(audio_path).unlink(missing_ok=True)
        except OSError:
            pass


def command_transcribe(args: argparse.Namespace) -> dict[str, Any]:
    folder = resolve_path(args.folder)
    transcripts = []
    for path in list_video_paths(folder):
        try:
            if args.engine == "api":
                text = transcribe_with_api(
                    path,
                    args.api_key or os.environ.get("OPENAI_API_KEY", ""),
                    int(args.start),
                    int(args.end),
                )
            else:
                text = transcribe_with_whisper(path, args.model, int(args.start), int(args.end))
            transcripts.append({"path": str(path), "name": path.name, "transcript": text, "error": None})
        except Exception as exc:
            log(f"{path.name}: {exc}")
            transcripts.append(
                {"path": str(path), "name": path.name, "transcript": None, "error": str(exc)}
            )
    return {"folder": str(folder), "engine": args.engine, "transcripts": transcripts}


def normalize_watermark_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = load_config()
    if overrides:
        config.update({key: overrides[key] for key in WATERMARK_KEYS if key in overrides})
    for key in ("font_size", "quality"):
        if config.get(key) is not None:
            config[key] = int(config[key])
    for key in ("opacity", "volume"):
        if config.get(key) is not None:
            config[key] = float(config[key])
    for key in ("custom_x", "custom_y"):
        if config.get(key) is not None:
            config[key] = int(config[key])
    return {key: config.get(key) for key in WATERMARK_KEYS}


def make_report_record(item: dict[str, Any], output_file: Path, status: str, error: str | None) -> dict[str, Any]:
    result = "✅ 成功" if status == "ok" else "⏭️ 已跳过（输出已存在）" if status == "skipped" else f"❌ {error or ''}"
    return {
        "status": "success" if status == "ok" else status,
        "result": result,
        "original_file": str(resolve_path(item["video"])),
        "output_file": str(output_file),
        "caption_file": "",
        "row_index": "",
        "seq": "",
        "title": output_file.stem,
        "message": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def write_manual_report(output_dir: Path, records: list[dict[str, Any]]) -> None:
    csv_path = output_dir / "处理结果.csv"
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


def command_process(args: argparse.Namespace) -> dict[str, Any]:
    from processing import verify_output_folder_writable, write_job_report
    from watermark import add_watermark

    mapping_path = resolve_path(args.mapping)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if not isinstance(mapping, dict):
        raise ValueError("mapping.json must contain a JSON object")

    output_dir = resolve_path(mapping["output_dir"])
    ok, writable_error = verify_output_folder_writable(output_dir)
    if not ok:
        raise RuntimeError(f"output_dir is not writable: {writable_error}")

    items = mapping.get("items") or []
    if not isinstance(items, list):
        raise ValueError("items must be a list")

    image_source = mapping.get("image_source")
    if image_source:
        from image_matching import copy_all_images_preserve_names

        copied = copy_all_images_preserve_names(resolve_path(image_source), output_dir / "原图-已匹配")
        log(f"已复制原图: {len(copied)}")

    move_to_trash = bool(mapping.get("move_to_trash", True))
    burn_subtitles = bool(mapping.get("burn_subtitles", False))
    watermark_params = normalize_watermark_config(mapping.get("watermark") or {})
    results = []
    records = []

    for index, item in enumerate(items, 1):
        input_path = resolve_path(item["video"])
        output_file = output_dir / str(item["output_name"])
        log(f"[{index}/{len(items)}] 正在处理: {input_path.name}")

        status = "failed"
        error = None
        if output_file.exists():
            status = "skipped"
        else:
            try:
                success, message = add_watermark(str(input_path), str(output_file), **watermark_params)
                if not success:
                    raise RuntimeError(message or "watermark failed")
                if burn_subtitles:
                    from processing import burn_subtitles_for_output

                    subtitle_ok, subtitle_error = burn_subtitles_for_output(
                        output_file,
                        burn_subtitles=True,
                    )
                    if not subtitle_ok:
                        raise RuntimeError(subtitle_error or "subtitle burn failed")
                if move_to_trash:
                    from send2trash import send2trash

                    send2trash(str(input_path))
                status = "ok"
            except Exception as exc:
                error = str(exc)
                log(f"{input_path.name}: {error}")

        result = {
            "input": input_path.name,
            "output": output_file.name,
            "status": status,
            "error": error,
        }
        results.append(result)
        records.append(make_report_record(item, output_file, status, error))

    try:
        write_job_report(output_dir, records)
    except Exception as exc:
        log(f"write_job_report failed, writing CSV directly: {exc}")
        write_manual_report(output_dir, records)

    return {
        "output_dir": str(output_dir),
        "succeeded": sum(1 for result in results if result["status"] == "ok"),
        "failed": sum(1 for result in results if result["status"] == "failed"),
        "skipped": sum(1 for result in results if result["status"] == "skipped"),
        "results": results,
    }


def command_config(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config()
    if args.set:
        key, value = args.set
        if key not in WATERMARK_KEYS:
            raise ValueError(f"unknown config key: {key}")
        config[key] = parse_config_value(value)
        config = normalize_watermark_config(config)
        save_config(config)
    return config


def command_auth(args: argparse.Namespace) -> dict[str, Any]:
    import gdrive

    if args.revoke:
        gdrive.revoke_auth()
        return {"status": "revoked", "message": "已断开 Google Drive 授权"}

    if gdrive.is_authenticated():
        email = gdrive.get_account_email()
        return {"status": "already_authenticated", "email": email}

    if not gdrive.has_credentials_file():
        raise RuntimeError(
            "找不到 credentials.json。请前往 Google Cloud Console 下载 OAuth 凭据文件，放到项目目录。"
        )

    log("正在打开浏览器完成 Google Drive 授权，请在浏览器中登录并授权...")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(gdrive.CREDS_PATH), gdrive.SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True, prompt="select_account")
        gdrive.TOKEN_PATH.write_text(creds.to_json())
    except Exception as exc:
        raise RuntimeError(f"授权失败: {exc}") from exc

    email = gdrive.get_account_email()
    return {"status": "authenticated", "email": email, "message": "授权成功"}


def command_upload(args: argparse.Namespace) -> dict[str, Any]:
    import gdrive
    from processing import infer_mime_type

    if not gdrive.is_authenticated():
        raise RuntimeError("未登录 Google Drive。请先打开 Streamlit 界面完成一次授权，或手动运行 OAuth 流程。")

    folder_path = resolve_path(args.folder)
    if not folder_path.is_dir():
        raise ValueError(f"文件夹不存在: {folder_path}")

    # 收集要上传的文件（视频）
    files = sorted(
        [p for p in folder_path.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS],
        key=lambda p: p.name.lower(),
    )
    if not files:
        raise ValueError(f"文件夹中没有视频文件: {folder_path}")

    # 确定目标 Drive 文件夹
    folder_id = args.folder_id
    folder_name = args.folder_name or folder_path.name
    if not folder_id:
        log(f"在 Drive 新建文件夹: {folder_name}")
        folder_id = gdrive.create_folder(folder_name)
        if not folder_id:
            raise RuntimeError(f"Drive 文件夹创建失败: {folder_name}")
        gdrive.make_shareable(folder_id)

    link = gdrive.folder_link(folder_id)
    results = []
    for i, file_path in enumerate(files, 1):
        log(f"[{i}/{len(files)}] 上传中: {file_path.name}")
        ok, detail = gdrive.upload_file(
            str(file_path),
            folder_id,
            mime_type=infer_mime_type(file_path),
        )
        results.append({
            "file": file_path.name,
            "status": "ok" if ok else "failed",
            "error": None if ok else detail,
        })

    succeeded = sum(1 for r in results if r["status"] == "ok")
    return {
        "folder_name": folder_name,
        "folder_id": folder_id,
        "folder_link": link,
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Reels watermark tool CLI")
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("folder")
    list_parser.set_defaults(func=command_list)

    transcribe_parser = subparsers.add_parser("transcribe")
    transcribe_parser.add_argument("folder")
    transcribe_parser.add_argument("--engine", choices=["whisper", "api"], default="whisper")
    transcribe_parser.add_argument("--model", default="base")
    transcribe_parser.add_argument("--start", type=int, default=5)
    transcribe_parser.add_argument("--end", type=int, default=20)
    transcribe_parser.add_argument("--api-key", default="")
    transcribe_parser.set_defaults(func=command_transcribe)

    process_parser = subparsers.add_parser("process")
    process_parser.add_argument("mapping")
    process_parser.set_defaults(func=command_process)

    config_parser = subparsers.add_parser("config")
    config_parser.add_argument("--show", action="store_true")
    config_parser.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"))
    config_parser.set_defaults(func=command_config)

    auth_parser = subparsers.add_parser("auth")
    auth_parser.add_argument("--revoke", action="store_true", help="断开 Google Drive 授权")
    auth_parser.set_defaults(func=command_auth)

    upload_parser = subparsers.add_parser("upload")
    upload_parser.add_argument("folder", help="本地视频文件夹路径")
    upload_parser.add_argument("--folder-name", default="", help="Drive 文件夹名（默认用本地文件夹名）")
    upload_parser.add_argument("--folder-id", default="", help="已有 Drive 文件夹 ID（不传则新建）")
    upload_parser.set_defaults(func=command_upload)

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        payload = args.func(args)
        emit(payload)
        return 0
    except Exception as exc:
        emit({"error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
