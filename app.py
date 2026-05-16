from __future__ import annotations

import html
import logging
import tempfile
import os
import subprocess
import time
import threading
import streamlit as st
import streamlit.components.v1 as components
import streamlit.runtime as st_runtime
from pathlib import Path

import gdrive
import pandas as pd
from ui_styles import APP_CSS

if not st_runtime.exists():
    logging.disable(logging.CRITICAL)

from watermark import (
    add_watermark,
    check_ffmpeg,
    check_videotoolbox,
    find_video_files,
    generate_audio_preview,
    get_available_fonts,
    transcribe_video_local_whisper,
    transcribe_video_openai,
)
from matching import (
    assign_voice_matches,
    build_output_name,
    mapping_entries_for_mode,
    matched_files_for_row,
    parse_mapping_rows,
    review_id_for,
    sort_video_files,
)
from image_matching import (
    find_image_files,
    hash_image,
    hash_video_frames,
    assign_videos_to_images,
    copy_image_with_new_name,
    make_frame_workdir,
)
from processing import (
    burn_subtitles_for_output,
    build_process_items,
    detect_existing_outputs,
    infer_mime_type,
    make_result_row,
    result_to_job_record,
    split_existing_process_items,
    successful_upload_file_names,
    verify_output_folder_writable,
    write_job_report,
)
from presets import (
    load_all,
    save_last_used,
    get_app_settings,
    save_app_settings,
    save_preset,
    rename_preset,
    get_preset_settings,
    DEFAULT_SETTINGS,
)

DEFAULT_SETTINGS.setdefault("burn_subtitles", False)

MATCH_MODE_OPTIONS = ["语音识别自动配对（推荐）", "按视频顺序配对（不用改文件名）", "按序号/关键词匹配（原方式）"]

