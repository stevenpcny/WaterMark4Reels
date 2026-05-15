from __future__ import annotations


APP_CSS = r'''
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

.subsection-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: #1D1D1F;
    margin-bottom: 8px;
    margin-top: 12px;
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
'''
