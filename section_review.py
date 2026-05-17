from __future__ import annotations

import html

import streamlit as st

from ui_helpers import _pd_dataframe, render_review_video_panel


def render_review_section(
    videos: dict,
    mapping_entries: list,
    ordered_video_files: list,
    match_by_order: bool,
    match_by_voice: bool,
    voice_assignments: dict,
    voice_scores: dict,
    voice_transcripts: dict,
    manual_assignments: dict,
    has_captions: bool,
    _row_key,
    _manual_video_for,
    _matched_files,
    _output_name_for,
    _review_id_for,
    review_video_width: int,
    auto_play_review_video: bool,
    mute_auto_play_review_video: bool,
) -> dict:
    review_items = []
    review_statuses = {}
    matched_entries = 0
    processable_count = 0
    confirmed_count = 0
    problem_count = 0
    unchecked_count = 0
    unmatched = 0
    st.divider()
    st.markdown('<div class="section-title">3️⃣ 配对与审核</div>', unsafe_allow_html=True)
    st.markdown('<div class="subsection-title">📋 配对与人工复核</div>', unsafe_allow_html=True)

    with st.expander(
        "手动匹配 / 修正错配",
        expanded=bool(manual_assignments) or st.session_state.get("show_manual_match_for") is not None,
    ):
        if not ordered_video_files:
            st.caption("当前没有可选视频。")
        else:
            manual_row_options = list(range(len(mapping_entries)))
            manual_row_index = st.selectbox(
                "表格行",
                manual_row_options,
                format_func=lambda idx: (
                    f"{idx + 1}. {mapping_entries[idx]['seq']} · {mapping_entries[idx]['name']}"
                ),
                key="manual_match_row_select",
            )
            manual_row = mapping_entries[manual_row_index]
            manual_key = _row_key(manual_row_index, manual_row)
            video_names = [path.name for path in ordered_video_files]
            manual_options = ["不指定"] + video_names
            current_manual = manual_assignments.get(manual_key, "不指定")
            manual_video_choice = st.selectbox(
                "指定对应视频",
                manual_options,
                index=manual_options.index(current_manual) if current_manual in manual_options else 0,
                key="manual_match_video_select",
            )
            mc1, mc2 = st.columns(2)
            if mc1.button("保存手动匹配", use_container_width=True, key="manual_match_save"):
                if manual_video_choice == "不指定":
                    manual_assignments.pop(manual_key, None)
                else:
                    manual_assignments[manual_key] = manual_video_choice
                st.rerun()
            if mc2.button("清除这一行", use_container_width=True, key="manual_match_clear"):
                manual_assignments.pop(manual_key, None)
                st.rerun()
            if manual_assignments:
                st.caption("手动匹配会优先于语音识别、顺序配对和关键词匹配；切换文件夹后不会丢，但只在同名视频仍存在时生效。")

    if match_by_voice:
        if not voice_assignments:
            st.info("先点击上方“识别视频语音并自动配对”，完成后这里会显示语音和文案的匹配结果。")
    elif match_by_order:
        order_rows = [
            {"顺序": i, "视频文件": path.name}
            for i, path in enumerate(ordered_video_files, 1)
        ]
        with st.expander("查看当前视频顺序", expanded=False):
            st.dataframe(_pd_dataframe(order_rows), use_container_width=True, hide_index=True)
            st.caption("表格第 1 行会配上面第 1 个视频；如果顺序不对，先切换上方的视频排序。")

    preview_rows = []
    review_items = []
    total_videos = 0
    for row_index, row in enumerate(mapping_entries):
        seq = row["seq"]
        new_name = row["name"]
        manual_video = _manual_video_for(row_index, row)
        is_manual_match = manual_video is not None
        matched_files = _matched_files(row_index, seq)
        voice_video_index = voice_assignments.get(row_index) if match_by_voice else None
        voice_text = voice_transcripts.get(voice_video_index, "") if voice_video_index is not None else ""
        voice_score = voice_scores.get(row_index)
        if not matched_files:
            preview_rows.append({
                "顺序": row_index + 1 if (match_by_order or match_by_voice) else "—",
                "序号": seq,
                "中文标题": new_name,
                "原文件": "(没有对应视频)" if (match_by_order or match_by_voice) else f"(未匹配到「{seq}」)",
                "输出文件名": "—",
                **({"匹配度": "—", "识别英文语音": "—"} if match_by_voice else {}),
                **({"英文文案": row.get("caption", "") or "—"} if has_captions else {}),
                "状态": "❌ 未找到",
            })
        else:
            total_videos += len(matched_files)
            for i, video_file in enumerate(matched_files, 1):
                out_name = _output_name_for(seq, new_name, video_file, len(matched_files), i)
                review_id = _review_id_for(row_index, video_file, out_name)
                review_items.append({
                    "id": review_id,
                    "row_index": row_index,
                    "match_index": i,
                    "row": row,
                    "seq": seq,
                    "chinese_title": new_name,
                    "caption": row.get("caption", ""),
                    "video_file": video_file,
                    "output_name": out_name,
                    "voice_text": voice_text,
                    "voice_score": voice_score,
                    "manual_match": is_manual_match,
                })
                preview_rows.append({
                    "顺序": row_index + 1 if (match_by_order or match_by_voice) else "—",
                    "序号": seq,
                    "中文标题": new_name,
                    "原文件": video_file.name,
                    "输出文件名": out_name,
                    **({
                        "匹配度": f"{voice_score:.0%}" if voice_score is not None else "—",
                        "识别英文语音": (voice_text[:80] + "…") if len(voice_text) > 80 else (voice_text or "—"),
                    } if match_by_voice else {}),
                    **({"英文文案": row.get("caption", "") or "—"} if has_captions else {}),
                    "状态": "✅ 手动匹配" if is_manual_match else f"✅ 已找到{f' ({len(matched_files)}个)' if len(matched_files) > 1 and i == 1 else ''}",
                })

    preview_df = _pd_dataframe(preview_rows)
    review_statuses = st.session_state.setdefault("review_statuses", {})
    st.session_state.setdefault("review_only_confirmed", True)
    confirmed_count = 0
    problem_count = 0
    unchecked_count = 0

    review_ui_col, review_video_col = st.columns([1.45, 1], gap="large")
    with review_ui_col:
        st.dataframe(preview_df, use_container_width=True, hide_index=True)

        if has_captions:
            st.markdown(
                '<div class="info-bar info-bar-green" style="margin-top:8px;">'
                '<span>📝</span><span>英文文案仅用于配对和复核；处理后不再自动生成同名 .txt 文件。</span>'
                '</div>',
                unsafe_allow_html=True,
            )

        if review_items:
            st.divider()
            confirmed_count = sum(1 for item in review_items if review_statuses.get(item["id"]) == "confirmed")
            problem_count = sum(1 for item in review_items if review_statuses.get(item["id"]) == "problem")
            unchecked_count = len(review_items) - confirmed_count - problem_count

            st.markdown(
                f"""
                <div class="review-strip">
                  <div class="review-chip"><span>已确认</span><strong>{confirmed_count}</strong></div>
                  <div class="review-chip"><span>待复核</span><strong>{unchecked_count}</strong></div>
                  <div class="review-chip"><span>有问题</span><strong>{problem_count}</strong></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            review_options = list(range(len(review_items)))
            pending_review_index = st.session_state.pop("pending_review_item_select", None)
            if pending_review_index is not None:
                st.session_state["review_item_select"] = max(
                    0,
                    min(int(pending_review_index), len(review_items) - 1),
                )
            if st.session_state.get("review_item_select") not in review_options:
                st.session_state["review_item_select"] = 0
            selector_col, gate_col = st.columns([3.4, 1.1])
            with selector_col:
                selected_index = st.selectbox(
                    "选择要复核的视频",
                    review_options,
                    format_func=lambda idx: (
                        f"{review_items[idx]['seq']} · {review_items[idx]['video_file'].name} → "
                        f"{review_items[idx]['output_name']}"
                    ),
                    key="review_item_select",
                )
            with gate_col:
                review_only_confirmed = st.checkbox(
                    "只处理已确认",
                    key="review_only_confirmed",
                    help="建议保持开启：人工确认后再打水印和改名，避免识别错配后批量输出。",
                )
            selected_item = review_items[selected_index]
            selected_status = review_statuses.get(selected_item["id"], "")
            selected_status_label = {
                "confirmed": "已确认通过",
                "problem": "已标记有问题",
            }.get(selected_status, "待复核")
            score_text = f"{selected_item['voice_score']:.0%}" if selected_item["voice_score"] is not None else "—"

            st.session_state["active_review_video"] = {
                "path": str(selected_item["video_file"]),
                "name": selected_item["video_file"].name,
                "caption": selected_item.get("caption", ""),
                "voice_text": selected_item.get("voice_text", ""),
                "score": score_text,
                "window": f"{st.session_state.get('recognize_start_seconds', 10)}-{st.session_state.get('recognize_end_seconds', 20)} 秒" if match_by_voice else "",
            }

            safe_status = html.escape(selected_status_label)
            safe_output_name = html.escape(selected_item["output_name"])
            st.markdown(
                f"""
                <div class="review-meta">
                  <div class="review-meta-row">
                    <div class="review-meta-label">状态</div>
                    <div class="review-meta-value"><span class="review-status-pill">{safe_status}</span></div>
                  </div>
                  <div class="review-meta-row">
                    <div class="review-meta-label">输出文件</div>
                    <div class="review-meta-value">{safe_output_name}</div>
                  </div>
                  <div class="review-meta-row">
                    <div class="review-meta-label">匹配度</div>
                    <div class="review-meta-value">{score_text}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption("右侧面板显示当前选中视频；这里专注核对标题、文案和操作结果。")
            cn_col, en_col = st.columns(2)
            with cn_col:
                st.text_area(
                    "中文文案 / 标题",
                    value=selected_item["chinese_title"] or "",
                    height=180,
                    disabled=True,
                    key=f"review_chinese_text_{selected_index}",
                )
            with en_col:
                st.text_area(
                    "英文文案（表格原文）",
                    value=selected_item.get("caption", ""),
                    height=180,
                    disabled=True,
                    key=f"review_caption_text_{selected_index}",
                )
            if match_by_voice and (
                selected_item["row_index"] not in voice_assignments
                or not selected_item.get("voice_text")
            ):
                if st.button("✋ 手动指定这条对应的视频", key="quick_manual_match_btn"):
                    st.session_state["show_manual_match_for"] = selected_index
            if selected_item.get("voice_text"):
                st.text_area(
                    "识别到的英文语音",
                    value=selected_item["voice_text"],
                    height=110,
                    disabled=True,
                    key=f"review_voice_text_{selected_index}",
                )

                def _next_review_index_after(current_index: int) -> int:
                    if len(review_items) <= 1:
                        return current_index
                    for step in range(1, len(review_items) + 1):
                        next_index = (current_index + step) % len(review_items)
                        next_status = review_statuses.get(review_items[next_index]["id"])
                        if next_status not in {"confirmed", "problem"}:
                            return next_index
                    return (current_index + 1) % len(review_items)

                ba, bb, bc = st.columns(3)
                if ba.button("确认通过", type="primary", use_container_width=True, key=f"review_ok_{selected_item['id']}"):
                    review_statuses[selected_item["id"]] = "confirmed"
                    st.session_state["pending_review_item_select"] = _next_review_index_after(selected_index)
                    st.rerun()
                if bb.button("标记有问题", use_container_width=True, key=f"review_bad_{selected_item['id']}"):
                    review_statuses[selected_item["id"]] = "problem"
                    st.session_state["pending_review_item_select"] = _next_review_index_after(selected_index)
                    st.rerun()
                if bc.button("取消标记", use_container_width=True, key=f"review_clear_{selected_item['id']}"):
                    review_statuses.pop(selected_item["id"], None)
                    st.rerun()
        else:
            st.session_state.pop("active_review_video", None)
            review_only_confirmed = bool(st.session_state.get("review_only_confirmed", True))
    with review_video_col:
        render_review_video_panel(
            videos,
            review_video_width,
            auto_play_review_video,
            mute_auto_play_review_video,
            panel_key="manual_review",
        )

    matched_entries = sum(
        1 for row_index, row in enumerate(mapping_entries)
        if _matched_files(row_index, row["seq"])
    )
    unmatched = len(mapping_entries) - matched_entries

    processable_count = confirmed_count if review_only_confirmed else max(0, total_videos - problem_count)
    st.markdown(
        f"""
        <div class="workflow-stats">
          <div class="workflow-stat"><span>总条目</span><strong>{len(mapping_entries)}</strong></div>
          <div class="workflow-stat"><span>已匹配</span><strong>{matched_entries}</strong></div>
          <div class="workflow-stat"><span>未匹配</span><strong>{unmatched}</strong></div>
          <div class="workflow-stat"><span>可处理视频</span><strong>{processable_count}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if (match_by_order or match_by_voice) and len(ordered_video_files) != len(mapping_entries):
        if len(ordered_video_files) > len(mapping_entries):
            st.info(f"视频比表格多 {len(ordered_video_files) - len(mapping_entries)} 个，多出来的视频这次不会处理。")
        else:
            st.warning(f"表格比视频多 {len(mapping_entries) - len(ordered_video_files)} 行，多出来的文案没有对应视频。")

    return {
        "review_items": review_items,
        "review_statuses": review_statuses,
        "review_only_confirmed": review_only_confirmed,
        "matched_entries": matched_entries,
        "processable_count": processable_count,
        "confirmed_count": confirmed_count,
        "problem_count": problem_count,
        "unchecked_count": unchecked_count,
        "unmatched": unmatched,
    }
