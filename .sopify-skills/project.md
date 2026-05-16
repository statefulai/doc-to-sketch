# Project Conventions

## 定位

- AI Skill（prompt 工程）+ 轻量辅助脚本
- 不是 TS/Node 项目，不是框架

## 技术栈

- Skill 格式: YAML frontmatter + Markdown（Codex / Claude Code 兼容）
- 辅助脚本: Python 3（零外部依赖，仅标准库）
- 分发: `npx skills add statefulai/doc-to-sketch`（主路径）；git clone 备选
- `package.json` 负责 npm 元数据与 pack 白名单；GitHub 源安装仍以 git-tracked 文件为准

## 目录约定

- `SKILL.md` — Skill 入口
- `references/` — prompt 资产（叙事规划、版式、视觉 DNA 等）
- `assets/` — 主题色值、风格锚定图
- `scripts/` — 辅助脚本（`feishu_fetch.py`、`generate_image.sh`、`doctor.sh`）
- `examples/` — 示例 prompt 和效果图
- `.sopify-skills/` — 源码仓内部知识库，不是 skill 运行时依赖

## Git 约定

- commit message: conventional commits (feat/fix/refactor/docs)
- 分支: main + feature branches

## 敏感信息

- 默认内置 doc-to-sketch 共享飞书应用凭证，提供零配置 OAuth 授权体验
- 企业或敏感场景可用 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 环境变量覆盖默认凭证
- 用户 token 仅保存在本机 `~/.doc-to-sketch/token.json`，不入库
- 自建应用凭证、`.env`、token 文件不得提交；`.env.example` 只提供模板
