# Design — 飞书集成 + Skill 重组

## 实现原则

1. **官方 API + 自有规格**：代码、CLI 参数、错误文案、目录组织，均基于[飞书开放平台官方文档](https://open.feishu.cn/document/)和本项目自身产品目标独立设计。仅参考外部实践的能力边界与坑点清单，不做同构重写。
2. **Prompt ingestion 优先**：输出目标是给出图 workflow 喂结构化内容，不是文档保真备份。图片转占位、表格保留 Markdown 结构、不支持的 block 走可预期降级。
3. **文档卫生**：对外文档（README、NOTICE、代码注释、commit message）中不写"参考某实现"。内部只保留官方 API 链接和自有设计结论。

## 认证体验

**首版定义**：默认使用 doc-to-sketch 共享飞书应用凭证，首次 fetch 自动打开浏览器授权，授权后继续读取文档。

| 步骤 | 用户动作 | 频率 |
|------|---------|------|
| 1. 使用 Skill | 给飞书文档 URL + 出图指令；首次无有效 token 时自动弹出浏览器授权 | 每次 |
| 2. 手动预授权（可选） | 运行 `python3 scripts/feishu_fetch.py auth`，提前完成浏览器授权 | 按需 |
| 3. 自建应用覆盖（可选） | 企业或敏感场景设置 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`，并配置 `http://localhost:19823/callback` 后重新授权 | 按需 |

**鉴权方式**：OAuth 2.0 authorization code flow（RFC 6749），获取 `user_access_token`。
- 以用户身份读取文档，无需把文档分享给应用
- token 本地存储（`~/.doc-to-sketch/token.json`），过期自动刷新
- 刷新失败、scope 变更或 app_id 变更时由 fetch 自动触发浏览器重新授权
- 默认共享应用只用于零配置授权；共享应用身份可被公开复用，因此权限应保持最小化
- 自建应用凭证通过环境变量覆盖，不提交到仓库

**零配置边界**：普通用户只需首次浏览器授权；企业或敏感场景建议自建飞书应用并用环境变量覆盖默认凭证。

## URL 支持矩阵

**首版支持：**

| URL 形态 | 示例 | 支持状态 |
|----------|------|---------|
| 标准文档 URL | `https://xxx.feishu.cn/docx/AbCdEfGhIj` | ✅ 首版支持 |
| 带查询参数 | `https://xxx.feishu.cn/docx/AbCdEfGhIj?from=xxx` | ✅ 首版支持（忽略参数） |
| Lark 域名 | `https://xxx.lark.suite.com/docx/AbCdEfGhIj` | ✅ 首版支持 |
| 知识库节点 URL | `https://xxx.feishu.cn/wiki/AbCdEfGhIj` | ✅ 首版支持（通过 wiki API 解析 → docx document_id） |

**首版不支持（明确报错）：**

| URL 形态 | 示例 | 说明 |
|----------|------|------|
| 旧版文档 (doc) | `https://xxx.feishu.cn/docs/AbCdEfGhIj` | 旧版 API，不在 Block API 范围 |
| 电子表格 / 多维表格 | `https://xxx.feishu.cn/sheets/...` / `.../base/...` | 非文档类型 |
| 任意其他 URL | - | 统一提示"当前只支持 docx 文档 URL" |

## 输出契约

**输出目标**：为 doc-to-sketch 出图 workflow 提供稳定的结构化 Markdown 输入。

**输出不是**：文档的完整保真备份。

| 内容类型 | 输出策略 |
|---------|---------|
| 标题 (H1-H9) | 完整保留层级和文本 |
| 正文段落 | 完整保留 |
| 有序/无序列表 | 保留结构和文本 |
| 代码块 | 保留语言标签和代码内容 |
| Callout / 提示框 | 转为 blockquote |
| 分割线 | `---` |
| 表格 | 保留 Markdown 表格结构 |
| 图片 | 输出 `![Image](token:xxx)` 占位，不下载二进制 |
| 不支持的 block | `<!-- unsupported block_type: N -->` 注释降级 |

**稳定性要求**：输出 Markdown 可直接喂给 SKILL.md workflow Step 1 的 ingest 分支，不需要人工二次编辑。

## 目录重组

**当前 → 目标：**

```
当前:                          目标:
.                              .
├── ian-handdrawn-ppt/         ├── SKILL.md           ← 提升到根级
│   ├── SKILL.md               ├── references/        ← 提升到根级
│   ├── references/            │   ├── intake.md      (扩展飞书输入)
│   │   └── *.md               │   └── *.md
│   └── assets/                ├── assets/            ← 提升到根级
│       ├── theme-tokens.json  │   ├── theme-tokens.json
│       └── reference-*.png    │   └── reference-*.png
├── examples/                  ├── scripts/           ← 新增
│   ├── images/                │   └── feishu_fetch.py
│   └── prompts.md             ├── examples/
│                              ├── package.json       ← 可选分发
│                              ├── .env.example       ← 新增
│                              ├── README.md
│                              ├── LICENSE
│                              └── NOTICE.md
```

## feishu_fetch.py 设计

### Scope / Non-Goals

**支持范围（最小通用子集）**：
- OAuth user_access_token 鉴权（用户级，首次浏览器授权 + 本地 token 存储）
- docx 文档 URL → document_id 提取
- Block API 分页获取 + block tree 递归
- 核心 8 类 Block → Markdown 渲染
- 5 类基础错误处理
- token 自动刷新（refresh_token）
- token 过期缓冲期（提前 5 分钟触发刷新，避免请求中途 token 失效）
- scope 变更检测（代码更新权限需求后，加载旧 token 时自动比对 scope 并提示重新授权）

**明确不做（Non-Goals）**：
- Bitable / 评论 / 电子表格 / 画板
- 图片二进制下载落地
- SSL 关闭 / retry 重试

### 架构

**单文件 Python 脚本**（~600-900 行），无外部依赖（仅 urllib + json + http.server）。

```
feishu_fetch.py
├── FeishuAuth            # OAuth 授权
│   ├── __init__()        # 内置凭证 + env 可选覆盖
│   ├── login()           # 启动 localhost 回调 + 打开浏览器授权
│   ├── _exchange_code()  # code → user_access_token + refresh_token
│   ├── _refresh_token()  # refresh_token → 新 user_access_token
│   ├── _load_token()     # 从本地文件加载 token（含 scope 变更检测）
│   └── _save_token()     # 写入 ~/.doc-to-sketch/token.json（含 scope 快照）
├── FeishuClient          # HTTP 客户端
│   ├── __init__()        # 接收 auth 实例
│   └── request()         # 统一 HTTP 请求（带 Authorization header）
├── DocumentFetcher       # 文档抓取
│   ├── parse_url()       # URL → (url_type, token)
│   ├── resolve_document_id() # url_type + token → document_id (wiki 需额外 API)
│   ├── _resolve_wiki_node()  # wiki node_token → docx document_id
│   └── fetch_blocks()    # 分页获取所有 blocks
├── MarkdownRenderer      # Markdown 渲染
│   ├── render()          # block tree → Markdown 字符串
│   └── _render_block()   # 单 block 渲染（按 block_type 分派）
└── main()                # argparse 入口（auth / fetch 子命令）
```

### Block 类型支持

| Block Type | 常量值 | Markdown 输出 | 优先级 |
|-----------|--------|--------------|--------|
| PAGE | 1 | (容器，递归子 block) | P0 |
| TEXT | 2 | 段落文本 | P0 |
| H1-H9 | 3-11 | `# ` ~ `######### ` | P0 |
| BULLET | 12 | `- ` | P0 |
| ORDERED | 13 | `1. ` | P0 |
| CODE | 14 | ` ```lang ``` ` | P0 |
| CALLOUT | 19 | `> 💡 ` | P0 |
| DIVIDER | 22 | `---` | P0 |
| TABLE | 31 | Markdown 表格（递归 row/cell） | P0 |
| TABLE_CELL | - | (容器，递归子 block) | P0 |
| IMAGE | 27 | `![Image](token:xxx)` 占位 | P1 |
| 其他 | - | `<!-- unsupported block_type: N -->` | 降级 |

### 错误模型

```
错误类型          → 用户可见信息
─────────────────────────────────────────────
未授权            → fetch 自动打开浏览器授权，授权后继续读取文档
401 token 失效   → "Token 已过期，正在自动刷新..."（刷新失败 → "请重新运行 auth 授权"）
                   注意：token 有过期缓冲期（提前 5 分钟刷新），正常流程下不应出现 401
403 无权限        → "当前用户无权访问此文档"
404 文档不存在    → "文档 ID 无效或已被删除"
不支持的 URL 类型 → "当前只支持 docx 文档 URL"（wiki 已支持，docs/sheets/base 报错）
scope 不匹配     → "代码权限需求已更新，请重新运行 auth 授权"
app_id 不匹配    → "飞书应用配置已变更，请重新完成飞书授权"
token 文件损坏   → "本地 token 文件已损坏，请重新运行 auth 授权"
```

## SKILL.md 修改点

1. YAML frontmatter: `name: doc-to-sketch`
2. description: 增加飞书文档源描述
3. Resource Map: 路径从 `ian-handdrawn-ppt/references/` 改为 `references/`
4. Workflow Step 1 (Ingest): 增加飞书 URL 分支
5. 去掉 Ian 品牌绑定的措辞

## 执行顺序

```
Phase 0: 目录重组 (git mv + cleanup)
    ↓
Phase 1: SKILL.md 改造 (扩展 workflow)
    ↓
Phase 2: feishu_fetch.py (核心交付)
    ↓
Phase 3: 分发与文档 (README + package.json)
```
