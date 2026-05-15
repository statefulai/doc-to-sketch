# Design

## 架构概览

```
doc-to-sketch (Skill)
├── SKILL.md                    ← 核心 Skill 定义
├── references/                 ← prompt 资产
│   ├── intake.md               (扩展：增加飞书 URL 作为输入类型)
│   ├── narrative-planning.md
│   ├── slide-archetypes.md
│   ├── visual-dna-v6.md
│   ├── output-quality.md
│   └── prompt-patterns.md
├── assets/
│   ├── theme-tokens.json
│   └── style-anchor-cover-21x9.png
├── scripts/
│   └── feishu_fetch.py         ← 飞书文档 → Markdown 轻量脚本
├── examples/
├── package.json                ← 可选，仅用于 npx skills add 分发
├── README.md
├── LICENSE
└── NOTICE.md
```

**核心思路**：Skill workflow 中增加一个 ingest 分支 —— 如果输入是飞书 URL，先调用 `scripts/feishu_fetch.py` 获取 Markdown，然后走正常的 Skill 流水线。

**架构口径**：飞书内容获取基于官方 OpenAPI（docx / Block API）+ 自建 `feishu_fetch.py`，v1 不引入任何外部运行时依赖。

## 飞书获取脚本设计

### scripts/feishu_fetch.py

**功能**：给定飞书文档 URL → 输出 Markdown 文本

**鉴权**：OAuth 2.0 user_access_token 模式
- 内置飞书应用凭证（Skill 共享应用），零配置即可使用
- 可选覆盖：环境变量 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`
- 首次运行 `auth` 子命令 → 浏览器授权 → 本地存储 token
- 后续自动加载 token，过期自动刷新
- token 过期缓冲期：提前 5 分钟触发刷新，避免请求中途 token 失效
- scope 变更检测：代码更新权限需求后，加载旧 token 时自动比对 scope 并提示重新授权
- 以用户身份读取文档，无需将文档分享给应用

**API 调用链**：
```
首次授权：
1. GET /open-apis/authen/v1/authorize → 浏览器授权页
2. localhost 回调 → 获取 code
3. POST /open-apis/authen/v2/oauth/token → user_access_token + refresh_token

读取文档：
1. GET /open-apis/docx/v1/documents/{document_id} → 元信息
2. GET /open-apis/docx/v1/documents/{document_id}/blocks → Block 列表（分页）
3. Block 树递归 → Markdown 文本输出
```

**Block → Markdown 映射**：
| 飞书 Block 类型 | Markdown 输出 |
|----------------|---------------|
| heading1-9 | `#` - `#########` |
| text | 段落文本 |
| bullet / ordered | `- ` / `1. ` 列表 |
| code | ` ```lang ... ``` ` |
| image | `![Image](token:xxx)` 占位（不下载二进制） |
| table | Markdown 表格 |
| callout | `> ` 引用块 |
| divider | `---` |

**调用方式**（由 AI agent 在 Skill workflow 内部自动执行，用户不需要手动操作）：
```bash
# AI agent 内部调用（用户不可见）
python3 scripts/feishu_fetch.py fetch "https://xxx.feishu.cn/docx/xxxxx"
python3 scripts/feishu_fetch.py fetch "https://xxx.feishu.cn/wiki/xxxxx"
```

**授权行为**：
```bash
# fetch 首次读取且无有效 token 时会自动打开浏览器授权
python3 scripts/feishu_fetch.py fetch "https://xxx.feishu.cn/docx/xxxxx"

# 可选：提前浏览器授权
python3 scripts/feishu_fetch.py auth

# 高级：自定义飞书应用凭证（可选）
# export FEISHU_APP_ID=xxx
# export FEISHU_APP_SECRET=xxx
# 自建应用需配置回调地址: http://localhost:19823/callback
```

**依赖**：仅 Python 标准库（urllib + json + http.server + webbrowser），无外部依赖

## SKILL.md 扩展

在 workflow Step 1 (Ingest material) 中增加飞书分支：

```
1. Ingest material
   - If input is a Feishu/Lark document URL:
     1. Run `python3 scripts/feishu_fetch.py fetch "<url>"` to get Markdown
     2. Parse the Markdown output as the source material
   - If input is a local file: (existing logic)
   - If input is plain text/Markdown: (existing logic)
```

## 多宿主分发

| 宿主 | 安装方式 | Skill 入口 |
|------|----------|-----------|
| Codex CLI | `cp -R` 或 `ln -s` 到 `$CODEX_HOME/skills/` | SKILL.md |
| Claude Code | clone + symlink；`npx skills add` 待 package.json 完成后启用 | SKILL.md |
| 手动 | `git clone` + 按需使用 | SKILL.md |

所有宿主共用同一个 SKILL.md，因为 Skill 格式（YAML frontmatter + Markdown workflow）在 Codex 和 Claude Code 间兼容。

## 技术选型

| 维度 | 选择 | 原因 |
|------|------|------|
| 飞书脚本语言 | Python | 零依赖可行，所有宿主环境都有 Python |
| HTTP | urllib (标准库) | 无外部依赖，仅用标准库 |
| 分发 | npm package.json (可选) | 仅用于 `npx skills add` 路径 |
