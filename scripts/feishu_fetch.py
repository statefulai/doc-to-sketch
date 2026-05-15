#!/usr/bin/env python3
"""feishu_fetch.py — 飞书文档 → Markdown

给定飞书文档 URL（docx 或 wiki），输出 Markdown 文本。
供 doc-to-sketch Skill workflow 内部调用，用户无需手动执行。

用法：
    # 可选预授权（fetch 首次读取时也会自动触发浏览器授权）
    python3 scripts/feishu_fetch.py auth

    # 读取文档
    python3 scripts/feishu_fetch.py fetch "https://xxx.feishu.cn/docx/xxxxx"
    python3 scripts/feishu_fetch.py fetch "https://xxx.feishu.cn/wiki/xxxxx"

    # 高级：自定义飞书应用凭证（可选覆盖）
    export FEISHU_APP_ID=xxx
    export FEISHU_APP_SECRET=xxx
"""

import argparse
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"
FEISHU_ACCOUNTS_URL = "https://accounts.feishu.cn/open-apis"
TOKEN_DIR = Path.home() / ".doc-to-sketch"
TOKEN_FILE = TOKEN_DIR / "token.json"
CALLBACK_PORT = 19823
REQUIRED_SCOPES = "docx:document:readonly wiki:wiki:readonly offline_access"
TOKEN_REFRESH_BUFFER = 300
AUTH_TIMEOUT = 300

BLOCK_TYPE_TO_KEY = {
    1: "page",
    2: "text",
    3: "heading1",
    4: "heading2",
    5: "heading3",
    6: "heading4",
    7: "heading5",
    8: "heading6",
    9: "heading7",
    10: "heading8",
    11: "heading9",
    12: "bullet",
    13: "ordered",
    14: "code",
    15: "quote",
    19: "callout",
    22: "divider",
    27: "image",
    31: "table",
    32: "table_cell",
}