st.set_page_config(
    page_title="Reels 水印工具",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════
# Apple 设计系统 · 全局样式
# ══════════════════════════════════════
st.markdown(APP_CSS, unsafe_allow_html=True)


def _pd_dataframe(rows):
    return pd.DataFrame(rows)


# ── 全页拖拽蒙层 ──
components.html("""
<script>
(function() {
  const doc = window.parent.document;
  let dragCounter = 0;

  const overlay = doc.createElement('div');
  overlay.id = 'drop-overlay';
  overlay.innerHTML = `
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;">
      <div style="width:88px;height:88px;background:rgba(255,255,255,0.22);border-radius:26px;
                  display:flex;align-items:center;justify-content:center;font-size:48px;
                  animation:float 1s ease-in-out infinite alternate;backdrop-filter:blur(4px);">🎬</div>
      <div style="font-size:26px;font-weight:700;color:#fff;letter-spacing:-0.5px;
                  font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display',sans-serif;">
        松手即可上传
      </div>
      <div style="font-size:14px;color:rgba(255,255,255,0.75);
                  font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-weight:400;">
        支持 MP4 · MOV · AVI · MKV · WEBM
      </div>
    </div>`;
  Object.assign(overlay.style, {
    display:'none', position:'fixed', inset:'0', zIndex:'99999',
    background:'rgba(0,0,0,0.45)', backdropFilter:'blur(20px) saturate(180%)',
    WebkitBackdropFilter:'blur(20px) saturate(180%)',
    alignItems:'center', justifyContent:'center', pointerEvents:'none',
  });
  const style = doc.createElement('style');
  style.textContent = '@keyframes float{from{transform:translateY(0) scale(1)}to{transform:translateY(-12px) scale(1.04)}}';

  doc.head.appendChild(style);
  doc.body.appendChild(overlay);

  function hasFiles(e) { return e.dataTransfer && Array.from(e.dataTransfer.types).includes('Files'); }
  doc.addEventListener('dragenter', e => { if(!hasFiles(e)) return; if(++dragCounter===1) overlay.style.display='flex'; });
  doc.addEventListener('dragleave', e => { if(!hasFiles(e)) return; if(--dragCounter<=0){dragCounter=0;overlay.style.display='none';} });
  doc.addEventListener('dragover',  e => { if(hasFiles(e)) e.preventDefault(); });
  doc.addEventListener('drop', e => {
    dragCounter=0; overlay.style.display='none';
    if(!hasFiles(e)) return;
    e.preventDefault();
    const inputs=[];
    inputs.push(...doc.querySelectorAll('input[type="file"]'));
    Array.from(doc.querySelectorAll('iframe')).forEach(f=>{try{inputs.push(...f.contentDocument.querySelectorAll('input[type="file"]'));}catch(_){}});
    if(!inputs.length) return;
    const dt=new DataTransfer();
    Array.from(e.dataTransfer.files).forEach(f=>dt.items.add(f));
    inputs[0].files=dt.files;
    inputs[0].dispatchEvent(new Event('change',{bubbles:true}));
  });
})();
</script>
""", height=0)

if not check_ffmpeg():
    if os.name == "nt":
        st.error(
            "⚠️ 未检测到 FFmpeg！Windows 版请先安装 FFmpeg，并把 `ffmpeg.exe` 加入 PATH；"
            "也可以把 `ffmpeg.exe` 和 `ffprobe.exe` 放到工具目录的 `ffmpeg\\bin` 文件夹。"
        )
    else:
        st.error("⚠️ 未检测到 FFmpeg！请先安装：`brew install ffmpeg`")
    st.stop()


def pick_folder() -> str:
    if os.name == "nt":
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory()
            root.destroy()
            return folder or ""
        except Exception:
            return ""
    try:
        script = (
            'tell application "System Events"\n'
            '  activate\n'
            '  set f to choose folder with prompt "请选择文件夹"\n'
            'end tell\n'
            'POSIX path of f'
        )
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except Exception:
        return ""


def video_cache_key(video_path: str, *parts) -> str:
    path = Path(video_path)
    try:
        stat = path.stat()
        base = (path.name, stat.st_size, int(stat.st_mtime))
    except OSError:
        base = (path.name, 0, 0)
    return repr((*base, *parts))


def set_pending_path(path_key: str, value: str) -> None:
    st.session_state[f"pending_{path_key}"] = value
    st.rerun()


def pick_folder_into(path_key: str) -> None:
    chosen = pick_folder()
    if chosen:
        set_pending_path(path_key, chosen)
    else:
        st.warning("没有打开文件夹选择窗口。可以先直接把文件夹路径粘贴到左侧输入框。")


def desktop_output_folder() -> str:
    return str(Path.home() / "Desktop" / "打好水印")


def render_review_video_panel(
    videos: dict,
    review_video_width: int,
    auto_play_review_video: bool,
    mute_auto_play_review_video: bool,
    panel_key: str = "default",
) -> None:
    active_review = st.session_state.get("active_review_video") or {}
    active_review_path = active_review.get("path", "")
    showing_review_video = bool(active_review_path and os.path.isfile(active_review_path))

    if showing_review_video:
        st.markdown('<div class="section-title">🎞️ 检查视频</div>', unsafe_allow_html=True)
        st.video(
            active_review_path,
            autoplay=auto_play_review_video,
            muted=mute_auto_play_review_video,
            width=review_video_width,
        )
        if active_review.get("window"):
            st.caption(f"建议重点听 {active_review['window']} 附近；匹配度：{active_review.get('score', '—')}。")
        else:
            st.caption("当前人工复核选中的视频。")
        st.caption("播放器已预加载当前文件。")
        if active_review.get("voice_text"):
            with st.expander("识别到的英文语音", expanded=False):
                st.write(active_review["voice_text"])
    else:
        st.markdown('<div class="section-title">🎞️ 检查视频</div>', unsafe_allow_html=True)
        if videos:
            first_video = sorted(videos.values(), key=lambda p: p.stem)[0]
            st.video(str(first_video), muted=True, width=review_video_width)
            st.caption("选择或确认某条配对后，这里会显示当前视频。")
        else:
            st.markdown(
                '<div style="aspect-ratio:9/16;max-height:420px;'
                'background:rgba(120,120,128,0.07);border-radius:16px;'
                'border:1.5px dashed rgba(120,120,128,0.2);'
                'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;">'
                '<div style="font-size:3rem;opacity:0.35;">🎬</div>'
                '<div style="color:#8E8E93;font-size:13px;font-weight:500;">上传视频后显示预览</div>'
                '</div>',
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════
# 初始化 session_state
# ══════════════════════════════════════
if "settings_loaded" not in st.session_state:
    all_saved_settings = load_all()
    last = all_saved_settings["last_used"]
    for k, v in last.items():
        st.session_state[k] = v
    for k, v in get_app_settings().items():
        st.session_state.setdefault(k, v)
    st.session_state["settings_loaded"] = True

pending_widget_settings = st.session_state.pop("pending_widget_settings", None)
if pending_widget_settings:
    for k, v in pending_widget_settings.items():
        st.session_state[k] = v

if "recognition_default_window_updated" not in st.session_state:
    if (
        st.session_state.get("recognize_start_seconds") == 20
        and st.session_state.get("recognize_end_seconds") == 80
    ):
        st.session_state["recognize_start_seconds"] = 5
        st.session_state["recognize_end_seconds"] = 20
    st.session_state["recognition_default_window_updated"] = True

# 把旧默认 10-20s / 阈值 0.8 / 0.9 一次性升级到新默认 5-20s / 阈值 0.85
if "recognition_defaults_v3" not in st.session_state:
    if st.session_state.get("recognize_start_seconds") == 10 \
       and st.session_state.get("recognize_end_seconds") == 20:
        st.session_state["recognize_start_seconds"] = 5
    if st.session_state.get("match_threshold") in (0.8, 0.9):
        st.session_state["match_threshold"] = 0.85
    st.session_state["recognition_defaults_v3"] = True

if st.session_state.get("match_mode") not in MATCH_MODE_OPTIONS:
    st.session_state["match_mode"] = MATCH_MODE_OPTIONS[0]
st.session_state.setdefault("auto_play_review_video", True)


# ══════════════════════════════════════
# 侧边栏
# ══════════════════════════════════════
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
    "burn_subtitles": bool(st.session_state.get("burn_subtitles", False)),
})


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
    # ── 视频导入 ──
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
                st.session_state["auto_preview"] = True
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
            "image_match_video_ids",
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

    # ── 命名映射 ──
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

                if has_captions or match_by_voice:
                    st.download_button(
                        "📥 下载配对表 CSV",
                        data=preview_df.to_csv(index=False).encode("utf-8-sig"),
                        file_name="视频文案配对表.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
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

                match_btn_cols = st.columns([2, 1])
                with match_btn_cols[0]:
                    do_image_match = st.button(
                        f"🖼️ 配对原图（{len(_img_videos_for_match)} 个视频 × {len(find_image_files(_image_folder))} 张图）",
                        use_container_width=True,
                        key="run_image_match_btn",
                        disabled=not _img_videos_for_match,
                    )
                with match_btn_cols[1]:
                    if st.button("清空结果", use_container_width=True, key="clear_image_match_btn"):
                        st.session_state.pop("image_match_result", None)
                        st.session_state.pop("image_match_overrides", None)
                        st.session_state.pop("image_match_last_fingerprint", None)
                        st.rerun()

                # 自动原图匹配：未复核视频不参与；fingerprint 变化时跑一次
                _auto_run_enabled = bool(st.session_state.get("image_match_auto_run", True))
                _auto_run_videos = [
                    it for it in review_items
                    if review_statuses.get(it["id"]) == "confirmed"
                ]
                _auto_thr_now = int(st.session_state.get("image_match_auto_threshold", 18))
                _review_thr_now = int(st.session_state.get("image_match_review_threshold", 24))
                _auto_fp = (
                    _image_folder,
                    tuple(sorted(it["id"] for it in _auto_run_videos)),
                    _auto_thr_now,
                    _review_thr_now,
                )
                _last_fp = st.session_state.get("image_match_last_fingerprint")
                _auto_trigger = (
                    _auto_run_enabled
                    and _auto_run_videos
                    and _auto_fp != _last_fp
                )

                if do_image_match and _img_videos_for_match:
                    _videos_to_match = _img_videos_for_match
                    _run_match = True
                elif _auto_trigger:
                    _videos_to_match = _auto_run_videos
                    _run_match = True
                    st.info(f"🖼️ 自动原图匹配中（{len(_auto_run_videos)} 个已复核视频）...")
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
                        image_paths = find_image_files(_image_folder)
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

                _result = st.session_state.get("image_match_result")
                if _result:
                    assignments = dict(_result.get("assignments", {}))
                    overrides = st.session_state.setdefault("image_match_overrides", {})
                    # 应用 override 到 assignments 的最终显示
                    final_map: dict[str, str | None] = {}
                    for vid, info in assignments.items():
                        final_map[vid] = overrides.get(vid, info.get("image"))

                    auto_n = sum(1 for v, info in assignments.items() if info["status"] == "auto" and overrides.get(v, info["image"]))
                    review_n = sum(1 for v, info in assignments.items() if info["status"] == "review")
                    unmatched_n = sum(1 for v in assignments if not final_map.get(v))

                    st.markdown(
                        f"""
                        <div class="workflow-stats">
                          <div class="workflow-stat"><span>自动匹配</span><strong>{auto_n}</strong></div>
                          <div class="workflow-stat"><span>需复核</span><strong>{review_n}</strong></div>
                          <div class="workflow-stat"><span>未匹配</span><strong>{unmatched_n}</strong></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

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
                        def _image_for_review_id(rid: str) -> str | None:
                            if rid in _img_overrides:
                                return _img_overrides[rid]
                            info = _img_assignments.get(rid)
                            return info.get("image") if info else None

                        image_dest_folder = out_path / "原图-已配对"
                        image_copy_results = []

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
                                        copied = copy_image_with_new_name(
                                            Path(src_image), image_dest_folder, output_file.stem,
                                        )
                                        image_copy_results.append({
                                            "视频": output_file.name,
                                            "原图": Path(src_image).name,
                                            "复制到": copied.name,
                                            "结果": "✅",
                                        })
                                    except Exception as img_err:
                                        image_copy_results.append({
                                            "视频": output_file.name,
                                            "原图": Path(src_image).name,
                                            "复制到": "—",
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

                        if image_copy_results:
                            st.markdown('<div class="subsection-title">🖼️ 原图复制结果</div>', unsafe_allow_html=True)
                            st.caption(f"原图已复制到：{image_dest_folder}")
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
})
