from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from http import cookies
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(os.getenv("POSTER_DB_PATH", DATA_DIR / "poster_tool.sqlite"))
SESSION_COOKIE = "poster_session"


@dataclass
class AccessUser:
    user_id: str
    name: str
    open_id: str = ""
    avatar_url: str = ""


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_csv(name: str) -> set[str]:
    return {item.strip() for item in os.getenv(name, "").split(",") if item.strip()}


def app_base_url() -> str:
    return os.getenv("APP_PUBLIC_BASE_URL", "http://127.0.0.1:8765").rstrip("/")


def admin_token() -> str:
    return os.getenv("ADMIN_TOKEN", "local-admin")


def feishu_app_id() -> str:
    return os.getenv("FEISHU_APP_ID", "")


def feishu_app_secret() -> str:
    return os.getenv("FEISHU_APP_SECRET", "")


def feishu_admin_open_id() -> str:
    return os.getenv("FEISHU_ADMIN_OPEN_ID", "")


def require_feishu_login() -> bool:
    return env_bool("FEISHU_REQUIRE_LOGIN", bool(feishu_app_id() and feishu_app_secret()))


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            create table if not exists users (
              user_id text primary key,
              open_id text,
              name text not null,
              avatar_url text,
              status text not null default 'pending',
              created_at integer not null,
              updated_at integer not null
            );
            create table if not exists sessions (
              token text primary key,
              user_id text not null,
              created_at integer not null
            );
            create table if not exists entry_passes (
              user_id text primary key,
              created_at integer not null
            );
            create table if not exists access_requests (
              id integer primary key autoincrement,
              user_id text not null,
              note text,
              status text not null default 'pending',
              created_at integer not null,
              updated_at integer not null
            );
            create table if not exists export_logs (
              id integer primary key autoincrement,
              user_id text not null,
              kind text not null,
              filename text not null,
              file_url text not null,
              item_count integer not null default 1,
              created_at integer not null
            );
            """
        )


def db() -> sqlite3.Connection:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_ts() -> int:
    return int(time.time())


def cookie_token(headers: Any) -> str:
    raw = headers.get("Cookie", "")
    jar = cookies.SimpleCookie()
    jar.load(raw)
    morsel = jar.get(SESSION_COOKIE)
    return morsel.value if morsel else ""


def session_cookie(token: str) -> str:
    jar = cookies.SimpleCookie()
    jar[SESSION_COOKIE] = token
    jar[SESSION_COOKIE]["path"] = "/"
    jar[SESSION_COOKIE]["httponly"] = True
    jar[SESSION_COOKIE]["samesite"] = "Lax"
    if app_base_url().startswith("https://"):
        jar[SESSION_COOKIE]["secure"] = True
    return jar.output(header="").strip()


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute(
            "insert into sessions (token, user_id, created_at) values (?, ?, ?)",
            (token, user_id, now_ts()),
        )
    return token


def mark_entry_pass(user_id: str) -> None:
    with db() as conn:
        conn.execute(
            """
            insert into entry_passes (user_id, created_at) values (?, ?)
            on conflict(user_id) do update set created_at = excluded.created_at
            """,
            (user_id, now_ts()),
        )


def has_recent_entry_pass(user_id: str, ttl_seconds: int = 600) -> bool:
    with db() as conn:
        row = conn.execute("select created_at from entry_passes where user_id = ?", (user_id,)).fetchone()
    if not row:
        return False
    return now_ts() - int(row["created_at"]) <= ttl_seconds


def user_from_session(headers: Any) -> AccessUser | None:
    token = cookie_token(headers)
    if not token:
        return None
    with db() as conn:
        row = conn.execute(
            """
            select users.* from sessions
            join users on users.user_id = sessions.user_id
            where sessions.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        return None
    return AccessUser(
        user_id=row["user_id"],
        open_id=row["open_id"] or "",
        name=row["name"],
        avatar_url=row["avatar_url"] or "",
    )


