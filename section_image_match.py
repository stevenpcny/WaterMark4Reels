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
    # ── 4️⃣ 图片配对（可选） ──
    _image_folder = (st.session_state.get("source_image_folder") or "").strip()
    if _image_folder and find_image_files(_image_folder):
        st.divider()
        st.markdown('<div class="section-title">4️⃣ 图片配对（可选）</div>', unsafe_allow_html=True)
        st.caption("用感知哈希在视频中段抽帧 → 与原图对比。对 talking-head 动画做了适配，仍可能误判，请人工复核。")

        _img_videos_for_match = []
        for item in review_items:
            if review_only_confirmed and review_statuses.get(item["id"]) != "confirmed":
                continue
            _img_videos_for_match.append(item)

        # 跨轮锁定的匹配：{review_id: image_path}
        finalized: dict[str, str] = st.session_state.setdefault("image_match_finalized", {})
        all_image_paths = find_image_files(_image_folder)
        all_image_set = {str(p) for p in all_image_paths}
        # 清理已失效的锁定（图片删了或视频不在了）
        valid_vids = {it["id"] for it in review_items}
        for k in list(finalized.keys()):
            if k not in valid_vids or finalized[k] not in all_image_set:
                finalized.pop(k, None)
        locked_videos = set(finalized.keys())
        locked_images = set(finalized.values())

        remaining_videos = [it for it in _img_videos_for_match if it["id"] not in locked_videos]
        remaining_images = [p for p in all_image_paths if str(p) not in locked_images]

        match_btn_cols = st.columns([2, 1, 1])
        with match_btn_cols[0]:
            do_image_match = st.button(
                f"🖼️ 配对原图（剩余 {len(remaining_videos)} 视频 × {len(remaining_images)} 图，已锁定 {len(finalized)}）",
                use_container_width=True,
                key="run_image_match_btn",
                disabled=not remaining_videos or not remaining_images,
            )
        with match_btn_cols[1]:
            accept_round_btn = st.button(
                "✅ 锁定本轮并匹配剩余",
                use_container_width=True,
                key="accept_round_btn",
                disabled="image_match_result" not in st.session_state,
                help="把当前显示的匹配（含手动指认）全部锁定，下一轮只对剩余视频和剩余图片重新匹配。",
            )
        with match_btn_cols[2]:
            if st.button("🗑️ 全部清空", use_container_width=True, key="clear_image_match_btn"):
                st.session_state.pop("image_match_result", None)
                st.session_state.pop("image_match_overrides", None)
                st.session_state.pop("image_match_last_fingerprint", None)
                st.session_state.pop("image_match_finalized", None)
                st.rerun()

        # 处理"锁定本轮"：把当前 final 写入 finalized，清掉本轮结果，下一轮会自动跑
        if accept_round_btn:
            _cur_result = st.session_state.get("image_match_result", {})
            _cur_assignments = _cur_result.get("assignments", {})
            _cur_overrides = st.session_state.get("image_match_overrides", {})
            for vid, info in _cur_assignments.items():
                img = _cur_overrides.get(vid, info.get("image"))
                if img and img in all_image_set:
                    finalized[vid] = img
            st.session_state.pop("image_match_result", None)
            st.session_state.pop("image_match_overrides", None)
            st.session_state.pop("image_match_last_fingerprint", None)
            st.rerun()

        # 自动原图匹配：未复核视频不参与；fingerprint 变化时跑一次
        _auto_run_enabled = bool(st.session_state.get("image_match_auto_run", True))
        _auto_run_videos = [
            it for it in review_items
            if review_statuses.get(it["id"]) == "confirmed" and it["id"] not in locked_videos
        ]
        _auto_thr_now = int(st.session_state.get("image_match_auto_threshold", 18))
        _review_thr_now = int(st.session_state.get("image_match_review_threshold", 24))
        _auto_fp = (
            _image_folder,
            tuple(sorted(it["id"] for it in _auto_run_videos)),
            tuple(sorted(locked_videos)),
            _auto_thr_now,
            _review_thr_now,
        )
        _last_fp = st.session_state.get("image_match_last_fingerprint")
        _auto_trigger = (
            _auto_run_enabled
            and _auto_run_videos
            and remaining_images
            and _auto_fp != _last_fp
        )

        if do_image_match and remaining_videos and remaining_images:
            _videos_to_match = remaining_videos
            _run_match = True
        elif _auto_trigger:
            _videos_to_match = _auto_run_videos
            _run_match = True
            st.info(f"🖼️ 自动原图匹配中（{len(_auto_run_videos)} 个已复核视频 × {len(remaining_images)} 张剩余图）...")
        else:
            _videos_to_match = []
            _run_match = False

        if _run_match:
            auto_thr = _auto_thr_now
            review_thr = _review_thr_now
            progress = st.progress(0)
            status_text = st.empty()
            work_dir = make_frame_workdir()
            try:
                image_paths = remaining_images  # 只用未锁定的图
                image_hashes: dict[str, tuple[str, str]] = {}
                total_imgs = len(image_paths)
                for idx, img_path in enumerate(image_paths):
                    status_text.write(f"算图片哈希 {idx+1}/{total_imgs}：{img_path.name}")
                    h = hash_image(img_path)
                    if h:
                        image_hashes[str(img_path)] = h
                    progress.progress((idx + 1) / max(1, total_imgs + len(_videos_to_match)))

                video_hashes: dict[str, list[tuple[str, str]]] = {}
                for vidx, item in enumerate(_videos_to_match):
                    status_text.write(f"抽帧并哈希 {vidx+1}/{len(_videos_to_match)}：{item['video_file'].name}")
                    vh = hash_video_frames(item["video_file"], work_dir)
                    if vh:
                        video_hashes[item["id"]] = vh
                    progress.progress((total_imgs + vidx + 1) / max(1, total_imgs + len(_videos_to_match)))

                result = assign_videos_to_images(
                    video_hashes, image_hashes,
                    auto_threshold=auto_thr,
                    review_threshold=review_thr,
                )
                st.session_state["image_match_result"] = result
                st.session_state["image_match_video_ids"] = [it["id"] for it in _videos_to_match]
                st.session_state["image_match_overrides"] = {}
                st.session_state["image_match_last_fingerprint"] = _auto_fp
            finally:
                try:
                    import shutil as _sh
                    _sh.rmtree(work_dir, ignore_errors=True)
                except Exception:
                    pass
                status_text.empty()
                progress.empty()

        _result = st.session_state.get("image_match_result") or {"assignments": {}, "conflicts": []}
        assignments = dict(_result.get("assignments", {}))
        overrides = st.session_state.setdefault("image_match_overrides", {})
        final_map: dict[str, str | None] = {}
        for vid, info in assignments.items():
            final_map[vid] = overrides.get(vid, info.get("image"))

        # 统计
        locked_n = len(finalized)
        auto_n = sum(1 for v, info in assignments.items() if info["status"] == "auto" and overrides.get(v, info["image"]))
        review_n = sum(1 for v, info in assignments.items() if info["status"] == "review")
        unmatched_n = sum(1 for v in assignments if not final_map.get(v))

        if finalized or assignments:
            st.markdown(
                f"""
                <div class="workflow-stats">
                  <div class="workflow-stat"><span>🔒 已锁定</span><strong>{locked_n}</strong></div>
                  <div class="workflow-stat"><span>自动匹配</span><strong>{auto_n}</strong></div>
                  <div class="workflow-stat"><span>需复核</span><strong>{review_n}</strong></div>
                  <div class="workflow-stat"><span>未匹配</span><strong>{unmatched_n}</strong></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 不依赖 _result 也要能显示已锁定行
        review_lookup_outer = {it["id"]: it for it in review_items}

        if _result and assignments:

            # 冲突卡片
            conflicts = _result.get("conflicts", [])
            real_conflicts = [
                c for c in conflicts
                if len([cand for cand in c["candidates"]
                        if final_map.get(cand["video"]) == c["image"]]) > 1
            ]
            if real_conflicts:
                st.markdown('<div class="subsection-title">⚠️ 冲突：多个视频指向同一张图</div>', unsafe_allow_html=True)
                for ci, conf in enumerate(real_conflicts):
                    img_name = Path(conf["image"]).name
                    cand_videos = conf["candidates"]
                    options = ["（都不选，全部跳过）"] + [
                        f"{next((it['video_file'].name for it in review_items if it['id'] == c['video']), c['video'])}（距离 {c['distance']}）"
                        for c in cand_videos
                    ]
                    chosen = st.radio(
                        f"图片 {img_name}：保留哪个视频对应它？",
                        options=list(range(len(options))),
                        format_func=lambda i: options[i],
                        key=f"conflict_resolve_{ci}_{img_name}",
                    )
                    if chosen == 0:
                        for c in cand_videos:
                            overrides[c["video"]] = None
                    else:
                        winner = cand_videos[chosen - 1]["video"]
                        for c in cand_videos:
                            if c["video"] == winner:
                                overrides[c["video"]] = conf["image"]
                            elif final_map.get(c["video"]) == conf["image"]:
                                overrides[c["video"]] = None

            # 主表格
            table_rows = []
            review_lookup = {it["id"]: it for it in review_items}
            # 已锁定的行
            for vid, img in finalized.items():
                item = review_lookup.get(vid)
                if not item:
                    continue
                table_rows.append({
                    "视频": item["video_file"].name,
                    "新文件名": item["output_name"],
                    "原图": Path(img).name,
                    "距离": "—",
                    "状态": "🔒 已锁定",
                })
            # 本轮结果
            for vid, info in assignments.items():
                item = review_lookup.get(vid)
                if not item:
                    continue
                final_img = overrides.get(vid, info["image"])
                status_label = {
                    "auto": "✅ 自动",
                    "review": "🟡 需复核",
                    "unmatched": "❌ 未匹配",
                }[info["status"]]
                if final_img is None and info["image"] is not None:
                    status_label = "🚫 已跳过"
                table_rows.append({
                    "视频": item["video_file"].name,
                    "新文件名": item["output_name"],
                    "原图": Path(final_img).name if final_img else "—",
                    "距离": info["distance"] if info["distance"] is not None else "—",
                    "状态": status_label,
                })
            if table_rows:
                st.dataframe(_pd_dataframe(table_rows), use_container_width=True, hide_index=True)

            # 手动指认
            with st.expander("✋ 手动指认 / 修改某个视频的图片", expanded=False):
                vid_options = list(assignments.keys())
                if vid_options:
                    sel_vid = st.selectbox(
                        "选择视频",
                        vid_options,
                        format_func=lambda v: review_lookup[v]["video_file"].name if v in review_lookup else v,
                        key="manual_image_pick_vid",
                    )
                    image_paths_all = find_image_files(_image_folder)
                    img_options = ["（不配对）"] + [str(p) for p in image_paths_all]
                    current_img = overrides.get(sel_vid, assignments[sel_vid].get("image"))
                    try:
                        default_idx = img_options.index(current_img) if current_img else 0
                    except ValueError:
                        default_idx = 0
                    sel_img = st.selectbox(
                        "对应图片",
                        img_options,
                        index=default_idx,
                        format_func=lambda p: "（不配对）" if p == "（不配对）" else Path(p).name,
                        key="manual_image_pick_img",
                    )
                    if st.button("应用", key="apply_manual_image_pick"):
                        overrides[sel_vid] = None if sel_img == "（不配对）" else sel_img
                        st.rerun()

        # 没有本轮结果但已有锁定 → 仍要展示已锁定列表 + 解锁入口
        if finalized and not (_result and assignments):
            locked_rows = []
            for vid, img in finalized.items():
                item = review_lookup_outer.get(vid)
                if not item:
                    continue
                locked_rows.append({
                    "视频": item["video_file"].name,
                    "新文件名": item["output_name"],
                    "原图": Path(img).name,
                    "状态": "🔒 已锁定",
                })
            if locked_rows:
                st.dataframe(_pd_dataframe(locked_rows), use_container_width=True, hide_index=True)

        if finalized:
            with st.expander("🔓 解锁某个已锁定的匹配", expanded=False):
                unlock_options = list(finalized.keys())
                sel_unlock = st.selectbox(
                    "选择要解锁的视频",
                    unlock_options,
                    format_func=lambda v: review_lookup_outer[v]["video_file"].name if v in review_lookup_outer else v,
                    key="unlock_pick_vid",
                )
                if st.button("解锁", key="unlock_apply_btn"):
                    finalized.pop(sel_unlock, None)
                    st.rerun()
