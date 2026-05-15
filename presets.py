from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _settings_dir() -> Path:
    if getattr(sys, "frozen", False) and os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "ReelsWatermarkTool"
        base.mkdir(parents=True, exist_ok=True)
        return base
    return Path(__file__).parent


PRESETS_FILE = _settings_dir() / "presets.json"

DEFAULT_SETTINGS = {
    "watermark_text": "@YourAccount",
    "position": "右下",
    "custom_x": 100,
    "custom_y": 100,
    "font": "系统默认",
    "font_size": 28,
    "opacity": 0.7,
    "font_color": "white",
    "quality_label": "近似无损 (CRF 18) - 推荐",
    "encoder": "cpu",
    "volume": 1.0,
}

DEFAULT_APP_SETTINGS = {
    "import_mode": "拖拽上传视频",
    "source_folder_upload_val": str(Path.home() / "Downloads"),
    "output_folder_upload_val": str(Path.home() / "Downloads" / "打好水印"),
    "video_folder_path": "",
    "output_folder_path_val": str(Path.home() / "Downloads" / "打好水印"),
    "paste_data": "",
    "match_mode": "语音识别自动配对（推荐）",
    "voice_engine": "免费本地 Whisper",
    "local_whisper_model": "base",
    "recognize_start_seconds": 5,
    "recognize_end_seconds": 20,
    "match_threshold": 0.85,
    "order_sort_mode": "文件名 A-Z",
    "naming_rule": "水印-序号-中文标题",
    "filename_length_label": "较长（推荐，约50个中文字符）",
    "review_only_confirmed": True,
    "move_to_trash": True,
    "drive_target_folder_id": None,
    "drive_target_folder_name": "",
}

DEFAULT_PRESETS = {
    "last_used": dict(DEFAULT_SETTINGS),
    "app_settings": dict(DEFAULT_APP_SETTINGS),
    "presets": {
        "预设1": {"name": "预设1", "settings": dict(DEFAULT_SETTINGS)},
        "预设2": {"name": "预设2", "settings": dict(DEFAULT_SETTINGS)},
        "预设3": {"name": "预设3", "settings": dict(DEFAULT_SETTINGS)},
    },
}


def load_all() -> dict:
    if PRESETS_FILE.exists():
        try:
            data = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
            # 补全缺失字段（兼容旧版本）
            if "last_used" not in data:
                data["last_used"] = dict(DEFAULT_SETTINGS)
            if "presets" not in data:
                data["presets"] = DEFAULT_PRESETS["presets"]
            if "app_settings" not in data:
                data["app_settings"] = dict(DEFAULT_APP_SETTINGS)
            for key, val in DEFAULT_SETTINGS.items():
                data["last_used"].setdefault(key, val)
            for key, val in DEFAULT_APP_SETTINGS.items():
                data["app_settings"].setdefault(key, val)
            return data
        except Exception:
            pass
    return dict(DEFAULT_PRESETS)


def save_all(data: dict) -> None:
    PRESETS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_last_used(settings: dict) -> None:
    data = load_all()
    data["last_used"] = settings
    save_all(data)


def get_app_settings() -> dict:
    data = load_all()
    settings = dict(DEFAULT_APP_SETTINGS)
    settings.update(data.get("app_settings", {}))
    return settings


def save_app_settings(settings: dict) -> None:
    data = load_all()
    current = dict(DEFAULT_APP_SETTINGS)
    current.update(data.get("app_settings", {}))
    current.update(settings)
    data["app_settings"] = current
    save_all(data)


def save_preset(slot_key: str, name: str, settings: dict) -> None:
    data = load_all()
    data["presets"][slot_key] = {"name": name, "settings": settings}
    save_all(data)


def rename_preset(slot_key: str, new_name: str) -> None:
    data = load_all()
    if slot_key in data["presets"]:
        data["presets"][slot_key]["name"] = new_name
    save_all(data)


def get_preset_settings(slot_key: str) -> dict | None:
    data = load_all()
    preset = data["presets"].get(slot_key)
    if preset:
        s = dict(DEFAULT_SETTINGS)
        s.update(preset.get("settings", {}))
        return s
    return None
