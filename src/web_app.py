from __future__ import annotations

from email.parser import BytesParser
from email.policy import default as email_policy
import html
import io
import json
import tempfile
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from app import PROJECT_ROOT, clean_filename, load_config, read_rows, render_teacher_image, save_rendered_image, with_output_format
from feishu_support import (
    AccessUser,
    admin_token,
    authorization_url,
    create_access_request,
    create_session,
    dev_user,
    exchange_code_for_user,
    get_user_name,
    get_user_status,
    has_recent_entry_pass,
    init_db,
    is_approved,
    mark_entry_pass,
    notify_admin,
    pending_requests,
    record_export,
    require_feishu_login,
    session_cookie,
    set_user_status,
    user_from_session,
)


WEB_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "web"
DEFAULT_PORTRAIT = "assets/portraits/李甲_transparent.png"


class UploadedField:
    def __init__(self, value: bytes, filename: str = "") -> None:
        self.value = value
        self.filename = filename
        self.file = io.BytesIO(value)

    @property
    def text(self) -> str:
        return self.value.decode("utf-8", errors="replace")


class ParsedForm:
    def __init__(self) -> None:
        self._items: dict[str, list[UploadedField]] = {}

    def add(self, name: str, field: UploadedField) -> None:
        self._items.setdefault(name, []).append(field)

    def __contains__(self, key: str) -> bool:
        return key in self._items

    def __getitem__(self, key: str):
        values = self._items[key]
        return values if len(values) > 1 else values[0]

    def getfirst(self, key: str, default: str = "") -> str:
        values = self._items.get(key)
        if not values:
            return default
        return values[0].text


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>四星讲师海报生成</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #12100d;
      --panel: #1c1812;
      --line: #6f5528;
      --line-soft: rgba(232, 196, 123, .28);
      --text: #fff8e8;
      --muted: #bba87d;
      --gold: #e8c47b;
      --field: #0f0d0a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    .app {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(360px, 440px) 1fr;
    }
    aside {
      border-right: 1px solid var(--line-soft);
      background: var(--panel);
      padding: 22px;
      overflow-y: auto;
    }
    main {
      display: grid;
      place-items: center;
      padding: 24px;
      min-width: 0;
    }
    h1 {
      margin: 0 0 18px;
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0;
    }
    label {
      display: block;
      margin: 16px 0 7px;
      color: var(--muted);
      font-size: 13px;
    }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line-soft);
      border-radius: 6px;
      background: var(--field);
      color: var(--text);
      padding: 10px 11px;
      font: inherit;
      outline: none;
    }
    input:focus, textarea:focus, select:focus {
      border-color: var(--gold);
      box-shadow: 0 0 0 2px rgba(232, 196, 123, .15);
    }
    textarea {
      min-height: 108px;
      resize: vertical;
      line-height: 1.55;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 120px;
      gap: 12px;
      align-items: end;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }
    button, a.download {
      appearance: none;
      border: 1px solid var(--gold);
      border-radius: 6px;
      background: var(--gold);
      color: #1b1205;
      cursor: pointer;
      font-weight: 700;
      padding: 10px 14px;
      text-decoration: none;
      text-align: center;
      min-height: 42px;
    }
    a.download {
      display: none;
      background: transparent;
      color: var(--gold);
    }
    .status {
      min-height: 22px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .divider {
      height: 1px;
      background: var(--line-soft);
      margin: 24px 0 18px;
    }
    .hint {
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .preview-shell {
      width: min(52vh, 480px);
      max-width: 100%;
      aspect-ratio: 750 / 1436;
      border: 1px solid var(--line-soft);
      background: #080604;
      display: grid;
      place-items: center;
      overflow: hidden;
    }
    .preview-shell img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: none;
    }
    .placeholder {
      color: var(--muted);
      font-size: 14px;
    }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      display: none;
      place-items: center;
      background: rgba(0, 0, 0, .62);
      padding: 20px;
      z-index: 10;
    }
    .modal {
      width: min(420px, 100%);
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      background: #1c1812;
      padding: 24px;
      box-shadow: 0 22px 70px rgba(0, 0, 0, .42);
    }
    .modal h2 {
      margin: 0 0 10px;
      font-size: 22px;
    }
    .modal p {
      margin: 0 0 20px;
      color: var(--muted);
      line-height: 1.6;
    }
    .modal button {
      width: 100%;
    }
    @media (max-width: 860px) {
      .app { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line-soft); }
      .preview-shell { width: min(88vw, 430px); }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <h1>四星讲师海报</h1>
      <form id="posterForm">
        <div class="row">
          <div>
            <label for="name">讲师姓名</label>
            <input id="name" name="name" value="李甲" autocomplete="off">
          </div>
          <div>
            <label for="format">格式</label>
            <select id="format" name="format">
              <option value="png">PNG</option>
              <option value="jpg">JPG</option>
            </select>
          </div>
        </div>

        <label for="project_experience">项目经历</label>
        <textarea id="project_experience" name="project_experience">服务10+主机厂和区域的新媒体提升辅导
