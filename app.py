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
    generate_preview,
    generate_audio_preview,
    get_available_fonts,
    parse_mapping,
    sanitize_filename,
)
from presets import (
    load_all,
    save_last_used,
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
# 全局样式
# ══════════════════════════════════════
st.markdown("""
<style>
/* ── 隐藏 Streamlit 默认元素 ── */
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

/* ── 页面背景 ── */
.main { background: #f4f6fb; }
.block-container {
    padding-top: 1.8rem !important;
    padding-bottom: 2rem !important;
    max-width: 1280px;
}

/* ── 侧边栏 ── */
section[data-testid="stSidebar"] > div:first-child {
    background: #ffffff;
    border-right: 1px solid #e8ecf3;
    padding-top: 1.2rem;
}
section[data-testid="stSidebar"] .sidebar-section-label {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #94a3b8;
    padding: 0.6rem 0 0.3rem;
    margin-bottom: 0.2rem;
}

/* ── 按钮 ── */
button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #5b6ef5 0%, #8b5cf6 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    letter-spacing: 0.02em;
    box-shadow: 0 4px 14px rgba(91,110,245,0.35) !important;
    transition: all 0.2s ease !important;
}
button[data-testid="baseButton-primary"]:hover {
    box-shadow: 0 6px 20px rgba(91,110,245,0.5) !important;
    transform: translateY(-1px) !important;
}
button[data-testid="baseButton-secondary"] {
    border-radius: 8px !important;
    border: 1px solid #e2e8f0 !important;
    color: #64748b !important;
    background: white !important;
    font-weight: 500 !important;
    transition: all 0.15s ease !important;
}
button[data-testid="baseButton-secondary"]:hover {
    border-color: #5b6ef5 !important;
    color: #5b6ef5 !important;
    background: #f5f3ff !important;
}

/* ── 输入框 ── */
input[type="text"] {
    border-radius: 8px !important;
    border-color: #e2e8f0 !important;
    background: white !important;
}
input[type="text"]:focus {
    border-color: #5b6ef5 !important;
    box-shadow: 0 0 0 3px rgba(91,110,245,0.15) !important;
}

/* ── 文件上传区 ── */
[data-testid="stFileUploader"] {
    border-radius: 12px !important;
    background: white;
}
[data-testid="stFileUploader"] > div {
    border: 2px dashed #c7d2fe !important;
    border-radius: 12px !important;
    background: linear-gradient(135deg, #fafbff 0%, #f5f3ff 100%) !important;
    transition: all 0.2s ease !important;
}
[data-testid="stFileUploader"] > div:hover {
    border-color: #5b6ef5 !important;
    background: linear-gradient(135deg, #f0f0ff 0%, #ede9fe 100%) !important;
}

/* ── Textarea ── */
textarea {
    border-radius: 10px !important;
    border-color: #e2e8f0 !important;
    font-size: 0.875rem !important;
    background: white !important;
}
textarea:focus {
    border-color: #5b6ef5 !important;
    box-shadow: 0 0 0 3px rgba(91,110,245,0.15) !important;
}

/* ── 数据表格 ── */
[data-testid="stDataFrame"] {
    border-radius: 10px !important;
    overflow: hidden;
    border: 1px solid #e8ecf3 !important;
}

/* ── Alert / notification ── */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    border: none !important;
}

/* ── Expander ── */
details {
    border: 1px solid #e8ecf3 !important;
    border-radius: 10px !important;
    background: white !important;
}
details summary {
    border-radius: 10px !important;
    font-weight: 500 !important;
}

/* ── 进度条 ── */
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #5b6ef5, #8b5cf6) !important;
    border-radius: 999px !important;
}
[data-testid="stProgress"] > div {
    border-radius: 999px !important;
    background: #e8ecf3 !important;
}

/* ── Metric 卡片 ── */
[data-testid="stMetric"] {
    background: white;
    border-radius: 10px;
    padding: 0.8rem 1rem;
    border: 1px solid #e8ecf3;
}

/* ── 选项卡式 Radio ── */
div[data-testid="stRadio"] > label { font-weight: 500; }
div[data-testid="stRadio"] > div {
    gap: 6px !important;
}

/* ── 分割线 ── */
hr { border-color: #e8ecf3 !important; margin: 1rem 0 !important; }

/* ── Selectbox ── */
[data-testid="stSelectbox"] > div > div {
    border-radius: 8px !important;
    border-color: #e2e8f0 !important;
}

/* ── Slider ── */
[data-testid="stSlider"] [data-baseweb="slider"] > div:last-child > div {
    background: linear-gradient(90deg, #5b6ef5, #8b5cf6) !important;
}

/* ── 卡片容器 ── */
.ui-card {
    background: white;
    border-radius: 14px;
    padding: 1.4rem 1.6rem;
    border: 1px solid #e8ecf3;
    margin-bottom: 1rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.ui-card-title {
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #94a3b8;
    margin-bottom: 0.8rem;
}
.status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
}
.badge-green { background: #dcfce7; color: #16a34a; }
.badge-red   { background: #fee2e2; color: #dc2626; }
.badge-blue  { background: #dbeafe; color: #2563eb; }
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
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;">
      <div style="font-size:72px;animation:bounce 0.6s infinite alternate;">📥</div>
      <div style="font-size:28px;font-weight:700;color:#fff;letter-spacing:-0.5px;">松手即可上传视频</div>
      <div style="font-size:15px;color:rgba(255,255,255,0.8);">支持 mp4 / mov / avi / mkv / webm</div>
    </div>`;
  Object.assign(overlay.style, {
    display:'none', position:'fixed', inset:'0', zIndex:'99999',
    background:'rgba(91,110,245,0.6)', backdropFilter:'blur(8px)',
    alignItems:'center', justifyContent:'center', pointerEvents:'none',
  });
  const style = doc.createElement('style');
  style.textContent = '@keyframes bounce{from{transform:translateY(0)}to{transform:translateY(-18px)}}';
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
    st.error("⚠️ 未检测到 FFmpeg！请先安装：`brew install ffmpeg`")
    st.stop()


def pick_folder() -> str:
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


# ══════════════════════════════════════
# 初始化 session_state
# ══════════════════════════════════════
if "settings_loaded" not in st.session_state:
    last = load_all()["last_used"]
    for k, v in last.items():
        st.session_state[k] = v
    st.session_state["settings_loaded"] = True


# ══════════════════════════════════════
# 侧边栏
# ══════════════════════════════════════
with st.sidebar:
    st.markdown("## 🎬 Reels 水印工具")
    st.markdown("<div style='height:4px;background:linear-gradient(90deg,#5b6ef5,#8b5cf6);border-radius:4px;margin-bottom:1.2rem;'></div>", unsafe_allow_html=True)

    # ── 水印设置 ──
    st.markdown('<div class="sidebar-section-label">水印设置</div>', unsafe_allow_html=True)

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
    st.markdown('<div class="sidebar-section-label">输出画质</div>', unsafe_allow_html=True)
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
    st.markdown('<div class="sidebar-section-label">编码方式</div>', unsafe_allow_html=True)

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
            '<div style="font-size:0.82rem;color:#64748b;">🖥️ CPU (libx264)<br>'
            '<span style="color:#94a3b8;font-size:0.78rem;">GPU 不可用（FFmpeg 未编译 VideoToolbox）</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── 音量调整 ──
    st.markdown('<div class="sidebar-section-label">音量调整</div>', unsafe_allow_html=True)
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
    st.markdown('<div class="sidebar-section-label">预设管理</div>', unsafe_allow_html=True)
    all_data = load_all()
    preset_slots = list(all_data["presets"].keys())

    with st.expander("📁 预设", expanded=False):
        selected_slot_label = st.selectbox(
            "预设槽",
            options=preset_slots,
            format_func=lambda k: all_data["presets"][k]["name"],
            key="selected_slot",
            label_visibility="collapsed",
        )
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("📥 载入", use_container_width=True):
                s = get_preset_settings(selected_slot_label)
                if s:
                    for k, v in s.items():
                        st.session_state[k] = v
                    st.success(f"已载入「{all_data['presets'][selected_slot_label]['name']}」")
                    st.rerun()
        with col_b:
            if st.button("💾 保存", use_container_width=True):
                current = {k: st.session_state.get(k, DEFAULT_SETTINGS.get(k)) for k in DEFAULT_SETTINGS}
                save_preset(selected_slot_label, all_data["presets"][selected_slot_label]["name"], current)
                st.success("已保存！")

        st.caption("重命名预设")
        new_name = st.text_input("新名称", value=all_data["presets"][selected_slot_label]["name"], key="rename_input", label_visibility="collapsed", placeholder="预设名称")
        if st.button("✏️ 确认重命名", use_container_width=True):
            rename_preset(selected_slot_label, new_name)
            st.success(f"已重命名为「{new_name}」")
            st.rerun()

    st.divider()

    # ── Google Drive ──
    st.markdown('<div class="sidebar-section-label">Google Drive</div>', unsafe_allow_html=True)

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
            f'<div style="padding:8px 10px;background:#f0fdf4;border-radius:8px;'
            f'border:1px solid #bbf7d0;font-size:0.82rem;color:#15803d;font-weight:500;">'
            f'✅ {email}</div>',
            unsafe_allow_html=True,
        )
        st.caption("处理完成后自动上传到 Drive")
        if st.button("断开连接", use_container_width=True, key="drive_disconnect"):
            gdrive.revoke_auth()
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
<div style="margin-bottom:1.5rem;">
  <h1 style="font-size:1.9rem;font-weight:800;margin:0;
             background:linear-gradient(135deg,#5b6ef5,#8b5cf6);
             -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
    🎬 Reels 批量打水印
  </h1>
  <p style="color:#94a3b8;margin:4px 0 0;font-size:0.92rem;">
    批量添加文字水印 · 自动重命名 · 保留原始画质
  </p>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════
# 主区域
# ══════════════════════════════════════
left_col, right_col = st.columns([3, 2], gap="large")

with left_col:

    # ── 视频导入 ──
    st.markdown('<div class="ui-card-title">① 导入视频</div>', unsafe_allow_html=True)

    import_mode = st.radio(
        "导入方式",
        ["拖拽上传视频", "输入文件夹路径"],
        horizontal=True,
        label_visibility="collapsed",
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
                f'<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;'
                f'background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0;margin-top:0.5rem;">'
                f'<span style="font-size:1.1rem;">✅</span>'
                f'<span style="color:#15803d;font-weight:500;font-size:0.9rem;">已加载 {len(uploaded_files)} 个视频</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
        st.markdown("**📁 原视频所在目录**", unsafe_allow_html=False)
        src_col1, src_col2 = st.columns([5, 1])
        with src_col1:
            source_folder_input = st.text_input(
                "原视频目录", label_visibility="collapsed",
                value=st.session_state.get("source_folder_upload_val", str(Path.home() / "Downloads")),
                placeholder="/Users/你的用户名/Downloads",
            )
            st.session_state["source_folder_upload_val"] = source_folder_input
        with src_col2:
            if st.button("📂", help="选择文件夹", key="pick_source_upload"):
                chosen = pick_folder()
                if chosen:
                    st.session_state["source_folder_upload_val"] = chosen
                    st.rerun()
        source_folder = st.session_state.get("source_folder_upload_val", "").strip() or None

        st.markdown("**📂 输出文件夹** <span style='color:#94a3b8;font-size:0.8rem;'>（留空则输出到原视频目录）</span>", unsafe_allow_html=True)
        out_col1, out_col2 = st.columns([5, 1])
        with out_col1:
            output_folder = st.text_input(
                "输出路径", label_visibility="collapsed",
                value=st.session_state.get("output_folder_upload_val", str(Path.home() / "Downloads")),
                placeholder="/Users/你的用户名/Downloads",
            )
            st.session_state["output_folder_upload_val"] = output_folder
        with out_col2:
            if st.button("📂", help="选择文件夹", key="pick_out_upload"):
                chosen = pick_folder()
                if chosen:
                    st.session_state["output_folder_upload_val"] = chosen
                    st.rerun()

    else:
        st.markdown("**📁 视频文件夹**")
        vf_col1, vf_col2 = st.columns([5, 1])
        with vf_col1:
            video_folder = st.text_input(
                "视频路径", label_visibility="collapsed",
                value=st.session_state.get("video_folder_path", ""),
                placeholder="/Users/你的用户名/Videos/reels",
                key="video_folder_path",
            )
        with vf_col2:
            if st.button("📂", help="选择文件夹", key="pick_video"):
                chosen = pick_folder()
                if chosen:
                    st.session_state["video_folder_path"] = chosen
                    st.rerun()

        if video_folder:
            uploaded_video_paths = find_video_files(video_folder)
            source_folder = video_folder
            if uploaded_video_paths:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;'
                    f'background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0;">'
                    f'<span style="font-size:1.1rem;">✅</span>'
                    f'<span style="color:#15803d;font-weight:500;font-size:0.9rem;">找到 {len(uploaded_video_paths)} 个视频文件</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div style="padding:8px 12px;background:#fef9c3;border-radius:8px;border:1px solid #fde047;">'
                    '<span style="color:#92400e;font-size:0.9rem;">⚠️ 该文件夹中没有找到视频文件</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
        st.markdown("**📂 输出文件夹** <span style='color:#94a3b8;font-size:0.8rem;'>（留空则与原视频同目录）</span>", unsafe_allow_html=True)
        of_col1, of_col2 = st.columns([5, 1])
        with of_col1:
            output_folder = st.text_input(
                "输出路径", label_visibility="collapsed",
                value=st.session_state.get("output_folder_path_val", str(Path.home() / "Downloads")),
                placeholder="/Users/你的用户名/Downloads",
            )
            st.session_state["output_folder_path_val"] = output_folder
        with of_col2:
            if st.button("📂", help="选择文件夹", key="pick_out_folder"):
                chosen = pick_folder()
                if chosen:
                    st.session_state["output_folder_path_val"] = chosen
                    st.rerun()

    videos = uploaded_video_paths

    st.divider()

    # ── 命名映射 ──
    st.markdown('<div class="ui-card-title">② 粘贴 Google Sheets 数据</div>', unsafe_allow_html=True)
    st.caption("从 Google Sheets 复制两列（序号/关键词 + 新文件名），直接粘贴到下方")

    paste_data = st.text_area(
        "粘贴数据",
        height=150,
        placeholder="1\t我的第一个Reel\n2\t旅行vlog第二集\n3\t美食探店合集",
        label_visibility="collapsed",
    )

    if paste_data and videos:
        mapping = parse_mapping(paste_data)
        if mapping:
            st.divider()
            st.markdown('<div class="ui-card-title">③ 映射预览</div>', unsafe_allow_html=True)

            preview_rows = []
            for seq, new_name in sorted(mapping.items(), key=lambda x: x[0]):
                video_file = match_video(seq, videos)
                status = "✅ 已找到" if video_file else "❌ 未找到"
                original = video_file.name if video_file else f"(未匹配到「{seq}」)"
                clean = sanitize_filename(new_name)
                preview_rows.append({
                    "关键词": seq,
                    "原文件": original,
                    "输出文件名": f"水印-{seq}-{clean}.mp4",
                    "状态": status,
                })

            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

            matched = sum(1 for r in preview_rows if "✅" in r["状态"])
            unmatched = len(mapping) - matched

            m1, m2, m3 = st.columns(3)
            m1.metric("总条目", len(mapping))
            m2.metric("已匹配", matched, delta=None)
            m3.metric("未匹配", unmatched, delta=f"-{unmatched}" if unmatched else None, delta_color="inverse" if unmatched else "off")

            st.divider()

            if matched == 0:
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

                # ── Fix #1: 覆盖检测 ──
                if path_ok:
                    existing_files = []
                    for seq, new_name in mapping.items():
                        video_file = match_video(seq, videos)
                        if not video_file:
                            continue
                        clean_name = sanitize_filename(new_name)
                        output_file = out_path / f"水印-{seq}-{clean_name}{video_file.suffix}"
                        if output_file.exists():
                            existing_files.append(output_file.name)

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
                        f'<div style="padding:10px 14px;background:#f8faff;border-radius:8px;'
                        f'border:1px solid #e0e7ff;margin-bottom:0.8rem;font-size:0.875rem;color:#4338ca;">'
                        f'📂 输出到：<code style="background:transparent;">{out_path}</code>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    if path_ok and overwrite_confirmed and st.button(
                        f"🚀 开始处理 {matched} 个视频", type="primary", use_container_width=True
                    ):
                        out_path.mkdir(parents=True, exist_ok=True)
                        progress = st.progress(0)
                        status_text = st.empty()
                        results = []
                        total = matched
                        done = 0

                        for seq, new_name in sorted(mapping.items(), key=lambda x: x[0]):
                            video_file = match_video(seq, videos)
                            if not video_file:
                                continue
                            clean_name = sanitize_filename(new_name)
                            output_file = out_path / f"水印-{seq}-{clean_name}{video_file.suffix}"

                            status_text.markdown(
                                f'<div style="padding:8px 12px;background:#f5f3ff;border-radius:8px;'
                                f'font-size:0.875rem;color:#6d28d9;">'
                                f'⚙️ 正在处理 ({done+1}/{total})：{video_file.name}'
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
                            done += 1
                            progress.progress(done / total)
                            results.append({
                                "原文件": video_file.name,
                                "输出文件": output_file.name,
                                "结果": "✅ 成功" if success else f"❌ {error}",
                            })

                        status_text.empty()
                        progress.empty()

                        succeeded = sum(1 for r in results if "✅" in r["结果"])
                        failed = total - succeeded

                        st.markdown('<div class="ui-card-title">处理结果</div>', unsafe_allow_html=True)
                        ra, rb = st.columns(2)
                        ra.metric("✅ 成功", succeeded)
                        rb.metric("❌ 失败", failed)

                        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

                        if failed:
                            st.warning(f"{failed} 个文件处理失败，请查看上方结果表格。")

                        st.markdown(
                            f'<div style="padding:12px 16px;background:#f0fdf4;border-radius:10px;'
                            f'border:1px solid #bbf7d0;margin-top:0.5rem;">'
                            f'<span style="color:#15803d;font-weight:600;">📂 输出文件夹：</span>'
                            f'<code style="color:#15803d;">{out_path}</code>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        st.balloons()

                        # ── Google Drive 自动上传 ──
                        successful_files = [r for r in results if "✅" in r["结果"]]
                        if successful_files and gdrive.is_authenticated():
                            st.divider()
                            st.markdown('<div class="ui-card-title">☁️ 上传到 Google Drive</div>', unsafe_allow_html=True)

                            folder_name = out_path.name  # 与本地输出文件夹同名
                            with st.spinner(f"正在 Drive 创建文件夹「{folder_name}」…"):
                                folder_id = gdrive.create_folder(folder_name)

                            if not folder_id:
                                st.error("Drive 文件夹创建失败，请检查连接状态")
                            else:
                                gdrive.make_shareable(folder_id)
                                link = gdrive.folder_link(folder_id)

                                up_progress = st.progress(0)
                                up_status = st.empty()
                                upload_results = []

                                for i, r in enumerate(successful_files):
                                    file_path = out_path / r["输出文件"]
                                    up_status.markdown(
                                        f'<div style="padding:8px 12px;background:#eff6ff;'
                                        f'border-radius:8px;font-size:.875rem;color:#1d4ed8;">'
                                        f'☁️ 上传中 ({i+1}/{len(successful_files)})：{r["输出文件"]}'
                                        f'</div>',
                                        unsafe_allow_html=True,
                                    )
                                    ok, err = gdrive.upload_file(str(file_path), folder_id)
                                    upload_results.append({
                                        "文件": r["输出文件"],
                                        "上传": "✅" if ok else f"❌ {err}",
                                    })
                                    up_progress.progress((i + 1) / len(successful_files))

                                up_status.empty()
                                up_progress.empty()

                                up_ok = sum(1 for r in upload_results if "✅" in r["上传"])
                                st.dataframe(pd.DataFrame(upload_results), use_container_width=True, hide_index=True)

                                # 复制链接到剪贴板
                                gdrive.copy_to_clipboard(link)

                                st.markdown(
                                    f'<div style="padding:12px 16px;background:#eff6ff;'
                                    f'border-radius:10px;border:1px solid #bfdbfe;">'
                                    f'<div style="font-weight:600;color:#1d4ed8;margin-bottom:4px;">'
                                    f'☁️ 上传完成：{up_ok}/{len(successful_files)} 个文件</div>'
                                    f'<div style="font-size:.82rem;color:#3b82f6;">📋 Drive 文件夹链接已复制到剪贴板</div>'
                                    f'<a href="{link}" target="_blank" style="font-size:.82rem;color:#2563eb;">{link}</a>'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )

    elif paste_data and not videos:
        st.markdown(
            '<div style="padding:10px 14px;background:#fef9c3;border-radius:8px;'
            'border:1px solid #fde047;font-size:0.875rem;color:#92400e;">'
            '⚠️ 请先上传视频或输入视频文件夹路径'
            '</div>',
            unsafe_allow_html=True,
        )


# ── 右栏：预览 ──
with right_col:
    st.markdown('<div class="ui-card-title">👁️ 水印预览</div>', unsafe_allow_html=True)

    auto_preview = st.session_state.pop("auto_preview", False)

    # ── 音量试听 ──
    if videos:
        first_video_for_audio = sorted(videos.values(), key=lambda p: p.stem)[0]
        st.markdown('<div class="ui-card-title">🔊 音量试听</div>', unsafe_allow_html=True)
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
                f'<div style="text-align:center;font-size:0.78rem;color:#94a3b8;margin-top:4px;">'
                f'字号 {font_size} · 透明度 {opacity} · {position}'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="aspect-ratio:9/16;max-height:400px;background:#f1f5f9;border-radius:12px;'
                'border:2px dashed #e2e8f0;display:flex;align-items:center;justify-content:center;">'
                '<span style="color:#94a3b8;font-size:0.875rem;">点击「刷新预览」生成</span>'
                '</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="aspect-ratio:9/16;max-height:400px;background:#f8fafc;border-radius:12px;'
            'border:2px dashed #e2e8f0;display:flex;flex-direction:column;'
            'align-items:center;justify-content:center;gap:8px;">'
            '<div style="font-size:2.5rem;">🎬</div>'
            '<div style="color:#94a3b8;font-size:0.875rem;">上传视频后自动预览</div>'
            '</div>',
            unsafe_allow_html=True,
        )