CODE_LANGUAGE_MAP = {
    1: "",
    7: "bash",
    8: "csharp",
    9: "cpp",
    10: "c",
    12: "css",
    15: "dart",
    18: "dockerfile",
    22: "go",
    24: "html",
    27: "haskell",
    28: "json",
    29: "java",
    30: "javascript",
    32: "kotlin",
    36: "lua",
    38: "makefile",
    39: "markdown",
    43: "php",
    44: "perl",
    46: "powershell",
    48: "protobuf",
    49: "python",
    50: "r",
    52: "ruby",
    53: "rust",
    55: "scss",
    56: "sql",
    57: "scala",
    60: "shell",
    61: "swift",
    63: "typescript",
    66: "xml",
    67: "yaml",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FeishuError(Exception):
    """飞书相关错误的基类。"""


class ConfigError(FeishuError):
    """环境变量或配置缺失。"""


class URLError(FeishuError):
    """URL 不支持或无法解析。"""


class AuthError(FeishuError):
    """授权失败或 token 无效。"""


class APIError(FeishuError):
    """飞书 API 调用失败。"""


def _normalize_scopes(scope_value: str) -> str:
    return " ".join(sorted(part for part in scope_value.split() if part))


# ---------------------------------------------------------------------------
# FeishuAuth — OAuth 授权
# ---------------------------------------------------------------------------

class FeishuAuth:
    """OAuth 2.0 user_access_token 授权管理。"""

    # 默认共享应用凭证用于零配置授权；企业/敏感场景可用环境变量覆盖。
    # 共享应用身份可被公开复用，因此只申请只读最小权限并在文档中说明边界。
    DEFAULT_APP_ID = "cli_aa8f1a91c5f8dcc5"
    DEFAULT_APP_SECRET = "R0pl3isjR61AsfjFx8OLmdRnysuQVZoX"

    def __init__(self):
        self.app_id = os.environ.get("FEISHU_APP_ID") or self.DEFAULT_APP_ID
        self.app_secret = os.environ.get("FEISHU_APP_SECRET") or self.DEFAULT_APP_SECRET

    def login(self) -> dict:
        """启动 OAuth 授权流程：打开浏览器 + localhost 回调接收 code。"""
        redirect_uri = f"http://localhost:{CALLBACK_PORT}/callback"
        state = secrets.token_urlsafe(24)
        result = {"code": None, "state": None, "error": None}
        completed = threading.Event()

        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != "/callback":
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write("Not Found".encode("utf-8"))
                    return

                query = urllib.parse.parse_qs(parsed.query)
                result["code"] = query.get("code", [None])[0]
                result["state"] = query.get("state", [None])[0]
                result["error"] = query.get("error_description", query.get("error", [None]))[0]

                if result["state"] != state:
                    result["error"] = "授权状态校验失败，请重新运行 auth 授权"
                elif not result["code"] and not result["error"]:
                    result["error"] = "授权失败，未收到授权码"

                body = (
                    "<html><body><h1>飞书授权完成</h1>"
                    "<p>可以关闭此窗口并返回终端。</p></body></html>"
                )
                if result["error"]:
                    body = (
                        "<html><body><h1>飞书授权失败</h1>"
                        "<p>请返回终端查看错误信息后重试。</p></body></html>"
                    )

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))
                completed.set()

            def log_message(self, format: str, *args) -> None:
                return

        try:
            server = http.server.ThreadingHTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
        except OSError as exc:
            raise AuthError(
                f"无法启动本地回调服务，请确认 {CALLBACK_PORT} 端口未被占用；"
                f"自建飞书应用需配置回调地址 http://localhost:{CALLBACK_PORT}/callback"
            ) from exc

        server.daemon_threads = True
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            params = urllib.parse.urlencode(
                {
                    "client_id": self.app_id,
                    "response_type": "code",
                    "redirect_uri": redirect_uri,
                    "scope": REQUIRED_SCOPES,
                    "state": state,
                }
            )
            authorize_url = f"{FEISHU_ACCOUNTS_URL}/authen/v1/authorize?{params}"

            print(
                "需要在浏览器中完成飞书授权；授权成功后将继续读取文档。\n"
                f"自建飞书应用需配置回调地址：http://localhost:{CALLBACK_PORT}/callback",
                file=sys.stderr,
            )
            if not webbrowser.open(authorize_url):
                print(
                    "浏览器未能自动打开，请手动打开以下链接完成飞书授权：\n"
                    f"{authorize_url}",
                    file=sys.stderr,
                )

            if not completed.wait(AUTH_TIMEOUT):
                raise AuthError("授权超时，请重新运行 auth 命令")

            if result["error"]:
                raise AuthError(str(result["error"]))
            if result["state"] != state:
                raise AuthError("授权状态校验失败，请重新运行 auth 授权")
            if not result["code"]:
                raise AuthError("授权失败，未收到授权码")

            token_data = self._exchange_code(str(result["code"]))
            self._save_token(token_data)
            return token_data
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)

    def get_token(self) -> str:
        """获取有效的 user_access_token（自动刷新过期 token）。

        Raises:
            AuthError: 未授权或刷新失败。
        """
        token_data = self._load_token()
        if token_data is None:
            raise AuthError("本地没有飞书授权 token，需要完成浏览器授权")

        access_token = str(token_data.get("access_token", ""))
        refresh_token = str(token_data.get("refresh_token", ""))
        obtained_at = float(token_data.get("obtained_at", 0))
        expires_in = int(token_data.get("expires_in", 0))

        if not access_token:
            raise AuthError("本地授权信息无效，请重新运行 auth 授权")

        if time.time() >= obtained_at + expires_in - TOKEN_REFRESH_BUFFER:
            if not refresh_token:
                raise AuthError("Token 已过期，请重新运行 auth 授权")
            try:
                token_data = self._refresh_token(refresh_token)
            except AuthError as exc:
                raise AuthError("Token 刷新失败，请重新运行 auth 授权") from exc
            self._save_token(token_data)
            access_token = str(token_data.get("access_token", ""))

        if not access_token:
            raise AuthError("Token 刷新失败，请重新运行 auth 授权")
        return access_token

    def _exchange_code(self, code: str) -> dict:
        """code → user_access_token + refresh_token。"""
        redirect_uri = f"http://localhost:{CALLBACK_PORT}/callback"
        return self._request_token(
            {
                "grant_type": "authorization_code",
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            }
        )

    def _refresh_token(self, refresh_token: str) -> dict:
        """refresh_token → 新 user_access_token。"""
        return self._request_token(
            {
                "grant_type": "refresh_token",
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "refresh_token": refresh_token,
            }
        )

    def _load_token(self) -> dict | None:
        """从 ~/.doc-to-sketch/token.json 加载 token。"""
        if not TOKEN_FILE.exists():
            return None

        try:
            with TOKEN_FILE.open("r", encoding="utf-8") as fh:
                token_data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise AuthError("本地 token 文件已损坏，请重新运行 auth 授权") from exc
        except OSError as exc:
            raise AuthError("无法读取本地 token 文件，请检查权限设置") from exc

        stored_scopes = str(token_data.get("required_scopes") or token_data.get("scope") or "")
        if _normalize_scopes(stored_scopes) != _normalize_scopes(REQUIRED_SCOPES):
            raise AuthError("代码权限需求已更新，请重新运行 auth 授权")

        stored_app_id = str(token_data.get("app_id") or "")
        if not stored_app_id:
            raise AuthError("本地授权信息缺少应用标识，请重新完成飞书授权")
        if stored_app_id != self.app_id:
            raise AuthError("飞书应用配置已变更，请重新完成飞书授权")

        return token_data

    def _save_token(self, token_data: dict) -> None:
        """写入 ~/.doc-to-sketch/token.json（权限 600）。"""
        payload = dict(token_data)
        payload["required_scopes"] = REQUIRED_SCOPES
        payload["app_id"] = self.app_id

        try:
            TOKEN_DIR.mkdir(parents=True, exist_ok=True)
            with TOKEN_FILE.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.chmod(TOKEN_FILE, 0o600)
        except OSError as exc:
            raise AuthError("无法保存本地 token，请检查目录权限") from exc

    def _request_token(self, payload: dict) -> dict:
        url = f"{FEISHU_BASE_URL}/authen/v2/oauth/token"
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

        try:
            with urllib.request.urlopen(request) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore").strip()
            if detail:
                raise AuthError(f"飞书授权失败：{detail}") from exc
            raise AuthError(f"飞书授权接口调用失败（HTTP {exc.code}）") from exc
        except urllib.error.URLError as exc:
            raise AuthError(f"无法连接飞书授权服务：{exc.reason}") from exc

        try:
            response_data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuthError("飞书授权接口返回了无效响应") from exc

        if response_data.get("code") != 0:
            message = response_data.get("msg") or response_data.get("message") or "未知错误"
            raise AuthError(f"飞书授权失败：{message}")

        return {
            "access_token": response_data.get("access_token", ""),
            "expires_in": response_data.get("expires_in", 0),
            "refresh_token": response_data.get("refresh_token", ""),
            "refresh_token_expires_in": response_data.get("refresh_token_expires_in", 0),
            "scope": response_data.get("scope", ""),
            "token_type": response_data.get("token_type", "Bearer"),
            "obtained_at": time.time(),
        }


