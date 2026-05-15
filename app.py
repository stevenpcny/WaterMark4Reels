import html
import json
import tempfile
import os
import subprocess
import time
import threading
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from pathlib import Path

import gdrive

from watermark import (
    add_watermark,
    check_ffmpeg,
    check_videotoolbox,
    find_video_files,
    match_video,
    match_all_videos,
    generate_preview,
    generate_audio_preview,
    get_available_fonts,
    parse_mapping_rows,
    sanitize_filename,
    transcribe_video_local_whisper,
    transcribe_video_openai,
    text_similarity,
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

st.set_page_config(
    page_title="Reels 水印工具",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════
# Apple 设计系统 · 全局样式
# ══════════════════════════════════════
st.markdown("""
<style>
/* ── 系统字体 ── */
*, body, .stApp {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
                 "Helvetica Neue", Arial, sans-serif !important;
}

/* Streamlit 的内置图标要保留 Material Symbols 字体，否则会显示成 keyboard_arrow_right 这类文字 */
span[data-testid="stIconMaterial"],
span[class*="material-symbols"],
span[class*="material-icons"] {
    font-family: "Material Symbols Rounded", "Material Symbols Outlined", "Material Icons" !important;
    font-weight: normal !important;
    font-style: normal !important;
    line-height: 1 !important;
    letter-spacing: normal !important;
    text-transform: none !important;
    white-space: nowrap !important;
    word-wrap: normal !important;
    direction: ltr !important;
    -webkit-font-feature-settings: "liga" !important;
    -webkit-font-smoothing: antialiased !important;
}

/* ── 隐藏 Streamlit 默认元素 ── */
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

/* ── 页面背景 ── */
.main, .stApp { background: #F2F2F7 !important; }
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    padding-left: 1.25rem !important;
    padding-right: 1.25rem !important;
    max-width: 1680px !important;
    width: 100% !important;
}

/* ── 侧边栏 ── */
section[data-testid="stSidebar"] > div:first-child {
    background: #FAFAFA !important;
    border-right: 0.5px solid rgba(60,60,67,0.18) !important;
    padding-top: 1.5rem;
}
.sidebar-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #8E8E93;
    padding: 14px 0 5px;
}

/* ── 主按钮（Apple Blue Pill）── */
button[data-testid="baseButton-primary"] {
    background: #007AFF !important;
    border: none !important;
    color: #fff !important;
    font-weight: 500 !important;
    font-size: 15px !important;
    border-radius: 980px !important;
    letter-spacing: -0.01em !important;
    box-shadow: none !important;
    transition: background 0.15s ease, opacity 0.15s ease !important;
}
button[data-testid="baseButton-primary"]:hover  { background: #0071E3 !important; }
button[data-testid="baseButton-primary"]:active { opacity: 0.75 !important; }

/* ── 次按钮 ── */
button[data-testid="baseButton-secondary"] {
    background: rgba(120,120,128,0.12) !important;
    border: none !important;
    color: #1D1D1F !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    border-radius: 980px !important;
    transition: background 0.15s ease !important;
}
button[data-testid="baseButton-secondary"]:hover { background: rgba(120,120,128,0.2) !important; }

/* ── 输入框 ── */
input[type="text"], textarea {
    border-radius: 10px !important;
    border: 0.5px solid rgba(60,60,67,0.25) !important;
    background: #fff !important;
    font-size: 15px !important;
    color: #1D1D1F !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
input[type="text"]:focus, textarea:focus {
    border-color: #007AFF !important;
    box-shadow: 0 0 0 3px rgba(0,122,255,0.18) !important;
    outline: none !important;
}
textarea:disabled {
    color: #1D1D1F !important;
    -webkit-text-fill-color: #1D1D1F !important;
    opacity: 1 !important;
}
[data-testid="stTextArea"] textarea {
    line-height: 1.55 !important;
    font-size: 14px !important;
}

/* ── 文件上传区 ── */
[data-testid="stFileUploader"] > div {
    border: 1.5px dashed rgba(0,122,255,0.45) !important;
    border-radius: 14px !important;
    background: rgba(0,122,255,0.04) !important;
    transition: all 0.2s ease !important;
}
[data-testid="stFileUploader"] > div:hover {
    border-color: #007AFF !important;
    background: rgba(0,122,255,0.08) !important;
}

/* ── 数据表格 ── */
[data-testid="stDataFrame"] {
    border-radius: 12px !important;
    overflow: hidden !important;
    border: 0.5px solid rgba(60,60,67,0.16) !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
}

/* ── Alert ── */
[data-testid="stAlert"] {
    border-radius: 12px !important;
    border: none !important;
    font-size: 14px !important;
}

/* ── Expander ── */
details {
    border: 0.5px solid rgba(60,60,67,0.18) !important;
    border-radius: 12px !important;
    background: #fff !important;
}
details summary { font-weight: 500 !important; font-size: 14px !important; }

/* ── 进度条 ── */
[data-testid="stProgress"] > div > div {
    background: #007AFF !important;
    border-radius: 999px !important;
}
[data-testid="stProgress"] > div {
    border-radius: 999px !important;
    background: rgba(60,60,67,0.12) !important;
    height: 6px !important;
}

/* ── Metric ── */
[data-testid="stMetric"] {
    background: #fff;
    border-radius: 14px;
    padding: 14px 16px;
    border: 0.5px solid rgba(60,60,67,0.14);
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
[data-testid="stMetricLabel"] { font-size: 12px !important; color: #8E8E93 !important; font-weight: 500 !important; }
[data-testid="stMetricValue"] { font-size: 28px !important; font-weight: 600 !important; color: #1D1D1F !important; letter-spacing: -0.5px; }

/* ── Radio ── */
div[data-testid="stRadio"] > div { gap: 4px !important; }
div[data-testid="stRadio"] label { font-size: 14px !important; }

/* ── Selectbox ── */
[data-testid="stSelectbox"] > div > div {
    border-radius: 10px !important;
    border: 0.5px solid rgba(60,60,67,0.25) !important;
    background: #fff !important;
}

/* ── Slider ── */
[data-testid="stSlider"] [data-baseweb="slider"] > div:last-child > div {
    background: #007AFF !important;
}

/* ── 分割线 ── */
hr {
    border: none !important;
    border-top: 0.5px solid rgba(60,60,67,0.15) !important;
    margin: 1.1rem 0 !important;
}

/* ── Apple 卡片 ── */
.apple-card {
    background: #fff;
    border-radius: 16px;
    padding: 20px 22px;
    border: 0.5px solid rgba(60,60,67,0.12);
    box-shadow: 0 1px 4px rgba(0,0,0,0.07), 0 4px 16px rgba(0,0,0,0.04);
    margin-bottom: 14px;
}

/* ── 区域标题 ── */
.section-title {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: #8E8E93;
    margin-bottom: 10px;
    margin-top: 4px;
}

/* ── 状态徽标 ── */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: -0.01em;
}
.badge-green  { background: rgba(52,199,89,0.15);  color: #1A7F37; }
.badge-blue   { background: rgba(0,122,255,0.12);   color: #0055CC; }
.badge-orange { background: rgba(255,149,0,0.15);   color: #A05B00; }
.badge-red    { background: rgba(255,59,48,0.12);   color: #C0392B; }

/* ── 信息横条 ── */
.info-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 11px 14px;
    border-radius: 12px;
    font-size: 14px;
    margin: 8px 0;
}
.info-bar-green  { background: rgba(52,199,89,0.1);  border: 0.5px solid rgba(52,199,89,0.3);  color: #1A7F37; }
.info-bar-blue   { background: rgba(0,122,255,0.08); border: 0.5px solid rgba(0,122,255,0.25); color: #0055CC; }
.info-bar-orange { background: rgba(255,149,0,0.1);  border: 0.5px solid rgba(255,149,0,0.3);  color: #A05B00; }
.info-bar-yellow { background: rgba(255,204,0,0.1);  border: 0.5px solid rgba(255,204,0,0.35); color: #7A5C00; }

/* ── 复核工作台 ── */
.review-strip,
.workflow-stats {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: center;
    margin: 4px 0 12px;
}
.review-chip,
.workflow-stat {
    background: #fff;
    border: 0.5px solid rgba(60,60,67,0.14);
    border-radius: 12px;
    padding: 8px 12px;
    min-width: 92px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.review-chip span,
.workflow-stat span {
    display: block;
    color: #8E8E93;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.03em;
}
.review-chip strong,
.workflow-stat strong {
    display: block;
    color: #1D1D1F;
    font-size: 18px;
    line-height: 1.15;
    margin-top: 2px;
}
.review-meta {
    background: #fff;
    border: 0.5px solid rgba(60,60,67,0.14);
    border-radius: 14px;
    padding: 10px 12px;
    margin-bottom: 10px;
}
.review-meta-row {
    display: grid;
    grid-template-columns: 82px minmax(0, 1fr);
    gap: 8px;
    align-items: start;
    font-size: 13px;
    line-height: 1.45;
}
.review-meta-row + .review-meta-row { margin-top: 6px; }
.review-meta-label {
    color: #8E8E93;
    font-weight: 600;
}
.review-meta-value {
    color: #1D1D1F;
    word-break: break-word;
}
.review-status-pill {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 2px 9px;
    background: rgba(0,122,255,0.1);
    color: #0055CC;
    font-weight: 600;
}

/* caption 字体 */
.stCaption, [data-testid="stCaptionContainer"] p {
    color: #8E8E93 !important;
    font-size: 12px !important;
}
</style>
""", unsafe_allow_html=True)


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
            'tell application "System Events" to activate\n'
            'set f to choose folder\n'
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


def _review_media_url(video_path: str) -> str:
    """Return Streamlit's cached media URL for a local review video."""
    try:
        from streamlit import runtime

        if not runtime.exists():
            return ""
        path = Path(video_path)
        stat = path.stat()
        coordinates = f"review-video:{path.name}:{stat.st_size}:{int(stat.st_mtime)}"
        return runtime.get_instance().media_file_mgr.add(
            str(path),
            infer_mime_type(path),
            coordinates,
        )
    except Exception:
        return ""


def render_review_video_player(
    video_path: str,
    *,
    width_px: int,
    autoplay: bool,
    muted: bool,
) -> bool:
    """Render a cached HTML5 review player with responsive scrub controls."""
    media_url = _review_media_url(video_path)
    if not media_url:
        return False

    height_px = int(width_px * 1.15) + 118
    components.html(
        f"""
        <div class="review-player-wrap" style="max-width:{width_px}px;margin:0 auto;">
          <video id="review-video" controls playsinline preload="auto"
                 {'autoplay' if autoplay else ''} {'muted' if muted else ''}
                 style="width:100%;max-height:{int(width_px * 1.15)}px;background:#000;
                        border-radius:12px;display:block;object-fit:contain;">
          </video>
          <div style="display:flex;align-items:center;gap:8px;margin-top:8px;
                      font:12px -apple-system,BlinkMacSystemFont,sans-serif;color:#6b7280;">
            <span id="review-current" style="min-width:42px;text-align:right;">0:00</span>
            <input id="review-scrub" type="range" min="0" max="1000" value="0" step="1"
                   style="flex:1;accent-color:#007AFF;">
            <span id="review-duration" style="min-width:42px;">0:00</span>
            <select id="review-speed"
                    style="border:1px solid #e5e7eb;border-radius:7px;padding:3px 5px;
                           background:white;color:#374151;">
              <option value="0.5">0.5x</option>
              <option value="1" selected>1x</option>
              <option value="1.5">1.5x</option>
              <option value="2">2x</option>
            </select>
          </div>
        </div>
        <script>
        (() => {{
          const video = document.getElementById("review-video");
          const scrub = document.getElementById("review-scrub");
          const current = document.getElementById("review-current");
          const duration = document.getElementById("review-duration");
          const speed = document.getElementById("review-speed");
          const src = {json.dumps(media_url)};
          video.src = new URL(src, window.parent.location.href).toString();
          video.load();

          const fmt = (value) => {{
            if (!Number.isFinite(value)) return "0:00";
            const mins = Math.floor(value / 60);
            const secs = Math.floor(value % 60).toString().padStart(2, "0");
            return `${{mins}}:${{secs}}`;
          }};
          const updateScrub = () => {{
            if (!Number.isFinite(video.duration) || video.duration <= 0) return;
            scrub.value = Math.round((video.currentTime / video.duration) * 1000);
            current.textContent = fmt(video.currentTime);
            duration.textContent = fmt(video.duration);
          }};

          let wasPlaying = false;
          video.addEventListener("loadedmetadata", updateScrub);
          video.addEventListener("durationchange", updateScrub);
          video.addEventListener("timeupdate", updateScrub);
          video.addEventListener("canplay", () => {{
            if ({str(autoplay).lower()}) video.play().catch(() => {{}});
          }}, {{ once: true }});
          scrub.addEventListener("pointerdown", () => {{
            wasPlaying = !video.paused;
            video.pause();
          }});
          scrub.addEventListener("input", () => {{
            if (!Number.isFinite(video.duration) || video.duration <= 0) return;
            video.currentTime = (Number(scrub.value) / 1000) * video.duration;
            current.textContent = fmt(video.currentTime);
          }});
          scrub.addEventListener("pointerup", () => {{
            if (wasPlaying) video.play().catch(() => {{}});
          }});
          speed.addEventListener("change", () => {{
            video.playbackRate = Number(speed.value);
          }});
        }})();
        </script>
        """,
        height=height_px,
    )
    return True


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
        st.session_state["recognize_start_seconds"] = 10
        st.session_state["recognize_end_seconds"] = 20
    st.session_state["recognition_default_window_updated"] = True


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

    # ── 水印设置 ──
    st.markdown('<div class="sidebar-label">水印设置</div>', unsafe_allow_html=True)

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
        st.caption("X/Y 为像素值，(0,0) 为左上角")
        c1, c2 = st.columns(2)
        with c1:
            custom_x = st.number_input("X", min_value=0, max_value=3840, key="custom_x", label_visibility="collapsed")
            st.caption("← X")
        with c2:
            custom_y = st.number_input("Y", min_value=0, max_value=2160, key="custom_y", label_visibility="collapsed")
            st.caption("← Y")

    available_fonts = get_available_fonts()
    font_names = ["系统默认"] + list(available_fonts.keys())
    saved_font = st.session_state.get("font", "系统默认")
    font_index = font_names.index(saved_font) if saved_font in font_names else 0
    selected_font = st.selectbox("字体", font_names, index=font_index, key="font")
    font_path = available_fonts.get(selected_font) if selected_font != "系统默认" else None

    col_sz, col_op = st.columns(2)
    with col_sz:
        font_size = st.slider("字号", min_value=12, max_value=120, key="font_size")
    with col_op:
        opacity = st.slider("透明度", min_value=0.1, max_value=1.0, step=0.1, key="opacity")

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

    st.divider()

    # ── 画质设置 ──
    st.markdown('<div class="sidebar-label">输出画质</div>', unsafe_allow_html=True)
    quality_options = {
        "近似无损 (CRF 18) - 推荐": 18,
        "高画质 (CRF 20)": 20,
        "标准 (CRF 23)": 23,
        "较小文件 (CRF 28)": 28,
    }
    quality_labels = list(quality_options.keys())
    saved_ql = st.session_state.get("quality_label", quality_labels[0])
    ql_index = quality_labels.index(saved_ql) if saved_ql in quality_labels else 0
    quality_label = st.selectbox("画质", quality_labels, index=ql_index, key="quality_label")
    quality = quality_options[quality_label]
    st.caption("CRF 越低画质越高，18 几乎无损")

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
    st.markdown('<div class="sidebar-label">编码方式</div>', unsafe_allow_html=True)

    has_gpu = check_videotoolbox()
    encoder_options = {"cpu": "🖥️ CPU (libx264)", "gpu": "⚡ GPU (VideoToolbox)"}

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
            label_visibility="collapsed",
        )
        st.caption(encoder_hints[encoder])
    else:
        encoder = "cpu"
        st.markdown(
            '<div style="font-size:13px;color:#1D1D1F;font-weight:500;">🖥️ CPU (libx264)</div>'
            '<div style="font-size:12px;color:#8E8E93;margin-top:2px;">GPU 不可用（FFmpeg 未编译 VideoToolbox）</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── 音量调整 ──
    st.markdown('<div class="sidebar-label">音量调整</div>', unsafe_allow_html=True)
    volume = st.slider(
        "输出音量",
        min_value=0.5,
        max_value=3.0,
        step=0.1,
        key="volume",
        format="%.1fx",
    )
    if volume < 1.0:
        st.caption(f"🔉 降低至原始音量的 {volume:.0%}")
    elif volume == 1.0:
        st.caption("🔊 原始音量（不做调整）")
    elif volume <= 1.5:
        st.caption(f"🔊 提升至原始音量的 {volume:.0%}")
    else:
        st.caption(f"🔊 大幅提升至原始音量的 {volume:.0%}，注意失真风险")

    st.divider()

    # ── 预设管理 ──
    st.markdown('<div class="sidebar-label">预设管理</div>', unsafe_allow_html=True)
    all_data = load_all()
    preset_slots = list(all_data["presets"].keys())

    preset_notice = st.session_state.pop("preset_notice", "")
    if preset_notice:
        st.success(preset_notice)

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

    # ── Google Drive ──
    st.markdown('<div class="sidebar-label">Google Drive</div>', unsafe_allow_html=True)

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
video_layout_mode = st.session_state.get("review_video_layout", "标准")
column_ratios = {
    "标准": [3, 2],
    "大": [2.35, 2.25],
    "超大": [1.8, 2.7],
}.get(video_layout_mode, [3, 2])
left_col, right_col = st.columns(column_ratios, gap="large")

with left_col:

    # ── 视频导入 ──
    st.markdown('<div class="section-title">① 导入视频</div>', unsafe_allow_html=True)

    default_downloads = str(Path.home() / "Downloads")
    if "source_folder_upload_val" not in st.session_state:
        st.session_state["source_folder_upload_val"] = default_downloads
    if "output_folder_upload_val" not in st.session_state:
        st.session_state["output_folder_upload_val"] = default_downloads
    st.session_state.setdefault("output_folder_path_val", default_downloads)
    st.session_state.setdefault("video_folder_path", "")
    for path_key in (
        "source_folder_upload_val",
        "output_folder_upload_val",
        "output_folder_path_val",
        "video_folder_path",
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

            st.markdown(
                f'<div class="info-bar info-bar-green">'
                f'<span>✅</span>'
                f'<span style="font-weight:500;">已加载 {len(uploaded_files)} 个视频</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

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
                chosen = pick_folder()
                if chosen:
                    st.session_state["pending_source_folder_upload_val"] = chosen
                    st.rerun()
        source_folder = st.session_state.get("source_folder_upload_val", "").strip() or None

        st.markdown("**📂 输出文件夹** <span style='color:#94a3b8;font-size:0.8rem;'>（留空则输出到原视频目录）</span>", unsafe_allow_html=True)
        out_col1, out_col2 = st.columns([5, 1])
        with out_col1:
            output_folder = st.text_input(
                "输出路径", label_visibility="collapsed",
                placeholder="/Users/你的用户名/Downloads",
                key="output_folder_upload_val",
            )
        with out_col2:
            if st.button("📂", help="选择文件夹", key="pick_out_upload"):
                chosen = pick_folder()
                if chosen:
                    st.session_state["pending_output_folder_upload_val"] = chosen
                    st.rerun()

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
                chosen = pick_folder()
                if chosen:
                    st.session_state["pending_video_folder_path"] = chosen
                    st.rerun()

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
        st.markdown("**📂 输出文件夹** <span style='color:#94a3b8;font-size:0.8rem;'>（留空则与原视频同目录）</span>", unsafe_allow_html=True)
        of_col1, of_col2 = st.columns([5, 1])
        with of_col1:
            output_folder = st.text_input(
                "输出路径", label_visibility="collapsed",
                placeholder="/Users/你的用户名/Downloads",
                key="output_folder_path_val",
            )
        with of_col2:
            if st.button("📂", help="选择文件夹", key="pick_out_folder"):
                chosen = pick_folder()
                if chosen:
                    st.session_state["pending_output_folder_path_val"] = chosen
                    st.rerun()

    videos = uploaded_video_paths

    st.divider()

    # ── 命名映射 ──
    st.markdown('<div class="section-title">② 粘贴 Google Sheets 数据</div>', unsafe_allow_html=True)
    st.caption("从 Google Sheets 复制三列（序号 + 中文标题 + 英文文案），直接粘贴到下方")

    st.session_state.setdefault("paste_data", "")
    paste_data = st.text_area(
        "粘贴数据",
        height=150,
        placeholder="1\t我的第一个Reel\tPaste the English script for video one here\n2\t旅行vlog第二集\tPaste the English script for video two here",
        label_visibility="collapsed",
        key="paste_data",
    )

    match_mode_options = ["语音识别自动配对（推荐）", "按视频顺序配对（不用改文件名）", "按序号/关键词匹配（原方式）"]
    if st.session_state.get("match_mode") not in match_mode_options:
        st.session_state["match_mode"] = match_mode_options[0]
    match_mode = st.radio(
        "配对方式",
        match_mode_options,
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
    st.session_state.setdefault("recognize_start_seconds", 10)
    st.session_state.setdefault("recognize_end_seconds", 20)
    st.session_state.setdefault("match_threshold", 0.8)
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

    if st.button("保存当前填写内容", use_container_width=True, key="save_app_settings_btn"):
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
            "match_threshold": float(st.session_state.get("match_threshold", 0.8)),
            "order_sort_mode": st.session_state.get("order_sort_mode", order_sort_mode),
            "naming_rule": st.session_state.get("naming_rule", naming_rule),
            "filename_length_label": st.session_state.get("filename_length_label", filename_length_label),
            "review_only_confirmed": bool(st.session_state.get("review_only_confirmed", True)),
            "create_caption_files": bool(st.session_state.get("create_caption_files", True)),
            "move_to_trash": bool(st.session_state.get("move_to_trash", True)),
            "drive_target_folder_id": st.session_state.get("drive_target_folder_id"),
            "drive_target_folder_name": st.session_state.get("drive_target_folder_name", ""),
        })
        st.success("已保存当前填写内容。OpenAI API Key 不会写入设置文件。")

    if paste_data and videos:
        mapping_rows = parse_mapping_rows(paste_data)
        mapping = {row["seq"]: row["name"] for row in mapping_rows}
        caption_by_seq = {row["seq"]: row.get("caption", "") for row in mapping_rows}
        has_captions = any(text.strip() for text in caption_by_seq.values())
        if mapping:
            match_by_voice = match_mode.startswith("语音识别")
            match_by_order = match_mode.startswith("按视频顺序")

            def _file_mtime(path: Path) -> float:
                try:
                    return path.stat().st_mtime
                except OSError:
                    return 0

            if order_sort_mode == "修改时间：旧到新":
                ordered_video_files = sorted(videos.values(), key=lambda p: (_file_mtime(p), p.name.lower()))
            elif order_sort_mode == "修改时间：新到旧":
                ordered_video_files = sorted(videos.values(), key=lambda p: (_file_mtime(p), p.name.lower()), reverse=True)
            else:
                ordered_video_files = sorted(videos.values(), key=lambda p: p.name.lower())

            def _output_stem(seq: str, chinese_title: str) -> str:
                title = chinese_title.strip() or seq
                if naming_rule == "序号-中文标题":
                    raw = f"{seq}-{title}"
                elif naming_rule == "中文标题":
                    raw = title
                elif naming_rule == "中文标题-序号":
                    raw = f"{title}-{seq}"
                else:
                    raw = f"水印-{seq}-{title}"
                return sanitize_filename(raw, max_bytes=filename_max_bytes)

            if match_by_voice or match_by_order:
                mapping_entries = mapping_rows
            else:
                mapping_entries = [
                    {"seq": seq, "name": name, "caption": caption_by_seq.get(seq, "")}
                    for seq, name in sorted(mapping.items(), key=lambda x: x[0])
                ]

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
                stored_voice = st.session_state.get("voice_match_result", {})
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
                                ok, text_or_error = transcribe_video_local_whisper(
                                    str(video_file),
                                    start=recognize_start_seconds,
                                    duration=recognize_duration,
                                    model_size=local_whisper_model,
                                )
                            else:
                                ok, text_or_error = transcribe_video_openai(
                                    str(video_file),
                                    voice_api_key,
                                    start=recognize_start_seconds,
                                    duration=recognize_duration,
                                )
                            if ok:
                                transcribed[i] = text_or_error
                            else:
                                failures.append(f"{video_file.name}：{text_or_error}")
                            progress.progress((i + 1) / len(ordered_video_files))

                        candidate_scores = []
                        for video_index, transcript in transcribed.items():
                            for row_index, row in enumerate(mapping_entries):
                                target_text = row.get("caption", "").strip()
                                if not target_text:
                                    continue
                                score = text_similarity(transcript, target_text)
                                candidate_scores.append((score, video_index, row_index))

                        assigned_videos = set()
                        assigned_rows = set()
                        assignments = {}
                        scores = {}
                        for score, video_index, row_index in sorted(candidate_scores, reverse=True):
                            if score < match_threshold:
                                continue
                            if video_index in assigned_videos or row_index in assigned_rows:
                                continue
                            assigned_videos.add(video_index)
                            assigned_rows.add(row_index)
                            assignments[row_index] = video_index
                            scores[row_index] = score

                        st.session_state["voice_match_result"] = {
                            "signature": voice_signature,
                            "assignments": assignments,
                            "transcripts": transcribed,
                            "scores": scores,
                            "failures": failures,
                        }
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

            def _matched_files(row_index: int, seq: str) -> list:
                if match_by_voice:
                    video_index = voice_assignments.get(row_index)
                    if video_index is None:
                        return []
                    return [ordered_video_files[video_index]]
                if match_by_order:
                    return [ordered_video_files[row_index]] if row_index < len(ordered_video_files) else []
                return match_all_videos(seq, videos)

            def _output_name_for(seq: str, chinese_title: str, video_file: Path, matched_count: int, match_index: int) -> str:
                output_stem = _output_stem(seq, chinese_title)
                if matched_count == 1:
                    return f"{output_stem}{video_file.suffix}"
                return f"{output_stem}-{match_index}{video_file.suffix}"

            def _review_id_for(row_index: int, video_file: Path, output_name: str) -> str:
                return f"{row_index}:{video_file.name}:{output_name}"

            st.divider()
            st.markdown('<div class="section-title">③ 映射预览</div>', unsafe_allow_html=True)

            if match_by_voice:
                if not voice_assignments:
                    st.info("先点击上方“识别视频语音并自动配对”，完成后这里会显示语音和文案的匹配结果。")
            elif match_by_order:
                order_rows = [
                    {"顺序": i, "视频文件": path.name}
                    for i, path in enumerate(ordered_video_files, 1)
                ]
                with st.expander("查看当前视频顺序", expanded=False):
                    st.dataframe(pd.DataFrame(order_rows), use_container_width=True, hide_index=True)
                    st.caption("表格第 1 行会配上面第 1 个视频；如果顺序不对，先切换上方的视频排序。")

            preview_rows = []
            review_items = []
            total_videos = 0
            for row_index, row in enumerate(mapping_entries):
                seq = row["seq"]
                new_name = row["name"]
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
                            "状态": f"✅ 已找到{f' ({len(matched_files)}个)' if len(matched_files) > 1 and i == 1 else ''}",
                        })

            preview_df = pd.DataFrame(preview_rows)
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
                    '<span>📝</span><span>已检测到英文文案列：处理成功后会为每个视频生成同名 .txt 英文文案文件。</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )

            review_statuses = st.session_state.setdefault("review_statuses", {})
            current_review_ids = {item["id"] for item in review_items}
            st.session_state["review_statuses"] = {
                item_id: status
                for item_id, status in review_statuses.items()
                if item_id in current_review_ids
            }
            review_statuses = st.session_state["review_statuses"]
            st.session_state.setdefault("review_only_confirmed", True)
            confirmed_count = 0
            problem_count = 0
            unchecked_count = 0

            if review_items:
                st.divider()
                st.markdown('<div class="section-title">④ 人工复核</div>', unsafe_allow_html=True)
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

                video_col, text_col = st.columns([0.78, 1.65], gap="large")
                with video_col:
                    st.video(str(selected_item["video_file"]))
                    if match_by_voice:
                        st.caption(
                            "可以拖动进度条快进；建议重点听 "
                            f"{st.session_state.get('recognize_start_seconds', 10)}-"
                            f"{st.session_state.get('recognize_end_seconds', 20)} 秒附近。"
                        )
                    else:
                        st.caption("可以拖动进度条快进，边听声音边核对右侧文案。")
                with text_col:
                    safe_status = html.escape(selected_status_label)
                    safe_output_name = html.escape(selected_item["output_name"])
                    score_text = f"{selected_item['voice_score']:.0%}" if selected_item["voice_score"] is not None else "—"
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
                    cn_col, en_col = st.columns(2)
                    with cn_col:
                        st.text_area(
                            "中文文案 / 标题",
                            value=selected_item["chinese_title"] or "",
                            height=260,
                            disabled=True,
                            key=f"review_chinese_text_{selected_index}",
                        )
                    with en_col:
                        st.text_area(
                            "英文文案（表格原文）",
                            value=selected_item.get("caption", ""),
                            height=260,
                            disabled=True,
                            key=f"review_caption_text_{selected_index}",
                        )
                    if selected_item.get("voice_text"):
                        st.text_area(
                            "识别到的英文语音",
                            value=selected_item["voice_text"],
                            height=140,
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
                review_only_confirmed = bool(st.session_state.get("review_only_confirmed", True))

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

            st.divider()

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
                    out_path = Path(source_folder)
                else:
                    out_path = Path.home() / "Downloads"

                # ── Fix #8: 提前验证写入权限 ──
                path_ok = True
                try:
                    out_path.mkdir(parents=True, exist_ok=True)
                    test_file = out_path / ".write_test"
                    test_file.touch()
                    test_file.unlink()
                except Exception as e:
                    st.error(f"输出文件夹无法写入：{e}\n请重新选择一个有权限的文件夹。")
                    path_ok = False

                # ── 覆盖检测（支持多匹配） ──
                if path_ok:
                    create_caption_files = False
                    if has_captions:
                        create_caption_files = st.checkbox(
                            "📝 同时生成同名英文文案 .txt 文件",
                            value=True,
                            key="create_caption_files",
                            help="例如：输出视频.mp4 会同时生成 输出视频.txt，里面是对应英文文案。",
                        )

                    process_items = []
                    for row_index, row in enumerate(mapping_entries):
                        seq = row["seq"]
                        new_name = row["name"]
                        matched_files = _matched_files(row_index, seq)
                        if not matched_files:
                            continue
                        for i, vf in enumerate(matched_files, 1):
                            output_name = _output_name_for(seq, new_name, vf, len(matched_files), i)
                            review_id = _review_id_for(row_index, vf, output_name)
                            review_status = review_statuses.get(review_id)
                            if review_status == "problem":
                                continue
                            if review_only_confirmed and review_status != "confirmed":
                                continue
                            output_file = out_path / output_name
                            process_items.append({
                                "row_index": row_index,
                                "row": row,
                                "video_file": vf,
                                "output_file": output_file,
                                "review_id": review_id,
                            })

                    if review_only_confirmed and not process_items:
                        st.warning("还没有确认通过的配对。请在“人工复核”里确认至少一个视频，或者关闭“只处理已确认通过的配对”。")

                    existing_files = []
                    for item in process_items:
                        output_file = item["output_file"]
                        row = item["row"]
                        if output_file.exists():
                            existing_files.append(output_file.name)
                        if create_caption_files and row.get("caption", "").strip():
                            caption_file = output_file.with_suffix(".txt")
                            if caption_file.exists():
                                existing_files.append(caption_file.name)

                    if existing_files:
                        st.warning(
                            f"以下 {len(existing_files)} 个文件已存在，处理后将被覆盖：\n"
                            + "\n".join(f"• {f}" for f in existing_files[:5])
                            + ("…" if len(existing_files) > 5 else "")
                        )
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

                    if process_items and path_ok and overwrite_confirmed and st.button(
                        f"🚀 开始处理 {len(process_items)} 个视频", type="primary", use_container_width=True
                    ):
                        out_path.mkdir(parents=True, exist_ok=True)
                        progress = st.progress(0)
                        status_text = st.empty()
                        results = []
                        total = len(process_items)
                        done = 0

                        for item in process_items:
                            row = item["row"]
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
                            caption_file_name = ""
                            if success and create_caption_files:
                                caption_text = row.get("caption", "").strip()
                                if caption_text:
                                    caption_file = output_file.with_suffix(".txt")
                                    try:
                                        caption_file.write_text(caption_text + "\n", encoding="utf-8")
                                        caption_file_name = caption_file.name
                                    except Exception as e:
                                        caption_file_name = f"写入失败：{e}"

                            done += 1
                            progress.progress(done / total)
                            result_row = {
                                "原文件": video_file.name,
                                "输出文件": output_file.name,
                            }
                            if has_captions:
                                result_row["英文文案文件"] = caption_file_name or "—"
                            result_row["结果"] = "✅ 成功" if success else f"❌ {error}"
                            results.append(result_row)

                        status_text.empty()
                        progress.empty()

                        succeeded = sum(1 for r in results if "✅" in r["结果"])
                        failed = total - succeeded

                        st.markdown('<div class="section-title">处理结果</div>', unsafe_allow_html=True)
                        ra, rb = st.columns(2)
                        ra.metric("✅ 成功", succeeded)
                        rb.metric("❌ 失败", failed)

                        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

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

                        # ── Google Drive 自动上传 ──
                        successful_files = [r for r in results if "✅" in r["结果"]]
                        if successful_files and gdrive.is_authenticated():
                            st.divider()
                            st.markdown('<div class="section-title">☁️ 上传到 Google Drive</div>', unsafe_allow_html=True)

                            target_folder_id   = st.session_state.get("drive_target_folder_id")
                            target_folder_name = st.session_state.get("drive_target_folder_name", "")

                            if target_folder_id:
                                folder_id   = target_folder_id
                                folder_name = target_folder_name
                            else:
                                # 未选择文件夹时兜底：用输出文件夹名新建
                                folder_name = out_path.name
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

                                upload_file_names = []
                                for r in successful_files:
                                    upload_file_names.append(r["输出文件"])
                                    caption_file = r.get("英文文案文件", "") or r.get("文案文件", "")
                                    if isinstance(caption_file, str) and caption_file.endswith(".txt"):
                                        upload_file_names.append(caption_file)

                                for i, file_name in enumerate(upload_file_names):
                                    file_path = out_path / file_name
                                    up_status.markdown(
                                        f'<div class="info-bar info-bar-blue">'
                                        f'<span>☁️</span>'
                                        f'<span>上传中 ({i+1}/{len(upload_file_names)})：{file_name}</span>'
                                        f'</div>',
                                        unsafe_allow_html=True,
                                    )
                                    ok, err = gdrive.upload_file(str(file_path), folder_id)
                                    upload_results.append({
                                        "文件": file_name,
                                        "上传": "✅" if ok else f"❌ {err}",
                                    })
                                    up_progress.progress((i + 1) / len(upload_file_names))

                                up_status.empty()
                                up_progress.empty()

                                up_ok = sum(1 for r in upload_results if "✅" in r["上传"])
                                st.dataframe(pd.DataFrame(upload_results), use_container_width=True, hide_index=True)

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

    elif paste_data and not videos:
        st.markdown(
            '<div class="info-bar info-bar-orange">'
            '<span>⚠️</span><span>请先上传视频或输入视频文件夹路径</span>'
            '</div>',
            unsafe_allow_html=True,
        )


# ── 右栏：预览 ──
with right_col:
    st.markdown('<div class="section-title">👁️ 水印预览</div>', unsafe_allow_html=True)

    auto_preview = st.session_state.pop("auto_preview", False)

    # ── 音量试听 ──
    if videos:
        first_video_for_audio = sorted(videos.values(), key=lambda p: p.stem)[0]
        st.markdown('<div class="section-title">🔊 音量试听</div>', unsafe_allow_html=True)
        st.caption(f"当前音量：{volume:.1f}x — 截取前 8 秒试听")
        if st.button("🎧 生成试听片段", use_container_width=True, key="audio_preview_btn"):
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

        st.divider()

    if videos:
        first_video = sorted(videos.values(), key=lambda p: p.stem)[0]

        if st.button("🔄 刷新预览", use_container_width=True) or auto_preview:
            with st.spinner("生成预览中…"):
                old_preview = st.session_state.get("preview_path")
                if old_preview and os.path.isfile(old_preview):
                    try:
                        os.unlink(old_preview)
                    except Exception:
                        pass
                st.session_state.pop("preview_path", None)

                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    preview_path = tmp.name

                success, error = generate_preview(
                    input_path=str(first_video),
                    output_image=preview_path,
                    text=watermark_text,
                    position=position,
                    font_size=font_size,
                    opacity=opacity,
                    font_color=font_color,
                    font_path=font_path,
                    custom_x=custom_x,
                    custom_y=custom_y,
                )
                if success:
                    st.session_state["preview_path"] = preview_path
                    st.session_state["preview_name"] = first_video.name
                else:
                    st.error(f"预览生成失败：{error}")

        if "preview_path" in st.session_state and os.path.isfile(st.session_state["preview_path"]):
            st.image(
                st.session_state["preview_path"],
                caption=f"预览：{st.session_state.get('preview_name', '')}",
                use_container_width=True,
            )
            st.markdown(
                f'<div style="text-align:center;font-size:12px;color:#8E8E93;margin-top:4px;">'
                f'字号 {font_size} · 透明度 {opacity} · {position}'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="aspect-ratio:9/16;max-height:420px;'
                'background:rgba(120,120,128,0.08);border-radius:16px;'
                'border:1.5px dashed rgba(120,120,128,0.25);'
                'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;">'
                '<div style="font-size:2.2rem;opacity:0.4;">🖼️</div>'
                '<div style="color:#8E8E93;font-size:13px;font-weight:500;">点击「刷新预览」生成</div>'
                '</div>',
                unsafe_allow_html=True,
            )
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
