from __future__ import annotations

from pathlib import Path

import streamlit as st

import gdrive
from image_matching import (
    copy_all_images_preserve_names,
    copy_image_with_new_name,
    find_image_files,
    rename_in_folder,
)
from processing import (
    build_process_items,
    burn_subtitles_for_output,
    detect_existing_outputs,
    infer_mime_type,
    make_result_row,
    result_to_job_record,
    split_existing_process_items,
    successful_upload_file_names,
    verify_output_folder_writable,
    write_job_report,
)
from ui_helpers import _pd_dataframe, desktop_output_folder, set_pending_path
from watermark import add_watermark


def render_export_section(
    paste_data: str,
    videos: dict,
    source_folder: str,
    output_folder: str,
    import_mode: str,
    sidebar_export_btn: bool,
    matched_entries: int,
    match_by_voice: bool,
    match_by_order: bool,
    review_items: list,
    review_statuses: dict,
    review_only_confirmed: bool,
    mapping_entries: list,
    _matched_files,
    _output_name_for,
    _review_id_for,
    watermark_text: str,
    position: str,
    custom_x: int,
    custom_y: int,
    font_size: int,
    font_path: str,
    opacity: float,
    font_color: str,
    quality: int,
    encoder: str,
    volume: float,
) -> None:
    if paste_data and videos:
        st.divider()
        main_export_btn = st.button("🚀 一键导出", key="main_export_btn", use_container_width=True)
        if sidebar_export_btn or main_export_btn:
            st.session_state["pending_export_clicked"] = True
        export_clicked = bool(st.session_state.get("pending_export_clicked", False))

        if matched_entries == 0:
            if match_by_voice:
                st.warning("还没有语音配对结果，请先点击“识别视频语音并自动配对”。")
            elif match_by_order:
                st.warning("没有对应视频，请检查视频数量是否为空。")
            else:
                st.warning("没有匹配到任何视频，请检查关键词是否包含在文件名中。")
        else:
            # ── 确定输出路径 ──
            if output_folder and output_folder.strip():
                out_path = Path(output_folder.strip())
            elif source_folder:
                out_path = Path(source_folder) / "打好水印"
            else:
                out_path = Path.home() / "Downloads" / "打好水印"

            # ── Fix #8: 提前验证写入权限 ──
            path_ok, path_error = verify_output_folder_writable(out_path)
            if not path_ok:
                st.error(f"输出文件夹无法写入：{path_error}\n请切换到一个有权限的文件夹。")
                fallback_cols = st.columns(2)
                output_state_key = (
                    "output_folder_upload_val"
                    if import_mode == "拖拽上传视频"
                    else "output_folder_path_val"
                )
                with fallback_cols[0]:
                    if st.button("改用桌面/打好水印", use_container_width=True, key="fallback_desktop_output"):
                        set_pending_path(output_state_key, desktop_output_folder())
                with fallback_cols[1]:
                    if source_folder and st.button("改用原视频目录/打好水印", use_container_width=True, key="fallback_source_output"):
                        set_pending_path(output_state_key, str(Path(source_folder) / "打好水印"))

            # ── 覆盖检测（支持多匹配） ──
            if path_ok:
                process_items = build_process_items(
                    mapping_entries,
                    _matched_files,
                    _output_name_for,
                    _review_id_for,
                    review_statuses,
                    out_path,
                    review_only_confirmed=review_only_confirmed,
                )
                skipped_existing_items = []

                if review_only_confirmed and not process_items:
                    st.warning("还没有确认通过的配对。请在“人工复核”里确认至少一个视频，或者关闭“只处理已确认通过的配对”。")

                existing_files = detect_existing_outputs(process_items)

                if existing_files:
                    st.warning(
                        f"以下 {len(existing_files)} 个文件已存在：\n"
                        + "\n".join(f"• {f}" for f in existing_files[:5])
                        + ("…" if len(existing_files) > 5 else "")
                    )
                    skip_existing_outputs = st.checkbox(
                        "跳过已存在的输出文件（推荐）",
                        value=True,
                        key="skip_existing_outputs",
                    )
                    if skip_existing_outputs:
                        process_items, skipped_existing_items = split_existing_process_items(
                            process_items,
                        )
                        if skipped_existing_items:
                            st.info(f"已跳过 {len(skipped_existing_items)} 个已存在的输出。")
                        overwrite_confirmed = True
                    else:
                        overwrite_confirmed = st.checkbox("我已确认，允许覆盖")
                else:
                    overwrite_confirmed = True

                st.markdown(
                    f'<div class="info-bar info-bar-blue" style="margin-bottom:10px;">'
                    f'<span>📂</span>'
                    f'<span>输出到：<code style="background:transparent;font-family:ui-monospace,\'SF Mono\',monospace;">{out_path}</code></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                move_to_trash = st.checkbox(
                    "🗑️ 处理完成后将原文件移至 macOS 回收站",
                    value=True,
                    key="move_to_trash",
                    help="仅移动成功打水印的原始视频，未成功的文件不会被移动。可从回收站恢复。",
                )
                burn_subtitles = st.checkbox(
                    "烧录字幕（Hormozi 风格）",
                    key="burn_subtitles",
                )

                total_action_items = len(process_items) + len(skipped_existing_items)
                if total_action_items and path_ok and overwrite_confirmed and export_clicked:
                    st.session_state.pop("pending_export_clicked", None)
                    out_path.mkdir(parents=True, exist_ok=True)
                    progress = st.progress(0)
                    status_text = st.empty()
                    results = []
                    job_records = []

                    _img_assignments = (st.session_state.get("image_match_result") or {}).get("assignments", {})
                    _img_overrides = st.session_state.get("image_match_overrides", {})
                    _img_finalized = st.session_state.get("image_match_finalized", {})
                    def _image_for_review_id(rid: str) -> str | None:
                        # 优先级：锁定的 > 本轮 override > 本轮自动匹配
                        if rid in _img_finalized:
                            return _img_finalized[rid]
                        if rid in _img_overrides:
                            return _img_overrides[rid]
                        info = _img_assignments.get(rid)
                        return info.get("image") if info else None

                    image_dest_folder = out_path / "原图-已匹配"
                    image_copy_results = []

                    # 批量复制所有原图（保留原名）
                    _src_image_folder = (st.session_state.get("source_image_folder") or "").strip()
                    bulk_image_map: dict[str, Path] = {}
                    if _src_image_folder and find_image_files(_src_image_folder):
                        try:
                            bulk_image_map = copy_all_images_preserve_names(
                                Path(_src_image_folder), image_dest_folder,
                            )
                        except Exception as bulk_err:
                            st.warning(f"批量复制原图时出错：{bulk_err}")

                    for skipped_item in skipped_existing_items:
                        skipped_row = make_result_row(
                            skipped_item,
                            success=True,
                            skipped=True,
                        )
                        results.append(skipped_row)
                        job_records.append(result_to_job_record(skipped_item, skipped_row))

                    total = len(process_items)
                    done = 0
                    for item in process_items:
                        video_file = item["video_file"]
                        output_file = item["output_file"]

                        status_text.markdown(
                            f'<div class="info-bar info-bar-blue">'
                            f'<span>⚙️</span>'
                            f'<span>正在处理 ({done+1}/{total})：{video_file.name}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        success, error = add_watermark(
                            input_path=str(video_file),
                            output_path=str(output_file),
                            text=watermark_text,
                            position=position,
                            font_size=font_size,
                            opacity=opacity,
                            font_color=font_color,
                            font_path=font_path,
                            quality=quality,
                            custom_x=custom_x,
                            custom_y=custom_y,
                            encoder=encoder,
                            volume=volume,
                        )

                        if success and burn_subtitles:
                            status_text.markdown(
                                f'<div class="info-bar info-bar-blue">'
                                f'<span>⚙️</span>'
                                f'<span>正在烧录字幕 ({done+1}/{total})：{video_file.name}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                            success, error = burn_subtitles_for_output(
                                output_file,
                                burn_subtitles=burn_subtitles,
                            )

                        if success:
                            src_image = _image_for_review_id(item.get("review_id", ""))
                            if src_image:
                                try:
                                    # 先看是否已经在批量复制里——若是则就地改名；否则补做一次复制+改名
                                    copied_in_dest = bulk_image_map.get(src_image)
                                    if copied_in_dest and copied_in_dest.exists():
                                        copied = rename_in_folder(copied_in_dest, output_file.stem)
                                    else:
                                        copied = copy_image_with_new_name(
                                            Path(src_image), image_dest_folder, output_file.stem,
                                        )
                                    image_copy_results.append({
                                        "视频": output_file.name,
                                        "原图": Path(src_image).name,
                                        "改名为": copied.name,
                                        "结果": "✅",
                                    })
                                except Exception as img_err:
                                    image_copy_results.append({
                                        "视频": output_file.name,
                                        "原图": Path(src_image).name,
                                        "改名为": "—",
                                        "结果": f"❌ {img_err}",
                                    })

                        done += 1
                        progress.progress(done / total)
                        result_row = make_result_row(
                            item,
                            success=success,
                            error=error,
                        )
                        results.append(result_row)
                        job_records.append(result_to_job_record(item, result_row))

                    status_text.empty()
                    progress.empty()

                    succeeded = sum(1 for r in results if "✅" in r["结果"])
                    skipped = sum(1 for r in results if "⏭️" in r["结果"])
                    failed = sum(1 for r in results if "❌" in r["结果"])

                    st.markdown('<div class="section-title">处理结果</div>', unsafe_allow_html=True)
                    ra, rb, rc = st.columns(3)
                    ra.metric("✅ 成功", succeeded)
                    rb.metric("⏭️ 跳过", skipped)
                    rc.metric("❌ 失败", failed)

                    st.dataframe(_pd_dataframe(results), use_container_width=True, hide_index=True)

                    if bulk_image_map or image_copy_results:
                        st.markdown('<div class="subsection-title">🖼️ 原图处理结果</div>', unsafe_allow_html=True)
                        renamed_count = sum(1 for r in image_copy_results if r["结果"] == "✅")
                        kept_count = len(bulk_image_map) - renamed_count
                        st.caption(
                            f"已复制全部原图到：{image_dest_folder}（共 {len(bulk_image_map)} 张；其中 {renamed_count} 张按视频改名，{kept_count} 张保留原名）"
                        )
                        if image_copy_results:
                            st.dataframe(_pd_dataframe(image_copy_results), use_container_width=True, hide_index=True)

                    if failed:
                        st.warning(f"{failed} 个文件处理失败，请查看上方结果表格。")

                    st.markdown(
                        f'<div class="info-bar info-bar-green" style="margin-top:8px;">'
                        f'<span>📂</span>'
                        f'<span style="font-weight:500;">输出文件夹：</span>'
                        f'<code style="background:transparent;font-family:ui-monospace,\'SF Mono\',monospace;font-size:13px;">{out_path}</code>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    try:
                        _job_path, report_csv_path = write_job_report(out_path, job_records)
                        st.markdown(
                            f'<div class="info-bar info-bar-green" style="margin-top:8px;">'
                            f'<span>🧾</span>'
                            f'<span>已保存处理记录：<b>{report_csv_path.name}</b></span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    except Exception as e:
                        st.warning(f"处理结果报告写入失败：{e}")

                    # ── 移动原文件到回收站 ──
                    if move_to_trash and succeeded > 0:
                        try:
                            from send2trash import send2trash as _send2trash
                        except ImportError:
                            st.warning("⚠️ 未安装 send2trash，请运行：pip3 install --break-system-packages send2trash")
                            _send2trash = None

                        if _send2trash:
                            trashed, trash_failed = [], []
                            # 收集成功处理的原始文件路径
                            success_originals = set()
                            for r in results:
                                if "✅" in r["结果"]:
                                    success_originals.add(r["原文件"])

                            for item in process_items:
                                video_file = item["video_file"]
                                if video_file.name not in success_originals:
                                    continue
                                # 拖拽模式：原文件在 source_folder 下，videos 里是 temp 副本
                                if import_mode == "拖拽上传视频" and source_folder:
                                    orig = Path(source_folder) / video_file.name
                                else:
                                    orig = video_file
                                if not orig.exists():
                                    continue
                                try:
                                    _send2trash(str(orig))
                                    trashed.append(orig.name)
                                except Exception as e:
                                    trash_failed.append(f"{orig.name}：{e}")

                            if trashed:
                                st.markdown(
                                    f'<div class="info-bar info-bar-yellow" style="margin-top:8px;">'
                                    f'<span>🗑️</span>'
                                    f'<span>已将 <b>{len(trashed)}</b> 个原文件移至回收站</span>'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )
                            if trash_failed:
                                st.warning("以下文件移至回收站失败：\n" + "\n".join(f"• {f}" for f in trash_failed))

                    st.balloons()

                    successful_files = [r for r in results if "✅" in r["结果"]]
                    if successful_files:
                        upload_file_names = successful_upload_file_names(successful_files)
                        st.session_state["pending_drive_upload"] = {
                            "out_path": str(out_path),
                            "files": upload_file_names,
                            "folder_name": out_path.name,
                        }

    pending_drive_upload = st.session_state.get("pending_drive_upload")
    if pending_drive_upload and gdrive.is_authenticated():
        st.divider()
        st.markdown('<div class="section-title">☁️ 上传到 Google Drive</div>', unsafe_allow_html=True)

        upload_file_names = pending_drive_upload.get("files", [])
        folder_name_hint = pending_drive_upload.get("folder_name", "")
        st.info(f"待上传 {len(upload_file_names)} 个文件到 Drive 文件夹「{folder_name_hint}」。")

        upload_col, cancel_col = st.columns(2)
        with upload_col:
            upload_pending_drive = st.button("上传到 Drive", use_container_width=True, key="upload_pending_drive")
        with cancel_col:
            cancel_pending_drive = st.button("取消上传", use_container_width=True, key="cancel_pending_drive")

        if cancel_pending_drive:
            st.session_state.pop("pending_drive_upload", None)
            st.rerun()

        if upload_pending_drive:
            out_path = Path(pending_drive_upload["out_path"])
            target_folder_id = st.session_state.get("drive_target_folder_id")
            target_folder_name = st.session_state.get("drive_target_folder_name", "")

            if target_folder_id:
                folder_id = target_folder_id
                folder_name = target_folder_name
            else:
                folder_name = folder_name_hint or out_path.name
                with st.spinner(f"正在 Drive 新建文件夹「{folder_name}」…"):
                    folder_id = gdrive.create_folder(folder_name)

            if not folder_id:
                st.error("Drive 文件夹不可用，请在侧边栏选择或新建一个文件夹")
            else:
                gdrive.make_shareable(folder_id)
                link = gdrive.folder_link(folder_id)

                up_progress = st.progress(0)
                up_status = st.empty()
                upload_results = []

                for i, file_name in enumerate(upload_file_names):
                    file_path = out_path / file_name
                    up_status.markdown(
                        f'<div class="info-bar info-bar-blue">'
                        f'<span>☁️</span>'
                        f'<span>上传中 ({i+1}/{len(upload_file_names)})：{file_name}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    ok, err = gdrive.upload_file(
                        str(file_path),
                        folder_id,
                        mime_type=infer_mime_type(file_path),
                    )
                    upload_results.append({
                        "文件": file_name,
                        "上传": "✅" if ok else f"❌ {err}",
                    })
                    up_progress.progress((i + 1) / len(upload_file_names))

                up_status.empty()
                up_progress.empty()

                up_ok = sum(1 for r in upload_results if "✅" in r["上传"])
                st.dataframe(_pd_dataframe(upload_results), use_container_width=True, hide_index=True)

                # 复制链接到剪贴板，并存入 session_state 常驻显示
                gdrive.copy_to_clipboard(link)
                st.session_state["last_drive_link"] = link
                st.session_state["last_drive_folder"] = folder_name
                st.session_state["last_drive_count"] = f"{up_ok}/{len(upload_file_names)}"

                st.markdown(
                    f'<div style="background:#fff;border-radius:16px;padding:16px 18px;'
                    f'border:0.5px solid rgba(0,122,255,0.25);'
                    f'box-shadow:0 1px 4px rgba(0,0,0,0.07);">'
                    f'<div style="font-weight:600;color:#1D1D1F;font-size:15px;margin-bottom:6px;">'
                    f'☁️ 上传完成 — {up_ok}/{len(upload_file_names)} 个文件 → {folder_name}</div>'
                    f'<div style="font-size:13px;color:#8E8E93;margin-bottom:6px;">📋 Drive 文件夹链接已复制到剪贴板</div>'
                    f'<a href="{link}" target="_blank" style="font-size:13px;color:#007AFF;text-decoration:none;">{link}</a>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.session_state.pop("pending_drive_upload", None)
                st.rerun()

    if paste_data and not videos:
        st.markdown(
            '<div class="info-bar info-bar-orange">'
            '<span>⚠️</span><span>请先上传视频或输入视频文件夹路径</span>'
            '</div>',
            unsafe_allow_html=True,
        )