# ---------------------------------------------------------------------------
# FeishuClient — HTTP 客户端
# ---------------------------------------------------------------------------

class FeishuClient:
    """统一 HTTP 请求，自动附加 Authorization header。"""

    def __init__(self, auth: FeishuAuth):
        self.auth = auth

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        """统一 HTTP 请求。"""
        url = f"{FEISHU_BASE_URL}{path}"
        token = self.auth.get_token()

        for attempt in range(2):
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
            data = None
            if body is not None:
                headers["Content-Type"] = "application/json; charset=utf-8"
                data = json.dumps(body).encode("utf-8")

            request = urllib.request.Request(
                url,
                data=data,
                method=method.upper(),
                headers=headers,
            )

            try:
                with urllib.request.urlopen(request) as response:
                    raw = response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                if exc.code == 401 and attempt == 0:
                    token_data = self.auth._load_token()
                    refresh_token = "" if token_data is None else str(token_data.get("refresh_token", ""))
                    if not refresh_token:
                        raise AuthError("Token 已失效，请重新运行 auth 授权") from exc
                    try:
                        token_data = self.auth._refresh_token(refresh_token)
                    except AuthError as refresh_exc:
                        raise AuthError("Token 刷新失败，请重新运行 auth 授权") from refresh_exc
                    self.auth._save_token(token_data)
                    token = str(token_data.get("access_token", ""))
                    continue
                if exc.code == 403:
                    raise APIError("当前用户无权访问此文档") from exc
                if exc.code == 404:
                    raise APIError("文档 ID 无效或已被删除") from exc
                detail = exc.read().decode("utf-8", errors="ignore").strip()
                if detail:
                    raise APIError(f"飞书 API 请求失败（HTTP {exc.code}）：{detail}") from exc
                raise APIError(f"飞书 API 请求失败（HTTP {exc.code}）") from exc
            except urllib.error.URLError as exc:
                raise APIError(f"无法连接飞书 API：{exc.reason}") from exc

            try:
                response_data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise APIError("飞书 API 返回了无效响应") from exc

            if response_data.get("code") != 0:
                message = response_data.get("msg") or response_data.get("message") or "未知错误"
                raise APIError(f"飞书 API 调用失败：{message}")

            return response_data.get("data", {})

        raise AuthError("Token 刷新失败，请重新运行 auth 授权")