问界打深耕深圳站集训及多店全链路入店提升辅导
比亚迪王朝云贵川战区新媒体直播获客专项辅导</textarea>

        <label for="bio">底部介绍</label>
        <textarea id="bio" name="bio">实战派辅导老师，14年汽车行业经验，6年新媒体经验，擅长新媒体全链路SOP集训/入店辅导，能快速切入门店痛点，用大白话讲专业方法，帮助学员拿到更有效的本地线索和成交闭环。</textarea>

        <label for="portrait">人像（无背景png人像）</label>
        <input id="portrait" name="portrait" type="file" accept="image/png,image/jpeg,image/webp">

        <label for="output_filename">文件名</label>
        <input id="output_filename" name="output_filename" value="李甲_四星讲师.png" autocomplete="off">

        <div class="actions">
          <button id="generateBtn" type="submit">导出图片</button>
          <a id="downloadBtn" class="download" href="#" download>下载海报</a>
        </div>
        <div id="status" class="status"></div>
      </form>

      <div class="divider"></div>
      <h1>批量生成</h1>
      <form id="batchForm">
        <label for="batch_table">讲师表格</label>
        <input id="batch_table" name="batch_table" type="file" accept=".xlsx,.xlsm,.csv">
        <div class="hint">表格字段：讲师姓名、项目经历、底部介绍（服务过的品牌与介绍写在一起，自行换行区分即可）、人像照片。人像照片可写路径/文件名，也可以直接把图片插入对应行。</div>

        <label for="batch_portraits">人像图片</label>
        <input id="batch_portraits" name="batch_portraits" type="file" accept="image/png,image/jpeg,image/webp" multiple>
        <div class="hint">表格里“人像照片”可以写图片路径/文件名或插入图片；也可以在这里单独上传多张人像，程序会按文件名匹配。两种方式都支持。</div>

        <label for="batch_format">导出格式</label>
        <select id="batch_format" name="format">
          <option value="png">PNG</option>
          <option value="jpg">JPG</option>
        </select>

        <div class="actions">
          <button id="batchBtn" type="submit">批量导出并下载</button>
          <a id="batchDownloadBtn" class="download" href="#" download>下载压缩包</a>
        </div>
        <div id="batchStatus" class="status"></div>
      </form>
    </aside>
    <main>
      <div class="preview-shell">
        <img id="preview" alt="海报预览">
        <div id="placeholder" class="placeholder">等待预览</div>
      </div>
    </main>
  </div>
  <div id="successModal" class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="successTitle">
    <div class="modal">
      <h2 id="successTitle">导出成功</h2>
      <p>海报已生成，使用记录已推送给管理员。</p>
      <button id="successCloseBtn" type="button">给设计师＋鸡腿</button>
    </div>
  </div>
  <script>
    const form = document.getElementById('posterForm');
    const preview = document.getElementById('preview');
    const placeholder = document.getElementById('placeholder');
    const statusEl = document.getElementById('status');
    const downloadBtn = document.getElementById('downloadBtn');
    const batchForm = document.getElementById('batchForm');
    const batchStatusEl = document.getElementById('batchStatus');
    const batchDownloadBtn = document.getElementById('batchDownloadBtn');
    const successModal = document.getElementById('successModal');
    const successCloseBtn = document.getElementById('successCloseBtn');
    let timer = null;
    let controller = null;

    function setStatus(text) {
      statusEl.textContent = text;
    }

    function showSuccessModal() {
      successModal.style.display = 'grid';
    }

    function hideSuccessModal() {
      successModal.style.display = 'none';
    }

    async function generate(intent = 'preview') {
      if (controller) controller.abort();
      controller = new AbortController();
      const data = new FormData(form);
      data.append('intent', intent);
      setStatus(intent === 'export' ? '导出中...' : '生成中...');
      try {
        const res = await fetch('/api/render', {
          method: 'POST',
          body: data,
          signal: controller.signal
        });
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || '生成失败');
        preview.src = payload.preview_url + '?t=' + Date.now();
        preview.style.display = 'block';
        placeholder.style.display = 'none';
        downloadBtn.href = payload.download_url;
        downloadBtn.setAttribute('download', payload.filename);
        downloadBtn.style.display = 'inline-block';
        setStatus(intent === 'export' ? '已导出，已通知管理员' : '已生成预览');
        if (intent === 'export') showSuccessModal();
      } catch (err) {
        if (err.name === 'AbortError') return;
        setStatus(err.message);
      }
    }

    function scheduleGenerate() {
      clearTimeout(timer);
      timer = setTimeout(generate, 650);
    }

    form.addEventListener('submit', (event) => {
      event.preventDefault();
      generate('export');
    });

    successCloseBtn.addEventListener('click', hideSuccessModal);
    successModal.addEventListener('click', (event) => {
      if (event.target === successModal) hideSuccessModal();
    });

    batchForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const table = document.getElementById('batch_table');
      if (!table.files.length) {
        batchStatusEl.textContent = '请先选择讲师表格';
        return;
      }
      batchStatusEl.textContent = '批量生成中...';
      batchDownloadBtn.style.display = 'none';
      try {
        const data = new FormData(batchForm);
        const res = await fetch('/api/batch', { method: 'POST', body: data });
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || '批量生成失败');
        batchDownloadBtn.href = payload.download_url;
        batchDownloadBtn.setAttribute('download', payload.filename);
        batchDownloadBtn.style.display = 'inline-block';
        batchStatusEl.textContent = `已生成 ${payload.count} 张`;
      } catch (err) {
        batchStatusEl.textContent = err.message;
      }
    });

    ['input', 'change'].forEach((eventName) => {
      form.addEventListener(eventName, (event) => {
        if (event.target.id === 'portrait') {
          generate('preview');
        } else if (event.target.closest('#batchForm')) {
          return;
        } else {
          scheduleGenerate();
        }
      });
    });

    generate('preview');
  </script>
