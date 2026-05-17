from __future__ import annotations

import logging
import os
import tempfile

import streamlit as st
import streamlit.runtime as st_runtime

from presets import DEFAULT_SETTINGS, save_app_settings
from section_export import render_export_section
from section_image_match import render_image_match_section
from section_review import render_review_section
from section_text import render_text_section
from section_videos import render_videos_section
from ui_helpers import ensure_ffmpeg, initialize_session_state, inject_styles
from ui_sidebar import render_sidebar
from watermark import generate_audio_preview

if not st_runtime.exists():
    logging.disable(logging.CRITICAL)

DEFAULT_SETTINGS.setdefault("burn_subtitles", False)

st.set_page_config(
    page_title="Reels 水印工具",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_styles()
ensure_ffmpeg()
initialize_session_state()

sidebar_state = render_sidebar(DEFAULT_SETTINGS)
watermark_text = sidebar_state["watermark_text"]
position = sidebar_state["position"]
custom_x = sidebar_state["custom_x"]
custom_y = sidebar_state["custom_y"]
font_size = sidebar_state["font_size"]
font_path = sidebar_state["font_path"]
opacity = sidebar_state["opacity"]
font_color = sidebar_state["font_color"]
quality_label = sidebar_state["quality_label"]
quality = sidebar_state["quality"]
encoder = sidebar_state["encoder"]
volume = sidebar_state["volume"]
match_mode = sidebar_state["match_mode"]
voice_engine = sidebar_state["voice_engine"]
voice_api_key = sidebar_state["voice_api_key"]
local_whisper_model = sidebar_state["local_whisper_model"]
recognize_start_seconds = sidebar_state["recognize_start_seconds"]
recognize_end_seconds = sidebar_state["recognize_end_seconds"]
match_threshold = sidebar_state["match_threshold"]
order_sort_mode = sidebar_state["order_sort_mode"]
naming_rule = sidebar_state["naming_rule"]
filename_length_label = sidebar_state["filename_length_label"]
filename_max_bytes = sidebar_state["filename_max_bytes"]
auto_play_review_video = sidebar_state["auto_play_review_video"]
mute_auto_play_review_video = sidebar_state["mute_auto_play_review_video"]
review_video_width = sidebar_state["review_video_width"]
sidebar_export_btn = sidebar_state["sidebar_export_btn"]

# ══════════════════════════════════════
# 页头
# ══════════════════════════════════════
st.markdown("""
<div style="margin-bottom:1.8rem;">
  <h1 style="font-size:34px;font-weight:700;margin:0;color:#1D1D1F;letter-spacing:-0.8px;
             font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',sans-serif;">
    Reels 批量打水印
  </h1>
  <p style="color:#8E8E93;margin:5px 0 0;font-size:15px;font-weight:400;letter-spacing:-0.1px;">
    批量添加文字水印 · 自动重命名 · 保留原始画质
  </p>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════
# 主区域
# ══════════════════════════════════════
video_layout_mode = st.session_state.get("review_video_layout", "标准")
column_ratios = {
    "标准": [3, 2],
    "大": [2.35, 2.25],
    "超大": [1.8, 2.7],
}.get(video_layout_mode, [3, 2])
left_col, right_col = st.columns(column_ratios, gap="large")

with left_col:
    video_state = render_videos_section()
    videos = video_state["videos"]
    source_folder = video_state["source_folder"]
    output_folder = video_state["output_folder"]
    import_mode = video_state["import_mode"]

    text_state = render_text_section(
        videos,
        match_mode,
        voice_engine,
        voice_api_key,
        local_whisper_model,
        recognize_start_seconds,
        recognize_end_seconds,
        match_threshold,
        order_sort_mode,
        naming_rule,
        filename_max_bytes,
    )
    paste_data = text_state["paste_data"]
    mapping_entries = text_state["mapping_entries"]
    ordered_video_files = text_state["ordered_video_files"]
    match_by_order = text_state["match_by_order"]
    match_by_voice = text_state["match_by_voice"]

    review_state = {
        "review_items": [],
        "review_statuses": {},
        "review_only_confirmed": bool(st.session_state.get("review_only_confirmed", True)),
        "matched_entries": 0,
    }
    if paste_data and videos:
        review_state = render_review_section(
            videos,
            mapping_entries,
            ordered_video_files,
            match_by_order,
            match_by_voice,
            text_state["voice_assignments"],
            text_state["voice_scores"],
            text_state["voice_transcripts"],
            text_state["manual_assignments"],
            text_state["has_captions"],
            text_state["_row_key"],
            text_state["_manual_video_for"],
            text_state["_matched_files"],
            text_state["_output_name_for"],
            text_state["_review_id_for"],
            review_video_width,
            auto_play_review_video,
            mute_auto_play_review_video,
        )
        render_image_match_section(
            review_state["review_items"],
            review_state["review_statuses"],
            review_state["review_only_confirmed"],
        )
    elif videos:
        # 没有字幕数据时，仍允许纯图片-视频匹配
        _video_only_items = [
            {"id": v.name, "video_file": v, "output_name": v.name}
            for v in videos.values()
        ]
        _video_only_statuses = {v.name: "confirmed" for v in videos.values()}
        render_image_match_section(
            _video_only_items,
            _video_only_statuses,
            False,
        )

    render_export_section(
        paste_data,
        videos,
        source_folder,
        output_folder,
        import_mode,
        sidebar_export_btn,
        review_state["matched_entries"],
        match_by_voice,
        match_by_order,
        review_state["review_items"],
        review_state["review_statuses"],
        review_state["review_only_confirmed"],
        mapping_entries,
        text_state["_matched_files"],
        text_state["_output_name_for"],
        text_state["_review_id_for"],
        watermark_text,
        position,
        custom_x,
        custom_y,
        font_size,
        font_path,
        opacity,
        font_color,
        quality,
        encoder,
        volume,
    )

# ── 右栏：检查与预览 ──
with right_col:
    # ── 音量试听 ──
    if videos:
        first_video_for_audio = sorted(videos.values(), key=lambda p: p.stem)[0]
        with st.expander("音量试听", expanded=False):
            st.caption(f"当前音量：{volume:.1f}x；截取前 8 秒试听。")
            if st.button("生成试听片段", use_container_width=True, key="audio_preview_btn"):
                with st.spinner("生成试听中…"):
                    old_audio = st.session_state.get("audio_preview_path")
                    if old_audio and os.path.isfile(old_audio):
                        try:
                            os.unlink(old_audio)
                        except Exception:
                            pass
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                        audio_path = tmp.name
                    ok, err = generate_audio_preview(
                        str(first_video_for_audio), audio_path, volume=volume
                    )
                    if ok:
                        st.session_state["audio_preview_path"] = audio_path
                    else:
                        st.error(f"试听生成失败：{err}")

            if "audio_preview_path" in st.session_state and os.path.isfile(st.session_state["audio_preview_path"]):
                st.audio(st.session_state["audio_preview_path"], format="audio/mp3")



save_app_settings({
    "import_mode": import_mode,
    "source_folder_upload_val": st.session_state.get("source_folder_upload_val", ""),
    "output_folder_upload_val": st.session_state.get("output_folder_upload_val", ""),
    "video_folder_path": st.session_state.get("video_folder_path", ""),
    "output_folder_path_val": st.session_state.get("output_folder_path_val", ""),
    "paste_data": st.session_state.get("paste_data", ""),
    "match_mode": st.session_state.get("match_mode", match_mode),
    "voice_engine": st.session_state.get("voice_engine", voice_engine),
    "local_whisper_model": st.session_state.get("local_whisper_model", local_whisper_model),
    "recognize_start_seconds": int(st.session_state.get("recognize_start_seconds", 10)),
    "recognize_end_seconds": int(st.session_state.get("recognize_end_seconds", 20)),
    "match_threshold": float(st.session_state.get("match_threshold", 0.85)),
    "order_sort_mode": st.session_state.get("order_sort_mode", order_sort_mode),
    "naming_rule": st.session_state.get("naming_rule", naming_rule),
    "filename_length_label": st.session_state.get("filename_length_label", filename_length_label),
    "review_only_confirmed": bool(st.session_state.get("review_only_confirmed", True)),
    "move_to_trash": bool(st.session_state.get("move_to_trash", True)),
    "burn_subtitles": bool(st.session_state.get("burn_subtitles", False)),
    "drive_target_folder_id": st.session_state.get("drive_target_folder_id"),
    "drive_target_folder_name": st.session_state.get("drive_target_folder_name", ""),
    "source_image_folder": st.session_state.get("source_image_folder", ""),
    "image_match_auto_threshold": int(st.session_state.get("image_match_auto_threshold", 18)),
    "image_match_review_threshold": int(st.session_state.get("image_match_review_threshold", 24)),
})
