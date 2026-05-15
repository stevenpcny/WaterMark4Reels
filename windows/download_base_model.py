from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python download_base_model.py <target_dir>")
        return 2

    target_dir = Path(sys.argv[1]).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Missing huggingface_hub. Run: python -m pip install huggingface-hub")
        return 1

    snapshot_download(
        repo_id="Systran/faster-whisper-base",
        local_dir=str(target_dir),
        local_dir_use_symlinks=False,
        allow_patterns=[
            "config.json",
            "model.bin",
            "tokenizer.json",
            "vocabulary.txt",
            "README.md",
        ],
    )

    required = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
    missing = [name for name in required if not (target_dir / name).is_file()]
    if missing:
        print("Model download incomplete. Missing: " + ", ".join(missing))
        return 1

    print(f"Downloaded faster-whisper base model to: {target_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
