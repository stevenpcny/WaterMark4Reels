"""
Google Drive 认证与上传模块

首次使用前，需要在项目目录放置 credentials.json：
  1. 打开 https://console.cloud.google.com/
  2. 新建项目 → APIs & Services → Enable APIs → 搜索 "Google Drive API" → 启用
  3. APIs & Services → Credentials → Create Credentials → OAuth client ID
  4. Application type 选 "Desktop app" → 创建 → 下载 JSON
  5. 将下载的文件重命名为 credentials.json，放到本工具的文件夹中
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

_BASE = Path(__file__).parent
TOKEN_PATH = _BASE / "token.json"
CREDS_PATH = _BASE / "credentials.json"

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


# ── 状态检查 ──────────────────────────────────────────────────

def has_credentials_file() -> bool:
    """检查 credentials.json 是否存在"""
    return CREDS_PATH.exists()


def is_authenticated() -> bool:
    """检查 token.json 是否存在且有效"""
    if not TOKEN_PATH.exists():
        return False
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds.valid:
            return True
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
            return True
    except Exception:
        pass
    return False


def get_account_email() -> str:
    """获取已登录账号的邮箱"""
    try:
        svc = _get_service()
        about = svc.about().get(fields="user").execute()
        return about["user"]["emailAddress"]
    except Exception:
        return ""


# ── 认证流程 ──────────────────────────────────────────────────

def start_oauth_flow() -> None:
    """在后台线程中启动 OAuth 流程（会自动打开浏览器）"""
    t = threading.Thread(target=_oauth_thread, daemon=True)
    t.start()


def _oauth_thread() -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
        TOKEN_PATH.write_text(creds.to_json())
    except Exception as e:
        # 把错误写到临时文件，让 UI 侧读取
        (_BASE / ".oauth_error").write_text(str(e))


def get_oauth_error() -> str:
    """读取并清除 OAuth 错误信息（如有）"""
    err_file = _BASE / ".oauth_error"
    if err_file.exists():
        msg = err_file.read_text()
        err_file.unlink()
        return msg
    return ""


def revoke_auth() -> None:
    """断开连接（删除 token.json）"""
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()


# ── Drive 操作 ────────────────────────────────────────────────

def _get_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds)


def list_folders() -> list[dict]:
    """返回 Drive 中所有文件夹 [{id, name}, ...]，按名称排序"""
    try:
        svc = _get_service()
        results = svc.files().list(
            q="mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces="drive",
            fields="files(id, name)",
            pageSize=200,
            orderBy="name",
        ).execute()
        return results.get("files", [])
    except Exception:
        return []


def create_folder(name: str, parent_id: Optional[str] = None) -> Optional[str]:
    """在 Drive 创建文件夹，返回新文件夹 ID"""
    try:
        svc = _get_service()
        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            meta["parents"] = [parent_id]
        f = svc.files().create(body=meta, fields="id").execute()
        return f.get("id")
    except Exception:
        return None


def make_shareable(file_id: str) -> bool:
    """将文件或文件夹设为「知道链接的人均可查看」"""
    try:
        svc = _get_service()
        svc.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
        ).execute()
        return True
    except Exception:
        return False


def folder_link(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"


def copy_to_clipboard(text: str) -> None:
    """将文本复制到 macOS 剪贴板"""
    import subprocess
    subprocess.run(["pbcopy"], input=text.encode(), check=False)


def upload_file(
    local_path: str,
    folder_id: Optional[str] = None,
) -> tuple[bool, str]:
    """
    上传单个文件到 Drive。
    返回 (True, webViewLink) 或 (False, 错误信息)
    """
    try:
        from googleapiclient.http import MediaFileUpload

        svc = _get_service()
        file_name = os.path.basename(local_path)
        meta: dict = {"name": file_name}
        if folder_id:
            meta["parents"] = [folder_id]

        # 大文件使用 resumable 分块上传
        media = MediaFileUpload(
            local_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=8 * 1024 * 1024,  # 8MB 块
        )
        req = svc.files().create(body=meta, media_body=media, fields="id,webViewLink")

        response = None
        while response is None:
            _, response = req.next_chunk()

        return True, response.get("webViewLink", "")
    except Exception as e:
        return False, str(e)
