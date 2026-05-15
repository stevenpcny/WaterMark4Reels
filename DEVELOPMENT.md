# Development Guide

This is the isolated Codex 5.5 development copy. Work in this folder only:

```text
/Users/xxxxx/Documents/打水印工具-codex55
```

Do not copy secrets or runtime settings from the original project. These files are intentionally ignored:

- `credentials*.json`
- `used-credentials*.json`
- `token.json`
- `presets.json`
- `.oauth_error`, `.folders_error`, `.write_test`
- local logs, virtualenvs, models, FFmpeg binaries, build/dist outputs, uploaded video caches

## Run

Use port `8502` so this copy does not collide with the existing app:

```bash
REELS_STREAMLIT_PORT=8502 python3 start.py
```

## Test

Install test dependencies when needed:

```bash
python3 -m pip install -r requirements-dev.txt
```

Run checks:

```bash
python3 -m compileall app.py watermark.py presets.py gdrive.py matching.py processing.py
python3 -m pytest
```

The tests avoid real video processing and focus on deterministic logic: mapping parsing, filename sanitizing, video matching, similarity, process queue creation, report writing, and MIME inference.

## Architecture Notes

- `app.py` remains the Streamlit UI entrypoint.
- `watermark.py` still owns FFmpeg/Pillow processing and local/OpenAI transcription.
- `matching.py` owns matching and naming logic used by the UI.
- `processing.py` owns queue construction, existing-output skip checks, caption writing, job reports, upload file selection, and MIME inference.
- `gdrive.py` accepts an optional `mime_type` for uploads; Drive upload failures are reported in the UI and do not change local processing success.
- `ui_styles.py` owns the large Streamlit CSS block so `app.py` stays smaller and easier to scan.

## Manual Acceptance

1. Start this copy on port `8502`.
2. Import a small test video folder.
3. Paste Google Sheets rows with `序号 + 中文标题 + 英文文案`.
4. Verify all three matching modes still preview correctly.
5. Confirm at least one item, process it, and check that the output video, `.reels-watermark-job.json`, and `处理结果.csv` are created.
6. Run the same job again and verify existing complete outputs are skipped by default.
7. Confirm the original project's `presets.json`, `token.json`, and credentials files were not modified.
## UX State Notes

- `review_statuses` is intentionally not pruned to the current preview list, so switching folders or modes does not erase prior review work.
- `voice_match_cache` stores recognition results by table/video/settings signature.
- `manual_video_assignments` stores row-to-video-name overrides and takes priority over automatic matching.
- Caption `.txt` generation remains supported in `processing.py` for tests and future use, but the UI now keeps it disabled by default.
- The right-side review player uses Streamlit's media cache plus a custom HTML5 video control for preload, autoplay, playback-rate selection, and smoother scrub previews.