# ---------------------------------------------------------------------------
# DocumentFetcher — URL 解析 + blocks 分页 + 递归
# ---------------------------------------------------------------------------

class DocumentFetcher:
    """从飞书 URL 获取 block 树。"""

    def __init__(self, client: FeishuClient):
        self.client = client

    @staticmethod
    def parse_url(url: str) -> tuple[str, str]:
        """从飞书文档 URL 提取 (url_type, token)。

        Returns:
            ("docx", document_id) 或 ("wiki", node_token)

        Raises:
            URLError: URL 不支持或无法解析。
        """
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if not host.endswith((".feishu.cn", ".lark.suite.com", ".larksuite.com")):
            raise URLError("当前只支持飞书 docx/wiki 文档 URL")

        parts = [part for part in parsed.path.split("/") if part]
        if not parts:
            raise URLError("当前只支持飞书 docx/wiki 文档 URL")

        if parts[0] in {"docs", "sheets", "base"}:
            raise URLError("当前只支持 docx 文档 URL，暂不支持 docs/sheets/base 链接")

        if parts[0] == "wiki":
            if len(parts) < 2 or not parts[1]:
                raise URLError("wiki URL 缺少节点 token")
            return ("wiki", parts[1])

        if parts[0] == "docx":
            if len(parts) < 2 or not parts[1]:
                raise URLError("docx URL 缺少文档 ID")
            return ("docx", parts[1])

        raise URLError("当前只支持飞书 docx/wiki 文档 URL")

    def resolve_document_id(self, url_type: str, token: str) -> str:
        """将 parse_url 的结果解析为 document_id。wiki 类型需要额外 API 调用。"""
        if url_type == "docx":
            return token
        if url_type == "wiki":
            return self._resolve_wiki_node(token)
        raise URLError(f"不支持的 URL 类型：{url_type}")

    def _resolve_wiki_node(self, node_token: str) -> str:
        """通过 wiki API 获取节点对应的 docx document_id。"""
        params = urllib.parse.urlencode({"token": node_token})
        data = self.client.request("GET", f"/wiki/v2/spaces/get_node?{params}")
        node = data.get("node", {})
        obj_type = str(node.get("obj_type", ""))
        obj_token = str(node.get("obj_token", ""))

        if obj_type != "docx":
            raise URLError(f"此知识库节点是 {obj_type} 类型，当前只支持 docx 文档")
        if not obj_token:
            raise URLError("无法获取知识库节点对应的文档 ID")
        return obj_token

    def fetch_blocks(self, document_id: str) -> list[dict]:
        """分页获取所有 blocks（含子 blocks 递归）。"""
        items: list[dict] = []
        page_token = ""

        while True:
            params = {
                "page_size": 500,
                "document_revision_id": -1,
            }
            if page_token:
                params["page_token"] = page_token

            path = (
                f"/docx/v1/documents/{urllib.parse.quote(document_id, safe='')}/blocks?"
                f"{urllib.parse.urlencode(params)}"
            )
            data = self.client.request("GET", path)
            items.extend(data.get("items", []))

            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token", ""))
            if not page_token:
                break

        return items


