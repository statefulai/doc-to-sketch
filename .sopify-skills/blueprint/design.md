# Design

## 架构概览

```text
doc-to-sketch (Skill)
├── SKILL.md                    ← 核心工作流与 Path A/B/C 输出契约
├── references/                 ← prompt 资产（intake / narrative / archetypes / visual DNA / quality）
├── assets/
│   ├── theme-tokens.json
│   └── style-anchor-cover-21x9.png
├── scripts/
│   ├── feishu_fetch.py         ← 飞书文档 URL -> Markdown
│   ├── generate_image.sh       ← Path B 外部 API fallback
│   └── doctor.sh               ← 配置自检 + 保守建议
├── tests/
│   └── test_feishu_fetch.py
├── examples/
│   ├── images/
│   └── prompts.md
├── .env.example
├── package.json                ← npm 元数据与 pack 白名单
├── README.md
├── LICENSE
└── NOTICE.md
```

## 核心流程

1. **Ingest**
   - 本地文件 / 纯文本直接读取
   - 飞书 docx/wiki URL 调用 `scripts/feishu_fetch.py fetch "<url>"`
2. **Planning**
   - intake -> narrative -> archetype -> visual DNA
3. **Output routing**
   - **Path A**: 宿主具备原生图像生成，直接输出 PNG 页面图
   - **Path B**: 宿主无原生图像生成，但用户配置了 `IMAGE_API_KEY` + `IMAGE_API_URL`；经用户确认后调用 `scripts/generate_image.sh`
   - **Path C**: 无生图能力时输出 blueprint + ready-to-use prompts

## 飞书获取脚本设计

### `scripts/feishu_fetch.py`

- 基于飞书 OpenAPI 的轻量执行器
- 使用 OAuth 2.0 `user_access_token`
- 默认共享应用凭证，可用 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 覆盖
- 首次授权自动打开浏览器；token 存在本机 `~/.doc-to-sketch/token.json`
- 作用是把飞书文档转换为稳定 Markdown，供 skill 主流程继续消费

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

### `scripts/generate_image.sh`

- 仅用于 Path B
- 使用 `IMAGE_API_KEY`、`IMAGE_API_URL`、`IMAGE_MODEL`
- prompt 会发送到用户配置的第三方服务
- 不是默认主链路，也不替代原生生图

### `scripts/doctor.sh`

- 自检配置状态，不修改环境
- 能确认的只检查配置与依赖
- 无法可靠判断宿主原生生图能力时，只给保守建议路径

## 分发与目录约定

- 主安装命令：`npx skills add statefulai/doc-to-sketch`
- 备选安装：`git clone` + 手动 symlink
- `package.json` 的 `files` 仅对 npm pack/publish 生效
- GitHub 源安装仍以 git-tracked 文件为准，因此 `.sopify-skills/` 等内部资产不会被 `package.json` 隔离
- `.sopify-skills/` 是源码仓内部知识库，不是 skill 运行时依赖

## 技术选型

| 维度 | 选择 | 原因 |
|------|------|------|
| Skill 入口 | YAML frontmatter + Markdown | Codex / Claude Code / 通用 skills 兼容 |
| 飞书脚本语言 | Python 3 标准库 | 零外部依赖，跨宿主可用 |
| fallback API | shell + curl + python3 | 保持轻量，避免引入额外运行时 |
| 分发元数据 | `package.json` | 元数据、npm pack 白名单、后续发布预留 |