def ensure_user(user: AccessUser, default_status: str = "pending") -> None:
    ts = now_ts()
    with db() as conn:
        existing = conn.execute("select user_id from users where user_id = ?", (user.user_id,)).fetchone()
        if existing:
            conn.execute(
                "update users set open_id = ?, name = ?, avatar_url = ?, updated_at = ? where user_id = ?",
                (user.open_id, user.name, user.avatar_url, ts, user.user_id),
            )
        else:
            conn.execute(
                """
                insert into users (user_id, open_id, name, avatar_url, status, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (user.user_id, user.open_id, user.name, user.avatar_url, default_status, ts, ts),
            )


def dev_user() -> AccessUser:
    name = os.getenv("DEV_FEISHU_USER_NAME", "本地测试用户")
    user_id = os.getenv("DEV_FEISHU_USER_ID", "dev_user")
    open_id = os.getenv("DEV_FEISHU_OPEN_ID", user_id)
    user = AccessUser(user_id=user_id, open_id=open_id, name=name)
    ensure_user(user, default_status=os.getenv("DEV_ACCESS_STATUS", "approved"))
    return user


def get_user_status(user_id: str) -> str:
    if user_id in env_csv("FEISHU_APPROVED_OPEN_IDS"):
        return "approved"
    with db() as conn:
        row = conn.execute("select status from users where user_id = ?", (user_id,)).fetchone()
    return row["status"] if row else "none"


def is_approved(user: AccessUser) -> bool:
    approved_ids = env_csv("FEISHU_APPROVED_OPEN_IDS")
    if user.user_id in approved_ids or user.open_id in approved_ids:
        return True
    return get_user_status(user.user_id) == "approved"


def create_access_request(user: AccessUser, note: str = "") -> None:
    ensure_user(user)
    ts = now_ts()
    request_id = None
    with db() as conn:
        existing = conn.execute(
            "select id from access_requests where user_id = ? and status = 'pending'",
            (user.user_id,),
        ).fetchone()
        if existing:
            request_id = existing["id"]
            conn.execute(
                "update access_requests set note = ?, updated_at = ? where id = ?",
                (note, ts, existing["id"]),
            )
        else:
            cursor = conn.execute(
                """
                insert into access_requests (user_id, note, status, created_at, updated_at)
                values (?, ?, 'pending', ?, ?)
                """,
                (user.user_id, note, ts, ts),
            )
            request_id = cursor.lastrowid
    sent = notify_access_request(user, note, request_id)
    if sent:
        return
    notify_admin(
        f"权限申请：{user.name} 申请使用四星讲师海报工具。\n"
        f"审核地址：{app_base_url()}/admin/requests?admin_token={quote(admin_token())}"
    )


def set_user_status(user_id: str, status: str) -> None:
    ts = now_ts()
    with db() as conn:
        conn.execute("update users set status = ?, updated_at = ? where user_id = ?", (status, ts, user_id))
        conn.execute(
            "update access_requests set status = ?, updated_at = ? where user_id = ? and status = 'pending'",
            (status, ts, user_id),
        )


def get_user_name(user_id: str) -> str:
    with db() as conn:
        row = conn.execute("select name from users where user_id = ?", (user_id,)).fetchone()
    return row["name"] if row else user_id


def pending_requests() -> list[sqlite3.Row]:
    with db() as conn:
        return list(
            conn.execute(
                """
                select
                  access_requests.id,
                  access_requests.user_id,
                  access_requests.note,
                  access_requests.status,
                  access_requests.created_at,
                  access_requests.updated_at,
                  users.name,
                  users.open_id,
                  users.status as user_status
                from access_requests
                join users on users.user_id = access_requests.user_id
                union all
                select
                  0 as id,
                  users.user_id,
                  '' as note,
                  users.status,
                  users.created_at,
                  users.updated_at,
                  users.name,
                  users.open_id,
                  users.status as user_status
                from users
                where users.status = 'pending'
                  and not exists (
                    select 1 from access_requests
                    where access_requests.user_id = users.user_id
                      and access_requests.status = 'pending'
                  )
                order by updated_at desc
                """
            ).fetchall()
        )


def record_export(user: AccessUser, kind: str, filename: str, file_url: str, item_count: int = 1) -> None:
    with db() as conn:
        conn.execute(
            """
            insert into export_logs (user_id, kind, filename, file_url, item_count, created_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (user.user_id, kind, filename, file_url, item_count, now_ts()),
        )
    label = "批量导出" if kind == "batch" else "导出图片"
    notify_admin(
        f"{label}：{user.name} 已导出 {item_count} 个文件。\n"
        f"文件：{filename}\n"
        f"链接：{app_base_url()}{file_url}"
    )


def json_post(url: str, payload: dict, headers: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def json_get(url: str, headers: dict | None = None) -> dict:
    request = Request(url, headers=headers or {}, method="GET")
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def tenant_access_token() -> str:
    payload = {"app_id": feishu_app_id(), "app_secret": feishu_app_secret()}
    result = json_post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal", payload)
    return result.get("tenant_access_token", "")


def app_access_token() -> str:
    payload = {"app_id": feishu_app_id(), "app_secret": feishu_app_secret()}
    result = json_post("https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal", payload)
    return result.get("app_access_token", "")


def exchange_code_for_user(code: str) -> AccessUser:
    token = app_access_token()
    result = json_post(
        "https://open.feishu.cn/open-apis/authen/v1/access_token",
        {"grant_type": "authorization_code", "code": code},
        {"Authorization": f"Bearer {token}"},
    )
    data = result.get("data", result)
    user_access_token = data.get("access_token") or data.get("user_access_token")
    if not user_access_token:
        raise RuntimeError(f"飞书登录换取用户凭证失败：{result}")
    info = json_get(
        "https://open.feishu.cn/open-apis/authen/v1/user_info",
        {"Authorization": f"Bearer {user_access_token}"},
    )
    user_info = info.get("data", info)
    open_id = user_info.get("open_id") or data.get("open_id") or data.get("user_id", "")
    user_id = open_id or user_info.get("union_id") or user_info.get("user_id")
    name = user_info.get("name") or user_info.get("en_name") or "飞书用户"
    if not user_id:
        raise RuntimeError(f"飞书登录未返回用户身份：{info}")
    user = AccessUser(
        user_id=user_id,
        open_id=open_id,
        name=name,
        avatar_url=user_info.get("avatar_url", ""),
    )
    ensure_user(user)
    return user


def authorization_url(state: str = "poster") -> str:
    redirect_uri = f"{app_base_url()}/feishu/start"
    query = urlencode(
        {
            "app_id": feishu_app_id(),
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
    )
    return f"https://open.feishu.cn/open-apis/authen/v1/authorize?{query}"


def send_feishu_message(receive_id: str, text: str) -> bool:
    if not (feishu_app_id() and feishu_app_secret() and receive_id):
        print(f"[feishu notify skipped] {text}")
        return False
    token = tenant_access_token()
    if not token:
        print(f"[feishu notify failed] tenant_access_token missing: {text}")
        return False
    payload = {
        "receive_id": receive_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    result = json_post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        payload,
        {"Authorization": f"Bearer {token}"},
    )
    ok = result.get("code") in (0, None)
    if not ok:
        print(f"[feishu notify failed] {result}")
    return ok


def send_feishu_card(receive_id: str, card: dict) -> bool:
    if not (feishu_app_id() and feishu_app_secret() and receive_id):
        print(f"[feishu card skipped] {json.dumps(card, ensure_ascii=False)}")
        return False
    token = tenant_access_token()
    if not token:
        print(f"[feishu card failed] tenant_access_token missing: {json.dumps(card, ensure_ascii=False)}")
        return False
    payload = {
        "receive_id": receive_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    result = json_post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        payload,
        {"Authorization": f"Bearer {token}"},
    )
    ok = result.get("code") in (0, None)
    if not ok:
        print(f"[feishu card failed] {result}")
    return ok


def access_request_card(user: AccessUser, note: str, request_id: int | None) -> dict:
    note_text = note.strip() or "无申请说明"
    admin_url = f"{app_base_url()}/admin/requests?admin_token={quote(admin_token())}"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "四星讲师海报工具权限申请"},
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**申请人：**{user.name}\n**open_id：**{user.open_id or user.user_id}\n**说明：**{note_text}",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "同意"},
                        "type": "primary",
                        "value": {
                            "action": "approved",
                            "user_id": user.user_id,
                            "request_id": str(request_id or ""),
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "拒绝"},
                        "type": "danger",
                        "value": {
                            "action": "rejected",
                            "user_id": user.user_id,
                            "request_id": str(request_id or ""),
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "打开管理页"},
                        "type": "default",
                        "url": admin_url,
                    },
                ],
            },
        ],
    }


def notify_access_request(user: AccessUser, note: str, request_id: int | None) -> bool:
    return send_feishu_card(feishu_admin_open_id(), access_request_card(user, note, request_id))


def notify_admin(text: str) -> bool:
    return send_feishu_message(feishu_admin_open_id(), text)
