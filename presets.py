from __future__ import annotations

import json
from pathlib import Path

PRESETS_FILE = Path(__file__).parent / "presets.json"

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

DEFAULT_PRESETS = {
    "last_used": dict(DEFAULT_SETTINGS),
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
            for key, val in DEFAULT_SETTINGS.items():
                data["last_used"].setdefault(key, val)
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
