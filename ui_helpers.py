from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from presets import get_app_settings, load_all
from ui_styles import APP_CSS
from watermark import check_ffmpeg

MATCH_MODE_OPTIONS = ["语音识别自动配对（推荐）", "按视频顺序配对（不用改文件名）", "按序号/关键词匹配（原方式）"]


def _pd_dataframe(rows):
    return pd.DataFrame(rows)


def inject_styles() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
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


def ensure_ffmpeg() -> None:
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




def initialize_session_state() -> None:
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

    if "volume_default_v1" not in st.session_state:
        st.session_state["volume"] = 1.0
        st.session_state["volume_default_v1"] = True

    if st.session_state.get("match_mode") not in MATCH_MODE_OPTIONS:
        st.session_state["match_mode"] = MATCH_MODE_OPTIONS[0]
    st.session_state.setdefault("auto_play_review_video", True)