# ---------------------------------------------------------------------------
# MarkdownRenderer — block 树 → Markdown
# ---------------------------------------------------------------------------

class MarkdownRenderer:
    """将 block 列表渲染为 Markdown 字符串。"""

    def render(self, blocks: list[dict]) -> str:
        """block 树 → Markdown 字符串。"""
        self._blocks_by_id = {
            str(block.get("block_id")): block
            for block in blocks
            if block.get("block_id") is not None
        }
        if not blocks:
            return ""

        root = next((block for block in blocks if block.get("block_type") == 1), None)
        if root is not None:
            rendered = "".join(
                self._render_block(child)
                for child in self._get_child_blocks(root)
            )
            return rendered.strip()

        top_level_blocks = [
            block
            for block in blocks
            if not block.get("parent_id") or str(block.get("parent_id")) not in self._blocks_by_id
        ]
        rendered = "".join(self._render_block(block) for block in top_level_blocks)
        return rendered.strip()

    def _render_block(self, block: dict, depth: int = 0) -> str:
        """单 block 渲染，按 block_type 分派。"""
        block_type = int(block.get("block_type", 0))

        if block_type == 1:
            return self._render_children(block, depth)

        if block_type == 2:
            text = self._extract_block_text(block)
            if not text:
                return "\n"
            return f"{text}\n\n"

        if 3 <= block_type <= 11:
            text = self._extract_block_text(block)
            if not text:
                return "\n"
            return f"{'#' * (block_type - 2)} {text}\n\n"

        if block_type == 12:
            text = self._extract_block_text(block)
            line = f"{'  ' * depth}- {text}".rstrip() + "\n"
            return line + self._render_children(block, depth + 1)

        if block_type == 13:
            text = self._extract_block_text(block)
            line = f"{'  ' * depth}1. {text}".rstrip() + "\n"
            return line + self._render_children(block, depth + 1)

        if block_type == 14:
            code_data = block.get("code") or {}
            style = code_data.get("style") or {}
            language = self._get_code_language(style.get("language"))
            text = self._extract_text(code_data.get("elements", []))
            fence = f"```{language}" if language else "```"
            content = text.rstrip("\n")
            return f"{fence}\n{content}\n```\n\n"

        if block_type == 15:
            text = self._extract_block_text(block)
            return self._render_blockquote(text, "> ")

        if block_type == 19:
            text = self._extract_block_text(block)
            return self._render_blockquote(text, "> 💡 ")

        if block_type == 22:
            return "---\n\n"

        if block_type == 27:
            token = str((block.get("image") or {}).get("token", ""))
            return f"![Image](token:{token})\n\n"

        if block_type == 31:
            return self._render_table(block)

        if block_type == 32:
            return self._render_table_cell(block)

        return f"<!-- unsupported block_type: {block_type} -->\n\n"

    def _extract_text(self, elements: list[dict]) -> str:
        parts: list[str] = []

        for element in elements or []:
            if "text_run" in element:
                text_run = element.get("text_run") or {}
                text = str(text_run.get("content", ""))
                style = text_run.get("text_element_style") or {}
            elif "mention_user" in element:
                text = str((element.get("mention_user") or {}).get("name", ""))
                style = {}
            elif "mention_doc" in element:
                mention_doc = element.get("mention_doc") or {}
                text = str(mention_doc.get("title", ""))
                link = mention_doc.get("url")
                style = {"link": {"url": link}} if link else {}
            elif "equation" in element:
                text = str((element.get("equation") or {}).get("content", ""))
                style = {}
            elif "text_line_break" in element:
                parts.append("\n")
                continue
            else:
                continue

            if not text:
                continue

            if style.get("inline_code"):
                text = f"`{text}`"
            if style.get("bold"):
                text = f"**{text}**"
            if style.get("italic"):
                text = f"*{text}*"
            if style.get("strikethrough"):
                text = f"~~{text}~~"
            if style.get("underline"):
                text = f"<u>{text}</u>"

            link = (style.get("link") or {}).get("url")
            if link:
                text = f"[{text}]({link})"

            parts.append(text)

        return "".join(parts)

    def _get_code_language(self, lang_int: int | str | None) -> str:
        try:
            return CODE_LANGUAGE_MAP.get(int(lang_int), "")
        except (TypeError, ValueError):
            return ""

    def _extract_block_text(self, block: dict) -> str:
        key = BLOCK_TYPE_TO_KEY.get(int(block.get("block_type", 0)), "")
        data = block.get(key) or {}
        return self._extract_text(data.get("elements", []))

    def _get_child_blocks(self, block: dict) -> list[dict]:
        children: list[dict] = []
        for child_id in block.get("children", []):
            child = self._blocks_by_id.get(str(child_id))
            if child is not None:
                children.append(child)
        return children

    def _render_children(self, block: dict, depth: int = 0) -> str:
        return "".join(self._render_block(child, depth) for child in self._get_child_blocks(block))

    def _render_blockquote(self, text: str, prefix: str) -> str:
        if not text:
            return f"{prefix.strip()}\n\n"
        lines = [line for line in text.splitlines() if line] or [text]
        return "\n".join(f"{prefix}{line}" for line in lines) + "\n\n"

    def _render_table(self, block: dict) -> str:
        table_data = block.get("table") or {}
        property_data = table_data.get("property") or {}
        try:
            column_size = int(property_data.get("column_size", 0))
        except (TypeError, ValueError):
            column_size = 0

        rows: list[list[str]] = []
        for row_block in self._get_child_blocks(block):
            row: list[str] = []
            for cell_id in row_block.get("children", []):
                cell_block = self._blocks_by_id.get(str(cell_id))
                if cell_block is None:
                    continue
                row.append(self._render_table_cell(cell_block))
            rows.append(row)

        if not rows:
            return "\n"

        if column_size <= 0:
            column_size = max((len(row) for row in rows), default=0)
        if column_size <= 0:
            return "\n"

        normalized_rows: list[list[str]] = []
        for row in rows:
            padded = row[:column_size] + [""] * max(0, column_size - len(row))
            normalized_rows.append(padded)

        header = normalized_rows[0]
        body = normalized_rows[1:]

        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * column_size) + " |",
        ]
        for row in body:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines) + "\n\n"

    def _render_table_cell(self, block: dict) -> str:
        parts: list[str] = []
        cell_text = self._extract_block_text(block)
        if cell_text:
            parts.append(cell_text)

        for child in self._get_child_blocks(block):
            rendered = self._render_block(child).strip()
            if rendered:
                flattened = "<br>".join(
                    line.strip() for line in rendered.splitlines() if line.strip()
                )
                if flattened:
                    parts.append(flattened)

        text = "<br>".join(part for part in parts if part)
        return text.replace("|", "\\|")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_markdown(url_type: str, token: str, auth: FeishuAuth) -> str:
    """读取飞书文档并渲染为 Markdown。"""
    client = FeishuClient(auth)
    fetcher = DocumentFetcher(client)
    renderer = MarkdownRenderer()

    document_id = fetcher.resolve_document_id(url_type, token)
    blocks = fetcher.fetch_blocks(document_id)
    return renderer.render(blocks)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="飞书文档 → Markdown（doc-to-sketch 内部工具）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # auth 子命令
    subparsers.add_parser("auth", help="首次飞书授权（浏览器）")

    # fetch 子命令
    fetch_parser = subparsers.add_parser("fetch", help="读取飞书文档")
    fetch_parser.add_argument("url", help="飞书文档 URL")

    args = parser.parse_args()

    try:
        if args.command == "auth":
            auth = FeishuAuth()
            auth.login()
            print("授权成功！现在可以使用 fetch 命令读取飞书文档。")

        elif args.command == "fetch":
            url_type, token = DocumentFetcher.parse_url(args.url)
            auth = FeishuAuth()
            try:
                markdown = fetch_markdown(url_type, token, auth)
            except AuthError as exc:
                print(f"{exc}", file=sys.stderr)
                print("正在打开浏览器完成飞书授权，授权成功后将自动继续读取文档。", file=sys.stderr)
                auth.login()
                markdown = fetch_markdown(url_type, token, auth)
            print(markdown)

    except FeishuError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
