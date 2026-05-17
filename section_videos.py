from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

from image_matching import find_image_files
from ui_helpers import desktop_output_folder, pick_folder_into, set_pending_path
from watermark import find_video_files


def render_videos_section() -> dict:
    st.markdown('<div class="section-title">1️⃣ 导入视频</div>', unsafe_allow_html=True)
    default_downloads = str(Path.home() / "Downloads")
    default_output_folder = str(Path.home() / "Downloads" / "打好水印")
    if "source_folder_upload_val" not in st.session_state:
        st.session_state["source_folder_upload_val"] = default_downloads
    if "output_folder_upload_val" not in st.session_state:
        st.session_state["output_folder_upload_val"] = default_output_folder
    st.session_state.setdefault("output_folder_path_val", default_output_folder)
    st.session_state.setdefault("video_folder_path", "")
    st.session_state.setdefault("last_known_source_signature", None)
    for path_key in (
        "source_folder_upload_val",
        "output_folder_upload_val",
        "output_folder_path_val",
        "video_folder_path",
        "source_image_folder",
        "drive_local_upload_folder",
    ):
        pending_key = f"pending_{path_key}"
        if pending_key in st.session_state:
            st.session_state[path_key] = st.session_state.pop(pending_key)

    import_mode = st.radio(
        "导入方式",
        ["拖拽上传视频", "输入文件夹路径"],
        horizontal=True,
        label_visibility="collapsed",
        key="import_mode",
    )

    uploaded_video_paths = {}
    source_folder = None

    if import_mode == "拖拽上传视频":
        uploaded_video_paths = {
            stem: Path(path)
            for stem, path in st.session_state.get("uploaded_video_path_cache", {}).items()
            if Path(path).exists()
        }
        uploaded_files = st.file_uploader(
            "拖拽或点击选择视频文件",
            type=["mp4", "mov", "avi", "mkv", "webm"],
            accept_multiple_files=True,
        )
        if uploaded_files:
            upload_dir = os.path.join(tempfile.gettempdir(), "reels_watermark_uploads")
            os.makedirs(upload_dir, exist_ok=True)
            new_names = {uf.name for uf in uploaded_files}
            if new_names != st.session_state.get("uploaded_names", set()):
                st.session_state["uploaded_names"] = new_names
            for uf in uploaded_files:
                save_path = os.path.join(upload_dir, uf.name)
                with open(save_path, "wb") as f:
                    f.write(uf.getbuffer())
                uploaded_video_paths[Path(uf.name).stem] = Path(save_path)
            st.session_state["uploaded_video_path_cache"] = {
                stem: str(path) for stem, path in uploaded_video_paths.items()
            }

        if uploaded_video_paths:
            st.markdown(
                f'<div class="info-bar info-bar-green">'
                f'<span>✅</span>'
                f'<span style="font-weight:500;">当前已保留 {len(uploaded_video_paths)} 个上传视频</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("清空已上传视频", use_container_width=True, key="clear_uploaded_video_cache"):
                st.session_state.pop("uploaded_video_path_cache", None)
                st.session_state.pop("uploaded_names", None)
                st.session_state.pop("voice_match_result", None)
                st.rerun()

        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
        st.markdown("**📁 原视频所在目录**", unsafe_allow_html=False)
        src_col1, src_col2 = st.columns([5, 1])
        with src_col1:
            source_folder_input = st.text_input(
                "原视频目录", label_visibility="collapsed",
                placeholder="/Users/你的用户名/Downloads",
                key="source_folder_upload_val",
            )
        with src_col2:
            if st.button("📂", help="选择文件夹", key="pick_source_upload"):
                pick_folder_into("source_folder_upload_val")
        source_folder = st.session_state.get("source_folder_upload_val", "").strip() or None

        st.markdown("**📂 成品文件夹** <span style='color:#94a3b8;font-size:0.8rem;'>（建议单独放打好水印的视频）</span>", unsafe_allow_html=True)
        out_col1, out_col2 = st.columns([5, 1])
        with out_col1:
            output_folder = st.text_input(
                "输出路径", label_visibility="collapsed",
                placeholder="/Users/你的用户名/Downloads/打好水印",
                key="output_folder_upload_val",
            )
        with out_col2:
            if st.button("📂", help="选择文件夹", key="pick_out_upload"):
                pick_folder_into("output_folder_upload_val")
        quick_out_cols = st.columns(2)
        with quick_out_cols[0]:
            if st.button("用桌面/打好水印", use_container_width=True, key="use_desktop_output_upload"):
                set_pending_path("output_folder_upload_val", desktop_output_folder())
        with quick_out_cols[1]:
            if st.button("用原视频目录/打好水印", use_container_width=True, key="use_source_output_upload"):
                if source_folder:
                    set_pending_path("output_folder_upload_val", str(Path(source_folder) / "打好水印"))
                else:
                    st.warning("请先填写原视频所在目录。")

    else:
        st.markdown("**📁 视频文件夹**")
        vf_col1, vf_col2 = st.columns([5, 1])
        with vf_col1:
            video_folder = st.text_input(
                "视频路径", label_visibility="collapsed",
                placeholder="/Users/你的用户名/Videos/reels",
                key="video_folder_path",
            )
        with vf_col2:
            if st.button("📂", help="选择文件夹", key="pick_video"):
                pick_folder_into("video_folder_path")

        if video_folder:
            uploaded_video_paths = find_video_files(video_folder)
            source_folder = video_folder
            if uploaded_video_paths:
                st.markdown(
                    f'<div class="info-bar info-bar-green">'
                    f'<span>✅</span>'
                    f'<span style="font-weight:500;">找到 {len(uploaded_video_paths)} 个视频文件</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="info-bar info-bar-orange">'
                    '<span>⚠️</span><span>该文件夹中没有找到视频文件</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
        st.markdown("**📂 成品文件夹** <span style='color:#94a3b8;font-size:0.8rem;'>（建议单独放打好水印的视频）</span>", unsafe_allow_html=True)
        of_col1, of_col2 = st.columns([5, 1])
        with of_col1:
            output_folder = st.text_input(
                "输出路径", label_visibility="collapsed",
                placeholder="/Users/你的用户名/Downloads/打好水印",
                key="output_folder_path_val",
            )
        with of_col2:
            if st.button("📂", help="选择文件夹", key="pick_out_folder"):
                pick_folder_into("output_folder_path_val")
        quick_out_cols = st.columns(2)
        with quick_out_cols[0]:
            if st.button("用桌面/打好水印", use_container_width=True, key="use_desktop_output_folder"):
                set_pending_path("output_folder_path_val", desktop_output_folder())
        with quick_out_cols[1]:
            if st.button("用视频文件夹/打好水印", use_container_width=True, key="use_video_output_folder"):
                if video_folder:
                    set_pending_path("output_folder_path_val", str(Path(video_folder) / "打好水印"))
                else:
                    st.warning("请先填写视频文件夹。")

    videos = uploaded_video_paths

    # ── 原图文件夹（可选） ──
    _has_image_folder = bool((st.session_state.get("source_image_folder") or "").strip())
    with st.expander("🖼️ 原图文件夹（可选，配对后自动重命名复制）", expanded=_has_image_folder):
        img_col1, img_col2 = st.columns([5, 1])
        with img_col1:
            source_image_folder = st.text_input(
                "原图文件夹路径", label_visibility="collapsed",
                placeholder="/Users/你的用户名/Pictures/原图",
                key="source_image_folder",
            )
        with img_col2:
            if st.button("📂", help="选择文件夹", key="pick_image_folder"):
                pick_folder_into("source_image_folder")
        if source_image_folder:
            _imgs_preview = find_image_files(source_image_folder)
            if _imgs_preview:
                st.markdown(
                    f'<div class="info-bar info-bar-green">'
                    f'<span>✅</span><span style="font-weight:500;">找到 {len(_imgs_preview)} 张原图</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="info-bar info-bar-orange">'
                    '<span>⚠️</span><span>该文件夹中没有找到图片</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )

    def _source_state_snapshot() -> dict:
        return {
            "import_mode": st.session_state.get("import_mode", import_mode),
            "source_folder_upload_val": st.session_state.get("source_folder_upload_val", ""),
            "video_folder_path": st.session_state.get("video_folder_path", ""),
            "uploaded_names": set(st.session_state.get("uploaded_names", set())),
            "uploaded_video_path_cache": dict(st.session_state.get("uploaded_video_path_cache", {})),
        }

    def _clear_source_scan_state() -> None:
        preserved_paste_data = st.session_state.get("paste_data", "")
        for state_key in (
            "review_statuses",
            "manual_video_assignments",
            "active_review_video",
            "voice_match_result",
            "image_match_result",
            "image_match_overrides",
        ):
            st.session_state.pop(state_key, None)
        st.session_state["paste_data"] = preserved_paste_data

    if import_mode == "拖拽上传视频":
        current_signature = str(hash(tuple(sorted(path.name for path in uploaded_video_paths.values()))))
    else:
        current_signature = str(source_folder or "")

    last_signature = st.session_state.get("last_known_source_signature")
    has_review_state = bool(st.session_state.get("review_statuses")) or bool(st.session_state.get("manual_video_assignments"))
    if last_signature is None or last_signature == current_signature or not has_review_state:
        st.session_state["last_known_source_signature"] = current_signature
        st.session_state["_last_known_source_values"] = _source_state_snapshot()
        st.session_state.pop("_pending_source_rollback", None)
    else:
        if "_pending_source_rollback" not in st.session_state:
            st.session_state["_pending_source_rollback"] = st.session_state.get("_last_known_source_values", _source_state_snapshot())
        st.warning("源视频已变化。继续会清空旧审核状态和手动匹配；也可以撤销这次切换。")
        clear_col, rollback_col = st.columns(2)
        with clear_col:
            if st.button("🗑️ 清空旧审核状态（继续）", use_container_width=True, key="clear_old_review_state_btn"):
                _clear_source_scan_state()
                st.session_state["last_known_source_signature"] = current_signature
                st.session_state["_last_known_source_values"] = _source_state_snapshot()
                st.session_state.pop("_pending_source_rollback", None)
                st.rerun()
        with rollback_col:
            if st.button("↩️ 撤销切换", use_container_width=True, key="rollback_source_change_btn"):
                rollback_values = st.session_state.get("_pending_source_rollback", {})
                for rollback_key, rollback_value in rollback_values.items():
                    st.session_state[rollback_key] = rollback_value
                st.session_state.pop("_pending_source_rollback", None)
                st.rerun()

    return {
        "videos": videos,
        "source_folder": source_folder,
        "output_folder": output_folder,
        "import_mode": import_mode,
    }