</body>
</html>
"""


class PosterRequestHandler(BaseHTTPRequestHandler):
    server_version = "PosterWeb/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/feishu/entry":
            user = self.current_user(parsed)
            if user is None:
                return
            mark_entry_pass(user.user_id)
            self.send_redirect("/feishu/start")
            return
        if parsed.path in {"/", "/feishu/start"}:
            user = self.current_user(parsed)
            if user is None:
                return
            if require_feishu_login() and not has_recent_entry_pass(user.user_id):
                self.send_entry_required_page()
                return
            if not is_approved(user):
                self.send_access_page(user)
                return
            self.send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/feishu/me":
            user = self.current_user(parsed)
            if user is None:
                return
            self.send_me_page(user)
            return
        if parsed.path == "/admin/requests":
            self.send_admin_page(parsed)
            return
        if parsed.path == "/healthz":
            self.send_json({"ok": True})
            return
        if parsed.path.startswith("/outputs/web/"):
            self.serve_output(parsed.path)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/feishu/card/callback":
                self.handle_feishu_card_callback()
                return
            if parsed.path == "/access/request":
                user = self.current_user(parsed)
                if user is None:
                    return
                form = self.parse_form()
                create_access_request(user, self.form_value(form, "note", ""))
                self.send_access_page(user, "申请已提交，我会在飞书里收到提醒。")
                return

            user = self.current_user(parsed)
            if user is None:
                return
            if not is_approved(user):
                self.send_json({"error": "你还没有使用权限，请先申请。"}, status=403)
                return
            if parsed.path == "/api/render":
                payload = self.render_from_form(user)
            elif parsed.path == "/api/batch":
                payload = self.batch_from_form(user)
            else:
                self.send_error(404)
                return
            self.send_json(payload)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)

    def handle_feishu_card_callback(self) -> None:
        payload = self.parse_json_body()
        challenge = payload.get("challenge")
        if challenge:
            self.send_json({"challenge": challenge})
            return

        value = self.find_action_value(payload)
        action = str(value.get("action", ""))
        user_id = str(value.get("user_id", ""))
        if action not in {"approved", "rejected"} or not user_id:
            self.send_json({"toast": {"type": "warning", "content": "无法识别这次操作"}})
            return

        set_user_status(user_id, action)
        user_name = get_user_name(user_id)
        action_text = "已同意" if action == "approved" else "已拒绝"
        notify_admin(f"权限审核：{user_name} {action_text}。")
        self.send_json(
            {
                "toast": {
                    "type": "success",
                    "content": f"{action_text} {user_name} 的使用申请",
                }
            }
        )

    def parse_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

    def find_action_value(self, payload: dict) -> dict:
        candidates = [
            payload.get("action", {}),
            payload.get("event", {}).get("action", {}),
            payload.get("action", {}).get("value", {}),
            payload.get("event", {}).get("action", {}).get("value", {}),
        ]
        for candidate in candidates:
            if isinstance(candidate, dict) and "value" in candidate and isinstance(candidate["value"], dict):
                return candidate["value"]
            if isinstance(candidate, dict) and "action" in candidate and "user_id" in candidate:
                return candidate
        return {}

    def current_user(self, parsed) -> AccessUser | None:
        query = parse_qs(parsed.query)
        if "code" in query:
            try:
                user = exchange_code_for_user(query["code"][0])
            except Exception as exc:
                self.send_bytes(
                    self.basic_page("登录失败", f"飞书身份验证失败：{html.escape(str(exc))}").encode("utf-8"),
                    "text/html; charset=utf-8",
                    500,
                )
                return None
            token = create_session(user.user_id)
            self.send_redirect("/", {"Set-Cookie": session_cookie(token)})
            return None

        user = user_from_session(self.headers)
        if user is not None:
            return user

        if not require_feishu_login():
            return dev_user()

        self.send_redirect(authorization_url())
        return None

    def send_access_page(self, user: AccessUser, message: str = "") -> None:
        status = get_user_status(user.user_id)
        status_text = {
            "pending": "申请审核中",
            "rejected": "申请未通过",
            "none": "尚未申请",
        }.get(status, status)
        body = f"""
        <p class="muted">当前用户：{html.escape(user.name)}</p>
        <p>状态：{html.escape(status_text)}</p>
        {f'<p class="ok">{html.escape(message)}</p>' if message else ''}
        <form method="post" action="/access/request">
          <label for="note">申请说明</label>
          <textarea id="note" name="note"></textarea>
          <button type="submit">申请使用权限</button>
        </form>
        """
        self.send_bytes(self.basic_page("四星讲师海报工具", body).encode("utf-8"), "text/html; charset=utf-8")

    def send_entry_required_page(self) -> None:
        body = f"""
        <p class="muted">如果你刚刚从飞书进入，可以重新点击一次机器人菜单。</p>
        <a class="button" href="/feishu/entry">重新进入</a>
        """
        self.send_bytes(self.basic_page("请从飞书入口打开", body).encode("utf-8"), "text/html; charset=utf-8", 403)

    def send_me_page(self, user: AccessUser) -> None:
        body = f"""
        <p class="muted">把下面这行填到云端环境变量 <code>FEISHU_ADMIN_OPEN_ID</code>。</p>
        <section class="request">
          <p>姓名：{html.escape(user.name)}</p>
          <p>open_id：</p>
          <pre>{html.escape(user.open_id or user.user_id)}</pre>
        </section>
        """
        self.send_bytes(self.basic_page("我的飞书身份", body).encode("utf-8"), "text/html; charset=utf-8")

    def send_admin_page(self, parsed) -> None:
        query = parse_qs(parsed.query)
        if query.get("admin_token", [""])[0] != admin_token():
            self.send_error(403)
            return

        action = query.get("action", [""])[0]
        user_id = query.get("user_id", [""])[0]
        if action in {"approved", "rejected"} and user_id:
            set_user_status(user_id, action)
            self.send_redirect(f"/admin/requests?admin_token={admin_token()}")
            return

        rows = pending_requests()
        items = []
        for row in rows:
            approve_url = f"/admin/requests?admin_token={admin_token()}&action=approved&user_id={row['user_id']}"
            reject_url = f"/admin/requests?admin_token={admin_token()}&action=rejected&user_id={row['user_id']}"
            items.append(
                f"""
                <section class="request">
                  <strong>{html.escape(row['name'])}</strong>
                  <p class="muted">状态：{html.escape(row['user_status'])}｜open_id：{html.escape(row['open_id'] or '-')}</p>
                  <p>{html.escape(row['note'] or '无申请说明')}</p>
                  <a class="button" href="{approve_url}">同意</a>
                  <a class="button secondary" href="{reject_url}">拒绝</a>
                </section>
                """
            )
        body = "".join(items) or "<p>暂无申请记录。</p>"
        self.send_bytes(self.basic_page("权限申请管理", body).encode("utf-8"), "text/html; charset=utf-8")

    def basic_page(self, title: str, body: str) -> str:
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; background: #12100d; color: #fff8e8; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; }}
    main {{ max-width: 720px; margin: 0 auto; padding: 40px 22px; }}
    h1 {{ font-size: 24px; margin: 0 0 20px; }}
    p {{ line-height: 1.7; }}
    .muted {{ color: #bba87d; }}
    .ok {{ color: #e8c47b; }}
    textarea {{ width: 100%; min-height: 120px; border: 1px solid rgba(232,196,123,.32); border-radius: 6px; background: #0f0d0a; color: #fff8e8; padding: 12px; font: inherit; }}
    code, pre {{ background: #0f0d0a; border: 1px solid rgba(232,196,123,.28); border-radius: 6px; color: #e8c47b; }}
    code {{ padding: 2px 5px; }}
    pre {{ padding: 12px; overflow-x: auto; }}
    button, .button {{ display: inline-block; border: 1px solid #e8c47b; border-radius: 6px; background: #e8c47b; color: #1b1205; cursor: pointer; font-weight: 700; padding: 10px 14px; text-decoration: none; margin: 10px 8px 0 0; }}
    .secondary {{ background: transparent; color: #e8c47b; }}
    .request {{ border: 1px solid rgba(232,196,123,.28); border-radius: 8px; padding: 16px; margin: 14px 0; }}
  </style>
</head>
<body><main><h1>{html.escape(title)}</h1>{body}</main></body>
</html>"""

    def parse_form(self) -> ParsedForm:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        form = ParsedForm()
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            return form

        raw_message = (
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {content_length}\r\n"
            "MIME-Version: 1.0\r\n\r\n"
        ).encode("utf-8") + body
        message = BytesParser(policy=email_policy).parsebytes(raw_message)
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            filename = part.get_filename() or ""
            payload = part.get_payload(decode=True) or b""
            form.add(name, UploadedField(payload, filename))
        return form

    def render_from_form(self, user: AccessUser) -> dict:
        form = self.parse_form()
        intent = self.form_value(form, "intent", "preview")
        output_format = self.form_value(form, "format", "png").lower()
        if output_format == "jpeg":
            output_format = "jpg"
        if output_format not in {"png", "jpg"}:
            raise ValueError("Unsupported output format.")

        portrait_path = DEFAULT_PORTRAIT
        portrait_item = form["portrait"] if "portrait" in form else None
        temp_path = None
        if portrait_item is not None and getattr(portrait_item, "filename", ""):
            suffix = Path(portrait_item.filename).suffix or ".png"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
                temp.write(portrait_item.file.read())
                temp_path = Path(temp.name)
            portrait_path = str(temp_path)

        name = self.form_value(form, "name", "讲师")
        output_filename = self.form_value(form, "output_filename", f"{name}_四星讲师.{output_format}")
        output_filename = Path(output_filename).with_suffix(f".{output_format}").name
        file_id = uuid.uuid4().hex[:12]
        filename = f"{Path(output_filename).stem}_{file_id}.{output_format}"
        output_path = WEB_OUTPUT_DIR / filename

        row = {
            "name": name,
            "project_experience": self.form_value(form, "project_experience", ""),
            "bio": self.form_value(form, "bio", ""),
            "portrait_path": portrait_path,
            "output_filename": filename,
        }
        config = load_config("four_star")
        image = render_teacher_image(config, row)
        save_rendered_image(image, output_path)

        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

        url = f"/outputs/web/{filename}"
        if intent == "export":
            record_export(user, "single", output_filename, url)
        return {
            "preview_url": url,
            "download_url": url,
            "filename": output_filename,
        }

    def batch_from_form(self, user: AccessUser) -> dict:
        form = self.parse_form()
        table_item = form["batch_table"] if "batch_table" in form else None
        if table_item is None or not getattr(table_item, "filename", ""):
            raise ValueError("请上传讲师表格。")

        output_format = self.form_value(form, "format", "png").lower()
        if output_format == "jpeg":
            output_format = "jpg"
        if output_format not in {"png", "jpg"}:
            raise ValueError("Unsupported output format.")

        temp_paths: list[Path] = []
        table_suffix = Path(table_item.filename).suffix or ".xlsx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=table_suffix) as temp_table:
            temp_table.write(table_item.file.read())
            table_path = Path(temp_table.name)
        temp_paths.append(table_path)

        uploaded_portraits: dict[str, Path] = {}
        portrait_items = []
        if "batch_portraits" in form:
            raw_items = form["batch_portraits"]
            portrait_items = raw_items if isinstance(raw_items, list) else [raw_items]
        for item in portrait_items:
            if not getattr(item, "filename", ""):
                continue
            suffix = Path(item.filename).suffix or ".png"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_portrait:
                temp_portrait.write(item.file.read())
                portrait_path = Path(temp_portrait.name)
            temp_paths.append(portrait_path)
            uploaded_portraits[Path(item.filename).name] = portrait_path
            uploaded_portraits[Path(item.filename).stem] = portrait_path

        rows = read_rows(table_path)
        if not rows:
            raise ValueError("表格里没有讲师数据。")

        batch_id = uuid.uuid4().hex[:12]
        batch_dir = WEB_OUTPUT_DIR / f"batch_{batch_id}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        zip_path = WEB_OUTPUT_DIR / f"batch_{batch_id}.zip"
        config = load_config("four_star")
        generated: list[Path] = []

        for index, row in enumerate(rows, start=1):
            name = str(row.get("name", "")).strip() or f"讲师{index}"
            row["name"] = name
            row["project_experience"] = str(row.get("project_experience", "")).strip()
            row["bio"] = str(row.get("bio", "")).strip()
            portrait_value = str(row.get("portrait_path", "")).strip()
            matched_portrait = self.match_portrait(portrait_value, uploaded_portraits)
            row["portrait_path"] = str(matched_portrait or (PROJECT_ROOT / DEFAULT_PORTRAIT))
            filename = row.get("output_filename") or f"{name}_四星讲师.{output_format}"
            filename = with_output_format(clean_filename(filename), output_format)
            row["output_filename"] = filename
            image = render_teacher_image(config, row)
            output_path = batch_dir / filename
            save_rendered_image(image, output_path)
            generated.append(output_path)

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for path in generated:
                zip_file.write(path, arcname=path.name)

        for path in temp_paths:
            path.unlink(missing_ok=True)

        url = f"/outputs/web/{zip_path.name}"
        record_export(user, "batch", zip_path.name, url, len(generated))
        return {
            "download_url": url,
            "filename": zip_path.name,
            "count": len(generated),
        }

    def match_portrait(self, value: str, uploaded_portraits: dict[str, Path]) -> Path | None:
        if value:
            value_path = Path(value)
            for key in (value_path.name, value_path.stem, value):
                if key in uploaded_portraits:
                    return uploaded_portraits[key]
            candidate = (PROJECT_ROOT / value).resolve()
            if candidate.exists():
                return candidate
            assets_candidate = (PROJECT_ROOT / "assets" / "portraits" / value_path.name).resolve()
            if assets_candidate.exists():
                return assets_candidate
        return None

    def form_value(self, form: cgi.FieldStorage, key: str, default: str = "") -> str:
        if key not in form:
            return default
        value = form.getfirst(key, default)
        return str(value).strip()

    def serve_output(self, path: str) -> None:
        filename = Path(unquote(path)).name
        output_path = WEB_OUTPUT_DIR / filename
        if not output_path.exists():
            self.send_error(404)
            return
        content_type = "image/png" if output_path.suffix.lower() == ".png" else "image/jpeg"
        if output_path.suffix.lower() == ".zip":
            content_type = "application/zip"
        self.send_bytes(output_path.read_bytes(), content_type)

    def send_json(self, payload: dict, status: int = 200) -> None:
        self.send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_redirect(self, location: str, headers: dict | None = None) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()


def main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8765")))
    args = parser.parse_args()

    init_db()
    WEB_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), PosterRequestHandler)
    print(f"http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
