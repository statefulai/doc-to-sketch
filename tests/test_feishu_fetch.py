#!/usr/bin/env python3
"""feishu_fetch.py 测试套件

覆盖 8 类错误场景 + URL 解析 + 缓冲期逻辑 + E2E 集成（需有效 token）。

用法：
    # 本地测试（无网络依赖，始终可跑）
    python3 tests/test_feishu_fetch.py

    # 有 token 时自动追加 E2E 集成测试
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import feishu_fetch as ff

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}: FAIL — {detail}")


def expect_error(error_cls, fn, *args, msg_contains: str = "", **kwargs):
    """Call fn and verify it raises error_cls with msg_contains."""
    try:
        fn(*args, **kwargs)
        return False, "no exception raised"
    except error_cls as exc:
        if msg_contains and msg_contains not in str(exc):
            return False, f"msg '{exc}' does not contain '{msg_contains}'"
        return True, str(exc)
    except Exception as exc:
        return False, f"wrong type: {type(exc).__name__}: {exc}"


def token_payload(**overrides):
    payload = {
        "app_id": ff.FeishuAuth().app_id,
        "access_token": "fake",
        "refresh_token": "fake",
        "obtained_at": time.time(),
        "expires_in": 7200,
        "required_scopes": ff.REQUIRED_SCOPES,
        "scope": ff.REQUIRED_SCOPES,
    }
    payload.update(overrides)
    return payload


# ── 1. URL 解析：拒绝不支持的 URL ──
print("\n── 1. 不支持的 URL 类型 ──")

bad_urls = [
    ("https://example.com/docx/abc", "非飞书域名"),
    ("https://xxx.feishu.cn/docs/abc", "旧版 doc"),
    ("https://xxx.feishu.cn/sheets/abc", "电子表格"),
    ("https://xxx.feishu.cn/base/abc", "多维表格"),
    ("https://xxx.feishu.cn/drive/abc", "drive"),
    ("not-a-url", "非 URL"),
]
for url, label in bad_urls:
    ok, msg = expect_error(ff.URLError, ff.DocumentFetcher.parse_url, url)
    check(f"URL 拒绝 ({label})", ok, msg)


# ── 2. URL 解析：合法 URL ──
print("\n── 2. 合法 URL 解析 ──")

valid_urls = [
    ("https://xxx.feishu.cn/docx/AbCdEf", ("docx", "AbCdEf")),
    ("https://xxx.feishu.cn/docx/AbCdEf?from=share", ("docx", "AbCdEf")),
    ("https://xxx.lark.suite.com/docx/AbCdEf", ("docx", "AbCdEf")),
    ("https://xxx.feishu.cn/wiki/NodeToken123", ("wiki", "NodeToken123")),
    ("https://xxx.larksuite.com/docx/AbCdEf", ("docx", "AbCdEf")),
]
for url, expected in valid_urls:
    try:
        result = ff.DocumentFetcher.parse_url(url)
        check(f"URL: {url}", result == expected,
              f"expected {expected}, got {result}")
    except Exception as exc:
        check(f"URL: {url}", False, str(exc))


# ── 3. 未授权（无 token 文件） ──
print("\n── 3. 未授权 ──")

orig_token_file = ff.TOKEN_FILE
try:
    ff.TOKEN_FILE = Path(tempfile.mktemp(suffix=".json"))
    auth = ff.FeishuAuth()
    ok, msg = expect_error(ff.AuthError, auth.get_token, msg_contains="浏览器授权")
    check("无 token → AuthError", ok, msg)
finally:
    ff.TOKEN_FILE = orig_token_file


# ── 4. Token 文件损坏 ──
print("\n── 4. Token 损坏 ──")

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    f.write("{invalid json!!!}")
    bad_file = f.name
try:
    ff.TOKEN_FILE = Path(bad_file)
    auth = ff.FeishuAuth()
    ok, msg = expect_error(ff.AuthError, auth.get_token, msg_contains="损坏")
    check("损坏 token → AuthError", ok, msg)
finally:
    ff.TOKEN_FILE = orig_token_file
    os.unlink(bad_file)


# ── 5. Scope 不匹配 ──
print("\n── 5. Scope 不匹配 ──")

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    json.dump(token_payload(required_scopes="old:scope:only", scope="old:scope:only"), f)
    scope_file = f.name
try:
    ff.TOKEN_FILE = Path(scope_file)
    auth = ff.FeishuAuth()
    ok, msg = expect_error(ff.AuthError, auth.get_token, msg_contains="权限需求已更新")
    check("scope 不匹配 → AuthError", ok, msg)
finally:
    ff.TOKEN_FILE = orig_token_file
    os.unlink(scope_file)


# ── 6. App ID 不匹配 ──
print("\n── 6. App ID 不匹配 ──")

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    json.dump(token_payload(app_id="different_app_id"), f)
    app_file = f.name
try:
    ff.TOKEN_FILE = Path(app_file)
    auth = ff.FeishuAuth()
    ok, msg = expect_error(ff.AuthError, auth.get_token, msg_contains="应用配置已变更")
    check("app_id 不匹配 → AuthError", ok, msg)
finally:
    ff.TOKEN_FILE = orig_token_file
    os.unlink(app_file)


# ── 7. Token 过期无 refresh_token ──
print("\n── 7. Token 过期 ──")

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    json.dump(token_payload(
        access_token="expired",
        refresh_token="",
        obtained_at=time.time() - 10000,
        expires_in=100,
    ), f)
    expired_file = f.name
try:
    ff.TOKEN_FILE = Path(expired_file)
    auth = ff.FeishuAuth()
    ok, msg = expect_error(ff.AuthError, auth.get_token, msg_contains="过期")
    check("过期 token 无 refresh → AuthError", ok, msg)
finally:
    ff.TOKEN_FILE = orig_token_file
    os.unlink(expired_file)


# ── 8. 缓冲期逻辑 ──
print("\n── 8. 缓冲期 (5 分钟) ──")

check(f"TOKEN_REFRESH_BUFFER = {ff.TOKEN_REFRESH_BUFFER}s ≥ 300",
      ff.TOKEN_REFRESH_BUFFER >= 300)

# 4 分钟剩余 < 5 分钟缓冲 → 应触发刷新
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    json.dump(token_payload(
        access_token="almost_expired",
        refresh_token="",
        obtained_at=time.time() - 6960,
    ), f)
    buf_file = f.name
try:
    ff.TOKEN_FILE = Path(buf_file)
    auth = ff.FeishuAuth()
    ok, msg = expect_error(ff.AuthError, auth.get_token, msg_contains="过期")
    check("缓冲期内触发刷新 (4min < 5min)", ok, msg)
finally:
    ff.TOKEN_FILE = orig_token_file
    os.unlink(buf_file)

# 10 分钟剩余 > 5 分钟缓冲 → 直接返回
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
    json.dump(token_payload(access_token="still_valid", obtained_at=time.time() - 6600), f)
    valid_file = f.name
try:
    ff.TOKEN_FILE = Path(valid_file)
    auth = ff.FeishuAuth()
    token = auth.get_token()
    check("缓冲期外不刷新 (10min > 5min)", token == "still_valid",
          f"got '{token}'")
finally:
    ff.TOKEN_FILE = orig_token_file
    os.unlink(valid_file)


# ── 9. 错误类层级 ──
print("\n── 9. 错误类层级 ──")

check("FeishuError < Exception", issubclass(ff.FeishuError, Exception))
check("ConfigError < FeishuError", issubclass(ff.ConfigError, ff.FeishuError))
check("URLError < FeishuError", issubclass(ff.URLError, ff.FeishuError))
check("AuthError < FeishuError", issubclass(ff.AuthError, ff.FeishuError))
check("APIError < FeishuError", issubclass(ff.APIError, ff.FeishuError))

# 死代码已删除
check("_fetch_children 已移除",
      not hasattr(ff.DocumentFetcher, '_fetch_children'))


# ── E2E 集成测试 ──
print("\n── E2E 集成测试 ──")

if orig_token_file.exists():
    auth = ff.FeishuAuth()
    try:
        auth.get_token()
    except ff.AuthError as exc:
        print(f"  ⚠️  token 需要重新授权，跳过 E2E: {exc}")
    else:
        print("  (有有效 token，执行 E2E)")
        try:
            url_type, token = ff.DocumentFetcher.parse_url(
                "https://geekbang.feishu.cn/wiki/SZiCw2LxUikbMLkRVAWcDyiinth"
            )
            client = ff.FeishuClient(auth)
            fetcher = ff.DocumentFetcher(client)
            renderer = ff.MarkdownRenderer()

            document_id = fetcher.resolve_document_id(url_type, token)
            blocks = fetcher.fetch_blocks(document_id)
            markdown = renderer.render(blocks)

            check("E2E: wiki → Markdown",
                  len(markdown) > 100 and "Skill" in markdown)
            check("E2E: 含标题", markdown.startswith("#") or "\n#" in markdown)
            check("E2E: 含中文",
                  any(kw in markdown for kw in ("背景", "MCP", "标准")))

            try:
                url_type, token = ff.DocumentFetcher.parse_url(
                    "https://nio.feishu.cn/wiki/LX4wwkmanisG1Vk4dQxcrzTinDh"
                )
                fetcher.resolve_document_id(url_type, token)
                check("E2E: 无权限 → 报错", False, "未抛异常")
            except ff.APIError as exc:
                check("E2E: 无权限 → APIError", True)
            except Exception as exc:
                check("E2E: 无权限 → APIError", False, f"{type(exc).__name__}: {exc}")
        except Exception as exc:
            check("E2E: wiki → Markdown", False, str(exc))
else:
    print("  ⚠️  无 token，跳过 E2E")


# ── 汇总 ──
print(f"\n{'='*50}")
print(f"结果: {PASS} 通过, {FAIL} 失败 (共 {PASS + FAIL})")
sys.exit(1 if FAIL else 0)
