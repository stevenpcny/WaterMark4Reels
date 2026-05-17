from __future__ import annotations

import os
import time
from pathlib import Path

import streamlit as st

import gdrive
from presets import get_preset_settings, load_all, rename_preset, save_last_used, save_preset
from processing import infer_mime_type
from ui_helpers import MATCH_MODE_OPTIONS, pick_folder_into
from watermark import check_videotoolbox, get_available_fonts


def render_sidebar(DEFAULT_SETTINGS: dict) -> dict:
    with st.sidebar:
        st.markdown("""
        <div style="padding:4px 0 18px;">
          <div style="font-size:20px;font-weight:700;color:#1D1D1F;letter-spacing:-0.4px;
                      font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',sans-serif;">
            🎬 水印工具
          </div>
          <div style="font-size:12px;color:#8E8E93;margin-top:3px;font-weight:400;">
            Reels 批量处理
          </div>
        </div>
        """, unsafe_allow_html=True)

        def settings_match(*terms: str) -> bool:
            return True

        def settings_expanded(*terms: str, default: bool = False) -> bool:
            return default

        st.markdown("### 水印参数")

        # ── 常用水印设置 ──
        with st.expander("常用设置", expanded=True):
            watermark_text = st.text_input("水印文字", key="watermark_text", placeholder="输入水印内容…")

            position = st.selectbox(
                "水印位置",
                ["右下", "左下", "右上", "左上", "居中", "自定义"],
                index=["右下", "左下", "右上", "左上", "居中", "自定义"].index(
                    st.session_state.get("position", "右下")
                ),
                key="position",
            )
            custom_x = custom_y = None
            if position == "自定义":
                with st.expander("自定义水印坐标", expanded=True):
                    st.caption("X/Y 为像素值，(0,0) 为左上角")
                    c1, c2 = st.columns(2)
                    with c1:
                        custom_x = st.number_input("X", min_value=0, max_value=3840, key="custom_x", label_visibility="collapsed")
                        st.caption("← X")
                    with c2:
                        custom_y = st.number_input("Y", min_value=0, max_value=2160, key="custom_y", label_visibility="collapsed")
                        st.caption("← Y")
            else:
                custom_x = st.session_state.get("custom_x", 100)
                custom_y = st.session_state.get("custom_y", 100)

            col_sz, col_op = st.columns(2)
            with col_sz:
                font_size = st.slider("字号", min_value=12, max_value=120, key="font_size")
            with col_op:
                opacity = st.slider("透明度", min_value=0.1, max_value=1.0, step=0.1, key="opacity")

        available_fonts = get_available_fonts()
        font_names = ["系统默认"] + list(available_fonts.keys())
        saved_font = st.session_state.get("font", "系统默认")
        font_index = font_names.index(saved_font) if saved_font in font_names else 0
        with st.expander("字体与颜色", expanded=False):
            selected_font = st.selectbox("字体", font_names, index=font_index, key="font")
            color_map_display = {"white": "⬜ 白色", "black": "⬛ 黑色", "yellow": "🟨 黄色", "red": "🟥 红色"}
            color_keys = list(color_map_display.keys())
            saved_color = st.session_state.get("font_color", "white")
            color_index = color_keys.index(saved_color) if saved_color in color_keys else 0
            font_color = st.selectbox(
                "字体颜色",
                color_keys,
                index=color_index,
                format_func=lambda k: color_map_display[k],
                key="font_color",
            )
        font_path = available_fonts.get(selected_font) if selected_font != "系统默认" else None

        quality_options = {
            "近似无损 (CRF 18) - 推荐": 18,
            "高画质 (CRF 20)": 20,
            "标准 (CRF 23)": 23,
            "较小文件 (CRF 28)": 28,
        }
        quality_labels = list(quality_options.keys())
        saved_ql = st.session_state.get("quality_label", quality_labels[0])
        ql_index = quality_labels.index(saved_ql) if saved_ql in quality_labels else 0
        has_gpu = check_videotoolbox()
        encoder_options = {"cpu": "🖥️ CPU (libx264)", "gpu": "⚡ GPU (VideoToolbox)"}
        if settings_match("输出", "画质", "编码", "gpu", "cpu"):
            with st.expander("输出与画质", expanded=settings_expanded("输出", "画质", "编码", "gpu", "cpu", default=False)):
                quality_label = st.selectbox("画质", quality_labels, index=ql_index, key="quality_label")
                quality = quality_options[quality_label]
                st.caption("CRF 越低画质越高，18 几乎无损")

                if has_gpu:
                    encoder_hints = {
                        "cpu": "画质最精准，速度较慢",
                        "gpu": "速度快 3-5 倍，画质略低",
                    }
                    saved_encoder = st.session_state.get("encoder", "cpu")
                    encoder = st.radio(
                        "编码器",
                        list(encoder_options.keys()),
                        format_func=lambda k: encoder_options[k],
                        index=list(encoder_options.keys()).index(saved_encoder) if saved_encoder in encoder_options else 0,
                        key="encoder",
                        horizontal=True,
                    )
                    st.caption(encoder_hints[encoder])
                else:
                    encoder = "cpu"
                    st.caption("CPU 编码；GPU 不可用。")
        else:
            quality_label = saved_ql if saved_ql in quality_options else quality_labels[0]
            quality = quality_options[quality_label]
            encoder = st.session_state.get("encoder", "cpu") if has_gpu else "cpu"

        if settings_match("音量", "声音", "试听"):
            with st.expander("音量", expanded=settings_expanded("音量", "声音", "试听", default=False)):
                volume = st.slider(
                    "输出音量",
                    min_value=0.5,
                    max_value=3.0,
                    step=0.1,
                    key="volume",
                    format="%.1fx",
                )
                if volume < 1.0:
                    st.caption(f"降低至原始音量的 {volume:.0%}")
                elif volume == 1.0:
                    st.caption("原始音量（不做调整）")
                elif volume <= 1.5:
                    st.caption(f"提升至原始音量的 {volume:.0%}")
                else:
                    st.caption(f"大幅提升至原始音量的 {volume:.0%}，注意失真风险")
        else:
            volume = float(st.session_state.get("volume", DEFAULT_SETTINGS.get("volume", 1.0)))

        all_data = load_all()
        preset_slots = list(all_data["presets"].keys())

        preset_notice = st.session_state.pop("preset_notice", "")
        if preset_notice:
            st.success(preset_notice)

        if settings_match("预设", "保存", "载入"):
            with st.expander("预设", expanded=settings_expanded("预设", "保存", "载入", default=False)):
                selected_slot_label = st.selectbox(
                    "选择预设",
                    options=preset_slots,
                    format_func=lambda k: f"{k} · {all_data['presets'][k]['name']}",
                    key="selected_slot",
                )
                selected_preset = all_data["presets"][selected_slot_label]
                saved_settings = get_preset_settings(selected_slot_label) or dict(DEFAULT_SETTINGS)

                st.caption(
                    f"已保存：{saved_settings.get('watermark_text', '') or '空水印'} · "
                    f"{saved_settings.get('position', '右下')} · "
                    f"{saved_settings.get('font_size', DEFAULT_SETTINGS['font_size'])}号 · "
                    f"{int(float(saved_settings.get('opacity', DEFAULT_SETTINGS['opacity'])) * 100)}%透明度"
                )

                preset_col_a, preset_col_b = st.columns(2)
                with preset_col_a:
                    if st.button("载入预设", use_container_width=True, key="preset_load_btn"):
                        st.session_state["pending_widget_settings"] = saved_settings
                        st.session_state["preset_notice"] = f"已载入「{selected_preset['name']}」"
                        st.rerun()
                with preset_col_b:
                    if st.button("保存当前", use_container_width=True, key="preset_save_btn"):
                        current = {k: st.session_state.get(k, DEFAULT_SETTINGS.get(k)) for k in DEFAULT_SETTINGS}
                        save_preset(selected_slot_label, selected_preset["name"], current)
                        st.session_state["preset_notice"] = f"已保存到「{selected_preset['name']}」"
                        st.rerun()

                new_name = st.text_input(
                    "预设名称",
                    value=selected_preset["name"],
                    key=f"rename_input_{selected_slot_label}",
                    placeholder="例如：右上角小字",
                ).strip()
                if st.button("保存名称", use_container_width=True, key="preset_rename_btn"):
                    if not new_name:
                        st.warning("预设名称不能为空")
                    else:
                        rename_preset(selected_slot_label, new_name)
                        st.session_state["preset_notice"] = f"已重命名为「{new_name}」"
                        st.rerun()

        st.divider()
        st.markdown("### 配对参数")
        match_mode = st.radio(
            "配对方式",
            MATCH_MODE_OPTIONS,
            horizontal=True,
            help="视频有英文语音时，推荐先识别中间片段，再和第三列英文文案自动配对。",
            key="match_mode",
        )
        order_sort_mode = "文件名 A-Z"
        voice_engine = "免费本地 Whisper"
        local_whisper_model = "base"
        voice_api_key = ""
        st.session_state.setdefault("voice_engine", "免费本地 Whisper")
        st.session_state.setdefault("local_whisper_model", "base")
        st.session_state.setdefault("voice_api_key", os.environ.get("OPENAI_API_KEY", ""))
        st.session_state.setdefault("recognize_start_seconds", 5)
        st.session_state.setdefault("recognize_end_seconds", 20)
        st.session_state.setdefault("match_threshold", 0.85)
        with st.expander("配对细节设置", expanded=False):
            if match_mode.startswith("语音识别"):
                voice_engine_options = ["免费本地 Whisper", "OpenAI API"]
                if st.session_state.get("voice_engine") not in voice_engine_options:
                    st.session_state["voice_engine"] = voice_engine_options[0]
                voice_engine = st.selectbox(
                    "语音识别方式",
                    voice_engine_options,
                    help="本地 Whisper 不需要 key；OpenAI API 更快更稳，但会按量计费。",
                    key="voice_engine",
                )
                if voice_engine == "免费本地 Whisper":
                    if st.session_state.get("local_whisper_model") not in ["base", "small"]:
                        st.session_state["local_whisper_model"] = "base"
                    local_whisper_model = st.selectbox(
                        "本地 Whisper 模型",
                        ["base", "small"],
                        help="base 更快更省资源；small 更准但更慢。首次使用会下载模型。",
                        key="local_whisper_model",
                    )
                    st.caption("本地识别不需要 key。第一次使用某个模型会下载一次，之后可离线使用。")
                else:
                    voice_api_key = st.text_input(
                        "OpenAI API Key",
                        type="password",
                        placeholder="sk-...",
                        help="用于把视频语音转成文字，只在你点击语音识别时使用。",
                        key="voice_api_key",
                    )
                range_col1, range_col2 = st.columns(2)
                with range_col1:
                    recognize_start_seconds = st.number_input(
                        "识别开始位置（秒）",
                        min_value=0,
                        step=5,
                        help="头部经常重复时，把开始位置设到中间，例如 10 秒。",
                        key="recognize_start_seconds",
                    )
                with range_col2:
                    recognize_end_seconds = st.number_input(
                        "识别结束位置（秒）",
                        min_value=1,
                        step=5,
                        help="结束位置必须大于开始位置。",
                        key="recognize_end_seconds",
                    )
                match_threshold = st.slider(
                    "识别成功匹配度",
                    min_value=0.5,
                    max_value=0.95,
                    step=0.05,
                    format="%.2f",
                    help="达到这个匹配度才算自动识别成功；建议先用 0.80。",
                    key="match_threshold",
                )
            else:
                recognize_start_seconds = st.session_state.get("recognize_start_seconds", 5)
                recognize_end_seconds = st.session_state.get("recognize_end_seconds", 20)
                match_threshold = st.session_state.get("match_threshold", 0.85)

            st.session_state.setdefault("order_sort_mode", "文件名 A-Z")
            if match_mode.startswith("按视频顺序"):
                order_sort_options = ["文件名 A-Z", "修改时间：旧到新", "修改时间：新到旧"]
                if st.session_state.get("order_sort_mode") not in order_sort_options:
                    st.session_state["order_sort_mode"] = order_sort_options[0]
                order_sort_mode = st.selectbox(
                    "视频排序",
                    order_sort_options,
                    help="让这里的顺序和你表格里的文案顺序一致即可。",
                    key="order_sort_mode",
                )

            naming_rule_options = ["水印-序号-中文标题", "序号-中文标题", "中文标题", "中文标题-序号"]
            if st.session_state.get("naming_rule") not in naming_rule_options:
                st.session_state["naming_rule"] = naming_rule_options[0]
            naming_rule = st.selectbox(
                "视频命名规则",
                naming_rule_options,
                help="最终输出视频会使用第二列中文标题命名。你可以先在下方预览里审定输出文件名。",
                key="naming_rule",
            )
            filename_length_options = ["较长（推荐，约50个中文字符）", "标准（约35个中文字符）", "很长（约65个中文字符）"]
            if st.session_state.get("filename_length_label") not in filename_length_options:
                st.session_state["filename_length_label"] = filename_length_options[0]
            filename_length_label = st.selectbox(
                "文件名长度",
                filename_length_options,
                help="会自动截断到 macOS/Windows 比较安全的长度，不使用完整英文文案做文件名。",
                key="filename_length_label",
            )
            filename_max_bytes = {
                "标准（约35个中文字符）": 110,
                "较长（推荐，约50个中文字符）": 160,
                "很长（约65个中文字符）": 210,
            }[filename_length_label]

        with st.expander("原图配对", expanded=False):
            st.checkbox(
                "自动原图匹配",
                value=st.session_state.get("image_match_auto_run", True),
                key="image_match_auto_run",
                help="文案/视频配对完成后自动跑感知哈希匹配；未复核视频暂不参与。",
            )
            st.number_input(
                "自动匹配阈值（汉明距离 ≤）",
                min_value=4, max_value=32, step=2,
                help="距离越小越严。talking-head 动画建议 16-20。",
                key="image_match_auto_threshold",
            )
            st.number_input(
                "需要复核的阈值（≤）",
                min_value=8, max_value=40, step=2,
                help="距离介于自动阈值和这个之间的会被标记为'需复核'。",
                key="image_match_review_threshold",
            )

        st.divider()
        st.markdown("### 视频显示")
        with st.expander("⚙️ 视频显示设置", expanded=False):
            video_layout_choice = st.selectbox(
                "检查视频大小",
                ["标准", "大", "超大"],
                key="review_video_layout",
                help="会调整右侧检查区域的宽度；选择后页面会自动重排。",
            )
            default_width = {"标准": 520, "大": 680, "超大": 860}.get(video_layout_choice, 520)
            review_video_width = st.slider(
                "播放器宽度",
                min_value=360,
                max_value=980,
                value=int(st.session_state.get("review_video_width", default_width)),
                step=20,
                key="review_video_width",
            )
            auto_play_review_video = st.checkbox(
                "切到下一个后自动播放",
                value=bool(st.session_state.get("auto_play_review_video", True)),
                key="auto_play_review_video",
                help="浏览器通常要求静音才能自动播放。",
            )
            mute_auto_play_review_video = st.checkbox(
                "自动播放时静音",
                value=bool(st.session_state.get("mute_auto_play_review_video", False)),
                key="mute_auto_play_review_video",
            )

        st.divider()
        st.markdown("### Google Drive")

        if settings_match("drive", "google", "上传", "云盘"):
            with st.expander("Google Drive", expanded=settings_expanded("drive", "google", "上传", "云盘", default=False)):

                if not gdrive.has_credentials_file():
                    with st.expander("☁️ 连接 Google Drive", expanded=False):
                        st.markdown("""
            **一次性配置步骤：**
            1. 打开 [Google Cloud Console](https://console.cloud.google.com/)
            2. 新建项目 → **APIs & Services → Enable APIs** → 搜索 **Google Drive API** → 启用
            3. **Credentials → Create Credentials → OAuth client ID → Desktop app**
            4. 下载 JSON → 重命名为 `credentials.json` → 放到工具文件夹
            5. 重启工具
            """)
                elif st.session_state.get("drive_oauth_pending"):
                    err = gdrive.get_oauth_error()
                    if err:
                        st.error(f"授权失败：{err}")
                        st.session_state.pop("drive_oauth_pending", None)
                    elif gdrive.is_authenticated():
                        st.session_state.pop("drive_oauth_pending", None)
                        st.rerun()
                    else:
                        st.info("🔐 浏览器已打开，请完成 Google 授权…")
                        time.sleep(2)
                        st.rerun()
                elif gdrive.is_authenticated():
                    email = gdrive.get_account_email()
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:8px;padding:10px 12px;'
                        f'background:rgba(52,199,89,0.1);border-radius:12px;'
                        f'border:0.5px solid rgba(52,199,89,0.3);">'
                        f'<div style="width:8px;height:8px;border-radius:50%;background:#34C759;flex-shrink:0;"></div>'
                        f'<span style="font-size:13px;color:#1A7F37;font-weight:500;">{email}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # ── Drive 目标文件夹选择 ──
                    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
                    st.caption("📁 上传到哪个文件夹？")

                    # 初次加载时拉取文件夹列表
                    if "drive_folders" not in st.session_state:
                        with st.spinner("读取 Drive 文件夹…"):
                            st.session_state["drive_folders"] = gdrive.list_folders()

                    folders = st.session_state.get("drive_folders", [])
                    folder_labels = [f["name"] for f in folders]
                    folder_ids    = [f["id"]   for f in folders]

                    folders_err = gdrive.get_folders_error()
                    if folders_err:
                        st.error(f"读取文件夹失败：{folders_err}")

                    if folders:
                        saved_folder_id = st.session_state.get("drive_target_folder_id", folder_ids[0])
                        saved_idx = folder_ids.index(saved_folder_id) if saved_folder_id in folder_ids else 0
                        selected_idx = st.selectbox(
                            "目标文件夹",
                            range(len(folder_labels)),
                            format_func=lambda i: folder_labels[i],
                            index=saved_idx,
                            key="drive_folder_selectbox",
                            label_visibility="collapsed",
                        )
                        st.session_state["drive_target_folder_id"]   = folder_ids[selected_idx]
                        st.session_state["drive_target_folder_name"] = folder_labels[selected_idx]
                    else:
                        st.caption("Drive 中暂无文件夹，请在下方新建一个")
                        st.session_state["drive_target_folder_id"]   = None
                        st.session_state["drive_target_folder_name"] = ""

                    # 刷新列表按钮
                    if st.button("🔄 刷新文件夹列表", use_container_width=True, key="drive_refresh_folders"):
                        with st.spinner("读取 Drive 文件夹…"):
                            st.session_state["drive_folders"] = gdrive.list_folders()
                        st.rerun()

                    # ── 新建文件夹 ──
                    st.markdown("<div style='height:0.2rem'></div>", unsafe_allow_html=True)
                    st.caption("➕ 新建 Drive 文件夹")
                    new_folder_name = st.text_input(
                        "新文件夹名称",
                        key="drive_new_folder_name",
                        placeholder="输入文件夹名称…",
                        label_visibility="collapsed",
                    )
                    if st.button("📁 创建并选择", use_container_width=True, key="drive_create_folder"):
                        if new_folder_name.strip():
                            with st.spinner(f"正在创建「{new_folder_name.strip()}」…"):
                                new_id = gdrive.create_folder(new_folder_name.strip())
                            if new_id:
                                # 刷新列表并自动选中新文件夹
                                st.session_state["drive_folders"] = gdrive.list_folders()
                                st.session_state["drive_target_folder_id"]   = new_id
                                st.session_state["drive_target_folder_name"] = new_folder_name.strip()
                                st.success(f"已创建并选择「{new_folder_name.strip()}」")
                                st.rerun()
                            else:
                                st.error("创建失败，请检查 Drive 连接")
                        else:
                            st.warning("请先输入文件夹名称")

                    # ── 上传本地文件夹 ──
                    st.markdown("<div style='height:0.2rem'></div>", unsafe_allow_html=True)
                    st.caption("⬆️ 上传本地成品文件夹")
                    if "pending_drive_local_upload_folder" in st.session_state:
                        st.session_state["drive_local_upload_folder"] = st.session_state.pop("pending_drive_local_upload_folder")
                    local_col1, local_col2 = st.columns([5, 1])
                    with local_col1:
                        drive_local_upload_folder = st.text_input(
                            "本地成品文件夹",
                            key="drive_local_upload_folder",
                            placeholder="选择或粘贴本地文件夹路径…",
                            label_visibility="collapsed",
                        )
                    with local_col2:
                        if st.button("📂", help="选择本地文件夹", key="pick_drive_local_upload_folder"):
                            pick_folder_into("drive_local_upload_folder")

                    if st.button("上传这个文件夹", use_container_width=True, key="drive_upload_local_folder"):
                        target_folder_id = st.session_state.get("drive_target_folder_id")
                        target_folder_name = st.session_state.get("drive_target_folder_name", "")
                        local_folder = Path((drive_local_upload_folder or "").strip())
                        allowed_suffixes = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
                        if not target_folder_id:
                            st.warning("请先选择或新建一个 Drive 目标文件夹。")
                        elif not local_folder.is_dir():
                            st.warning("请先选择一个有效的本地文件夹。")
                        else:
                            files_to_upload = [
                                path for path in sorted(local_folder.iterdir(), key=lambda p: p.name.lower())
                                if path.is_file() and path.suffix.lower() in allowed_suffixes
                            ]
                            if not files_to_upload:
                                st.warning("这个文件夹里没有可上传的视频文件。")
                            else:
                                up_progress = st.progress(0)
                                up_status = st.empty()
                                ok_count = 0
                                for i, file_path in enumerate(files_to_upload):
                                    up_status.caption(f"上传中 ({i + 1}/{len(files_to_upload)})：{file_path.name}")
                                    ok, err = gdrive.upload_file(
                                        str(file_path),
                                        target_folder_id,
                                        mime_type=infer_mime_type(file_path),
                                    )
                                    if ok:
                                        ok_count += 1
                                    else:
                                        st.warning(f"{file_path.name} 上传失败：{err}")
                                    up_progress.progress((i + 1) / len(files_to_upload))
                                up_status.empty()
                                up_progress.empty()
                                link = gdrive.folder_link(target_folder_id)
                                gdrive.copy_to_clipboard(link)
                                st.session_state["last_drive_link"] = link
                                st.session_state["last_drive_folder"] = target_folder_name or target_folder_id
                                st.session_state["last_drive_count"] = f"{ok_count}/{len(files_to_upload)}"
                                st.success(f"上传完成：{ok_count}/{len(files_to_upload)} 个文件")

                    # ── 最近上传的文件夹链接 ──
                    last_link   = st.session_state.get("last_drive_link")
                    last_folder = st.session_state.get("last_drive_folder", "")
                    last_count  = st.session_state.get("last_drive_count", "")
                    if last_link:
                        st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)
                        st.markdown(
                            f'<div style="background:#fff;border-radius:12px;padding:12px 14px;'
                            f'border:0.5px solid rgba(0,122,255,0.22);margin-bottom:4px;">'
                            f'<div style="font-size:11px;font-weight:600;color:#8E8E93;letter-spacing:0.04em;'
                            f'text-transform:uppercase;margin-bottom:6px;">最近上传</div>'
                            f'<div style="font-size:13px;font-weight:500;color:#1D1D1F;margin-bottom:4px;">'
                            f'📁 {last_folder} <span style="color:#8E8E93;font-weight:400;">· {last_count} 个文件</span></div>'
                            f'<a href="{last_link}" target="_blank" '
                            f'style="font-size:12px;color:#007AFF;text-decoration:none;word-break:break-all;">'
                            f'🔗 打开 Drive 文件夹</a>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        if st.button("✕ 清除链接", use_container_width=True, key="clear_drive_link"):
                            st.session_state.pop("last_drive_link", None)
                            st.session_state.pop("last_drive_folder", None)
                            st.session_state.pop("last_drive_count", None)
                            st.rerun()

                    col_sw, col_dc = st.columns(2)
                    with col_sw:
                        if st.button("切换账号", use_container_width=True, key="drive_switch"):
                            gdrive.revoke_auth()
                            st.session_state.pop("drive_folders", None)
                            st.session_state.pop("drive_target_folder_id", None)
                            gdrive.start_oauth_flow()
                            st.session_state["drive_oauth_pending"] = True
                            st.rerun()
                    with col_dc:
                        if st.button("断开连接", use_container_width=True, key="drive_disconnect"):
                            gdrive.revoke_auth()
                            st.session_state.pop("drive_folders", None)
                            st.session_state.pop("drive_target_folder_id", None)
                            st.rerun()
                else:
                    if st.button("🔗 连接 Google Drive", use_container_width=True, key="drive_connect"):
                        gdrive.start_oauth_flow()
                        st.session_state["drive_oauth_pending"] = True
                        st.rerun()

        st.divider()
        sidebar_export_btn = st.button("🚀 一键导出", key="sidebar_export_btn", use_container_width=True)

    # 持久化当前设置
    save_last_used({
        "watermark_text": watermark_text,
        "position": position,
        "custom_x": custom_x if custom_x is not None else st.session_state.get("custom_x", 100),
        "custom_y": custom_y if custom_y is not None else st.session_state.get("custom_y", 100),
        "font": selected_font,
        "font_size": font_size,
        "opacity": opacity,
        "font_color": font_color,
        "quality_label": quality_label,
        "encoder": encoder,
        "volume": volume,
    })
    return {
        "watermark_text": watermark_text,
        "position": position,
        "custom_x": custom_x,
        "custom_y": custom_y,
        "font_size": font_size,
        "selected_font": selected_font,
        "font_path": font_path,
        "opacity": opacity,
        "font_color": font_color,
        "quality_label": quality_label,
        "quality": quality,
        "encoder": encoder,
        "volume": volume,
        "match_mode": match_mode,
        "voice_engine": voice_engine,
        "voice_api_key": voice_api_key,
        "local_whisper_model": local_whisper_model,
        "recognize_start_seconds": recognize_start_seconds,
        "recognize_end_seconds": recognize_end_seconds,
        "match_threshold": match_threshold,
        "order_sort_mode": order_sort_mode,
        "naming_rule": naming_rule,
        "filename_length_label": filename_length_label,
        "filename_max_bytes": filename_max_bytes,
        "auto_play_review_video": auto_play_review_video,
        "mute_auto_play_review_video": mute_auto_play_review_video,
        "review_video_width": review_video_width,
        "sidebar_export_btn": sidebar_export_btn,
    }
