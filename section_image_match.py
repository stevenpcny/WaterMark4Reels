from __future__ import annotations

from pathlib import Path

import streamlit as st

from image_matching import assign_videos_to_images, find_image_files, hash_image, hash_video_frames, make_frame_workdir
from ui_helpers import _pd_dataframe


def render_image_match_section(
    review_items: list,
    review_statuses: dict,
    review_only_confirmed: bool,
) -> None:
    _image_folder = (st.session_state.get("source_image_folder") or "").strip()
    all_image_paths = find_image_files(_image_folder) if _image_folder else []
    if not all_image_paths:
        return

    st.divider()
    st.markdown('<div class="section-title">🖼️ 图片配对</div>', unsafe_allow_html=True)

    all_image_strs = [str(p) for p in all_image_paths]

    _videos = [
        it for it in review_items
        if not review_only_confirmed or review_statuses.get(it["id"]) == "confirmed"
    ]

    has_result = "image_match_result" in st.session_state
    btn_label = "🔄 重新配对" if has_result else "🖼️ 开始配对"

    btn_col, clear_col = st.columns([4, 1])
    with btn_col:
        do_match = st.button(
            btn_label,
            use_container_width=True,
            key="run_image_match_btn",
            disabled=not _videos or not all_image_paths,
        )
    with clear_col:
        if st.button("🗑️ 清空", use_container_width=True, key="clear_image_match_btn"):
            st.session_state.pop("image_match_result", None)
            st.session_state.pop("image_match_overrides", None)
            st.rerun()

    # ── 执行匹配 ──
    if do_match and _videos and all_image_paths:
        auto_thr = int(st.session_state.get("image_match_auto_threshold", 18))
        review_thr = int(st.session_state.get("image_match_review_threshold", 24))
        progress = st.progress(0)
        status_text = st.empty()
        work_dir = make_frame_workdir()
        try:
            image_hashes: dict[str, tuple[str, str]] = {}
            total_imgs = len(all_image_paths)
            for idx, img_path in enumerate(all_image_paths):
                status_text.write(f"计算图片哈希 {idx+1}/{total_imgs}：{img_path.name}")
                h = hash_image(img_path)
                if h:
                    image_hashes[str(img_path)] = h
                progress.progress((idx + 1) / max(1, total_imgs + len(_videos)))

            video_hashes: dict[str, list[tuple[str, str]]] = {}
            for vidx, item in enumerate(_videos):
                status_text.write(f"抽帧 {vidx+1}/{len(_videos)}：{item['video_file'].name}")
                vh = hash_video_frames(item["video_file"], work_dir)
                if vh:
                    video_hashes[item["id"]] = vh
                progress.progress((total_imgs + vidx + 1) / max(1, total_imgs + len(_videos)))

            result = assign_videos_to_images(
                video_hashes, image_hashes,
                auto_threshold=auto_thr,
                review_threshold=review_thr,
            )
            st.session_state["image_match_result"] = result
            st.session_state["image_match_overrides"] = {}
        finally:
            try:
                import shutil as _sh
                _sh.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass
            status_text.empty()
            progress.empty()

    _result = st.session_state.get("image_match_result")
    if not _result:
        return

    assignments: dict = dict(_result.get("assignments", {}))
    overrides: dict = st.session_state.setdefault("image_match_overrides", {})
    review_lookup = {it["id"]: it for it in review_items}

    # 最终映射：override 优先，否则取自动结果
    final_map: dict[str, str | None] = {
        vid: overrides.get(vid, info.get("image"))
        for vid, info in assignments.items()
    }

    # ── 统计 ──
    auto_n = sum(1 for v, info in assignments.items() if info["status"] == "auto" and final_map.get(v))
    review_n = sum(1 for v, info in assignments.items() if info["status"] == "review" and v not in overrides)
    unmatched_n = sum(1 for v in assignments if not final_map.get(v))

    st.markdown(
        f"""
        <div class="workflow-stats">
          <div class="workflow-stat"><span>✅ 自动匹配</span><strong>{auto_n}</strong></div>
          <div class="workflow-stat"><span>🟡 需确认</span><strong>{review_n}</strong></div>
          <div class="workflow-stat"><span>❌ 未匹配</span><strong>{unmatched_n}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 结果表格（只读概览） ──
    table_rows = []
    for vid, info in assignments.items():
        item = review_lookup.get(vid)
        if not item:
            continue
        final_img = final_map.get(vid)
        if vid in overrides:
            status_label = "✅ 已修改" if final_img else "🚫 已跳过"
        else:
            status_label = {
                "auto": "✅ 自动",
                "review": "🟡 需确认",
                "unmatched": "❌ 未匹配",
            }.get(info["status"], "")
        table_rows.append({
            "视频": item["video_file"].name,
            "原图": Path(final_img).name if final_img else "—",
            "状态": status_label,
        })
    if table_rows:
        st.dataframe(_pd_dataframe(table_rows), use_container_width=True, hide_index=True)

    # ── 需要人工确认的行：内嵌下拉修改 ──
    attention_vids = [
        vid for vid, info in assignments.items()
        if (info["status"] in ("review", "unmatched") and vid not in overrides)
    ]
    if attention_vids:
        st.markdown("**需要确认的配对：**")
        img_options_display = ["（跳过）"] + [Path(p).name for p in all_image_strs]
        for vid in attention_vids:
            item = review_lookup.get(vid)
            if not item:
                continue
            info = assignments[vid]
            current_img = info.get("image")
            try:
                default_idx = (all_image_strs.index(current_img) + 1) if current_img else 0
            except ValueError:
                default_idx = 0
            row_cols = st.columns([2, 3, 1])
            with row_cols[0]:
                st.markdown(f"<div style='padding-top:6px;font-size:13px'>{item['video_file'].name}</div>", unsafe_allow_html=True)
            with row_cols[1]:
                chosen = st.selectbox(
                    "对应原图",
                    options=list(range(len(img_options_display))),
                    index=default_idx,
                    format_func=lambda i: img_options_display[i],
                    key=f"inline_img_pick_{vid}",
                    label_visibility="collapsed",
                )
            with row_cols[2]:
                if st.button("确认", key=f"inline_img_confirm_{vid}"):
                    overrides[vid] = None if chosen == 0 else all_image_strs[chosen - 1]
                    st.rerun()

    # ── 修改已自动匹配的行 ──
    with st.expander("修改某一行的配对", expanded=False):
        all_vids = list(assignments.keys())
        if all_vids:
            img_options_display2 = ["（跳过）"] + [Path(p).name for p in all_image_strs]
            sel_vid = st.selectbox(
                "选择视频",
                all_vids,
                format_func=lambda v: review_lookup[v]["video_file"].name if v in review_lookup else v,
                key="manual_image_pick_vid",
            )
            current_img2 = overrides.get(sel_vid, assignments[sel_vid].get("image"))
            try:
                default_idx2 = (all_image_strs.index(current_img2) + 1) if current_img2 else 0
            except ValueError:
                default_idx2 = 0
            sel_img = st.selectbox(
                "对应原图",
                options=list(range(len(img_options_display2))),
                index=default_idx2,
                format_func=lambda i: img_options_display2[i],
                key="manual_image_pick_img",
            )
            if st.button("应用修改", key="apply_manual_image_pick"):
                overrides[sel_vid] = None if sel_img == 0 else all_image_strs[sel_img - 1]
                st.rerun()

    # ── 确认并改名 ──
    rename_map: dict[str, str] = {
        vid: img for vid, img in final_map.items() if img
    }
    if rename_map:
        st.divider()
        rename_preview = []
        for vid, img in rename_map.items():
            item = review_lookup.get(vid)
            if not item:
                continue
            img_path = Path(img)
            new_name = f"{Path(item['output_name']).stem}{img_path.suffix.lower()}"
            if new_name != img_path.name:
                rename_preview.append({
                    "原图": img_path.name,
                    "→ 改为": new_name,
                })

        if rename_preview:
            st.dataframe(_pd_dataframe(rename_preview), use_container_width=True, hide_index=True)

        if st.button(
            f"✅ 确认并改名（{len(rename_preview)} 张）",
            use_container_width=True,
            key="rename_images_in_place_btn",
            type="primary",
        ):
            rename_results = []
            for vid, img in list(rename_map.items()):
                item = review_lookup.get(vid)
                if not item:
                    continue
                img_path = Path(img)
                if not img_path.exists():
                    rename_results.append({"原图": img_path.name, "结果": "❌ 文件不存在"})
                    continue
                new_stem = Path(item["output_name"]).stem
                new_path = img_path.with_name(f"{new_stem}{img_path.suffix.lower()}")
                if new_path == img_path:
                    rename_results.append({"原图": img_path.name, "结果": "— 名称相同，跳过"})
                    continue
                if new_path.exists():
                    rename_results.append({"原图": img_path.name, "结果": f"❌ 目标已存在：{new_path.name}"})
                    continue
                try:
                    img_path.rename(new_path)
                    # 同步更新 session state 路径
                    if vid in assignments:
                        assignments[vid]["image"] = str(new_path)
                    if vid in overrides and overrides[vid] == img:
                        overrides[vid] = str(new_path)
                    rename_results.append({"原图": img_path.name, "结果": f"✅ → {new_path.name}"})
                except Exception as e:
                    rename_results.append({"原图": img_path.name, "结果": f"❌ {e}"})
            st.session_state["_image_rename_results"] = rename_results
            st.rerun()

    _rename_done = st.session_state.pop("_image_rename_results", None)
    if _rename_done:
        ok = sum(1 for r in _rename_done if r["结果"].startswith("✅"))
        st.success(f"改名完成：{ok}/{len(_rename_done)} 张成功")
        st.dataframe(_pd_dataframe(_rename_done), use_container_width=True, hide_index=True)
