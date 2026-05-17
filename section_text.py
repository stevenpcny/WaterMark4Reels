from __future__ import annotations

from pathlib import Path

import streamlit as st

from matching import (
    assign_voice_matches,
    build_output_name,
    mapping_entries_for_mode,
    matched_files_for_row,
    parse_mapping_rows,
    review_id_for,
    sort_video_files,
)
from watermark import transcribe_video_local_whisper, transcribe_video_openai


def render_text_section(
    videos: dict,
    match_mode: str,
    voice_engine: str,
    voice_api_key: str,
    local_whisper_model: str,
    recognize_start_seconds: int,
    recognize_end_seconds: int,
    match_threshold: float,
    order_sort_mode: str,
    naming_rule: str,
    filename_max_bytes: int,
) -> dict:
    mapping_rows = []
    mapping = {}
    caption_by_seq = {}
    mapping_entries = []
    ordered_video_files = []
    match_by_order = False
    match_by_voice = False
    voice_assignments = {}
    voice_scores = {}
    voice_transcripts = {}
    manual_assignments = {}
    has_captions = False
    _row_key = None
    _manual_video_for = None
    _matched_files = None
    _output_name_for = None
    _review_id_for = None
    st.markdown('<div class="section-title">2️⃣ 粘贴文案</div>', unsafe_allow_html=True)
    st.caption("从 Google Sheets 复制三列（序号 + 中文标题 + 英文文案），直接粘贴到下方")

    st.session_state.setdefault("paste_data", "")
    paste_data = st.text_area(
        "粘贴数据",
        height=150,
        placeholder="1\t我的第一个Reel\tPaste the English script for video one here\n2\t旅行vlog第二集\tPaste the English script for video two here",
        label_visibility="collapsed",
        key="paste_data",
    )

    if paste_data and videos:
        mapping_rows = parse_mapping_rows(paste_data)
        mapping = {row["seq"]: row["name"] for row in mapping_rows}
        caption_by_seq = {row["seq"]: row.get("caption", "") for row in mapping_rows}
        has_captions = any(text.strip() for text in caption_by_seq.values())
        if mapping:
            match_by_voice = match_mode.startswith("语音识别")
            match_by_order = match_mode.startswith("按视频顺序")

            ordered_video_files = sort_video_files(videos, order_sort_mode)
            mapping_entries = mapping_entries_for_mode(
                mapping_rows,
                match_by_voice=match_by_voice,
                match_by_order=match_by_order,
            )

            voice_assignments = {}
            voice_transcripts = {}
            voice_scores = {}
            if match_by_voice:
                recognize_start_seconds = int(recognize_start_seconds)
                recognize_end_seconds = int(recognize_end_seconds)
                recognize_duration = max(0, recognize_end_seconds - recognize_start_seconds)
                video_signature = [
                    # 拖拽上传模式每次页面刷新都会重写临时文件，mtime 会变化；
                    # 只用文件名和大小，避免“开始处理”刷新后丢失语音配对结果。
                    (path.name, path.stat().st_size if path.exists() else 0)
                    for path in ordered_video_files
                ]
                voice_signature = repr((
                    paste_data,
                    video_signature,
                    voice_engine,
                    local_whisper_model,
                    recognize_start_seconds,
                    recognize_end_seconds,
                    match_threshold,
                ))
                voice_match_cache = st.session_state.setdefault("voice_match_cache", {})
                stored_voice = voice_match_cache.get(voice_signature) or st.session_state.get("voice_match_result", {})
                if stored_voice.get("signature") == voice_signature:
                    voice_assignments = stored_voice.get("assignments", {})
                    voice_transcripts = stored_voice.get("transcripts", {})
                    voice_scores = stored_voice.get("scores", {})

                if st.button(
                    f"🎙️ 识别 {len(ordered_video_files)} 个视频语音并自动配对",
                    type="primary",
                    use_container_width=True,
                ):
                    if voice_engine == "OpenAI API" and not voice_api_key.strip():
                        st.warning("请先填写 OpenAI API Key。")
                    elif recognize_duration <= 0:
                        st.warning("识别结束位置必须大于开始位置。")
                    elif not any(row.get("caption", "").strip() for row in mapping_entries):
                        st.warning("没有检测到第三列英文文案，请从表格复制：序号 + 中文标题 + 英文文案。")
                    else:
                        progress = st.progress(0)
                        status_text = st.empty()
                        transcribed = {}
                        failures = []

                        for i, video_file in enumerate(ordered_video_files):
                            status_text.markdown(
                                f'<div class="info-bar info-bar-blue">'
                                f'<span>🎙️</span>'
                                f'<span>正在识别 ({i+1}/{len(ordered_video_files)})：{video_file.name}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                            if voice_engine == "免费本地 Whisper":
                                ok, result_or_error = transcribe_video_local_whisper(
                                    str(video_file),
                                    start=recognize_start_seconds,
                                    duration=recognize_duration,
                                    model_size=local_whisper_model,
                                )
                            else:
                                ok, result_or_error = transcribe_video_openai(
                                    str(video_file),
                                    voice_api_key,
                                    start=recognize_start_seconds,
                                    duration=recognize_duration,
                                )
                            if ok:
                                transcribed[i] = result_or_error
                            else:
                                failures.append(f"{video_file.name}：{result_or_error}")
                            progress.progress((i + 1) / len(ordered_video_files))

                        assignments, scores = assign_voice_matches(
                            transcribed,
                            mapping_entries,
                            match_threshold,
                        )

                        voice_result = {
                            "signature": voice_signature,
                            "assignments": assignments,
                            "transcripts": transcribed,
                            "scores": scores,
                            "failures": failures,
                        }
                        st.session_state["voice_match_result"] = voice_result
                        st.session_state.setdefault("voice_match_cache", {})[voice_signature] = voice_result
                        voice_assignments = assignments
                        voice_transcripts = transcribed
                        voice_scores = scores
                        status_text.empty()
                        progress.empty()

                        if failures:
                            st.warning("部分视频识别失败：\n" + "\n".join(f"• {f}" for f in failures[:5]))
                        st.success(f"语音识别完成，达到 {match_threshold:.0%} 匹配度的有 {len(assignments)} 条。请先检查下方预览。")
                        skipped = len(mapping_entries) - len(assignments)
                        if skipped:
                            st.warning(f"有 {skipped} 条未达到匹配度阈值，已留在未匹配中。")

            manual_assignments = st.session_state.setdefault("manual_video_assignments", {})
            manual_video_lookup = {path.name: path for path in ordered_video_files}

            def _row_key(row_index: int, row: dict) -> str:
                return f"{row_index}:{row.get('seq', '')}:{row.get('name', '')}"

            def _manual_video_for(row_index: int, row: dict) -> Path | None:
                assigned_name = manual_assignments.get(_row_key(row_index, row))
                if not assigned_name:
                    return None
                return manual_video_lookup.get(assigned_name)

            def _matched_files(row_index: int, seq: str) -> list:
                row = mapping_entries[row_index] if row_index < len(mapping_entries) else {"seq": seq}
                manual_video = _manual_video_for(row_index, row)
                if manual_video is not None:
                    return [manual_video]
                return matched_files_for_row(
                    row_index,
                    seq,
                    videos,
                    ordered_video_files,
                    match_by_voice=match_by_voice,
                    match_by_order=match_by_order,
                    voice_assignments=voice_assignments,
                )

            def _output_name_for(seq: str, chinese_title: str, video_file: Path, matched_count: int, match_index: int) -> str:
                return build_output_name(
                    seq,
                    chinese_title,
                    video_file,
                    matched_count,
                    match_index,
                    naming_rule,
                    max_bytes=filename_max_bytes,
                )

            def _review_id_for(row_index: int, video_file: Path, output_name: str) -> str:
                return review_id_for(row_index, video_file, output_name)

    return {
        "paste_data": paste_data,
        "mapping_rows": mapping_rows,
        "mapping": mapping,
        "caption_by_seq": caption_by_seq,
        "mapping_entries": mapping_entries,
        "ordered_video_files": ordered_video_files,
        "match_by_order": match_by_order,
        "match_by_voice": match_by_voice,
        "voice_assignments": voice_assignments,
        "voice_scores": voice_scores,
        "voice_transcripts": voice_transcripts,
        "manual_assignments": manual_assignments,
        "has_captions": has_captions,
        "_row_key": _row_key,
        "_manual_video_for": _manual_video_for,
        "_matched_files": _matched_files,
        "_output_name_for": _output_name_for,
        "_review_id_for": _review_id_for,
    }
