# doc-to-sketch Blueprint

## 状态

| 维度 | 当前状态 |
|------|----------|
| 阶段 | P0-P5 已落地；当前无活动 plan，已完成方案已归档 |
| 定位 | AI Skill（prompt 工程）+ 轻量辅助脚本 |
| 输入能力 | Markdown、DOCX、PDF、PPTX、纯文本、飞书 docx/wiki URL |
| 输出能力 | Path A 原生生图；Path B API fallback；Path C blueprint + prompts |
| 分发现状 | 主安装命令为 `npx skills add statefulai/doc-to-sketch`；GitHub 源安装仍会包含 git-tracked 内部资产，`package.json` 仅约束 npm pack/publish |

## 维护方式

- 长期约定写入 `project.md`、`blueprint/background.md`、`blueprint/design.md`
- 未完成长期项与明确延后项写入 `blueprint/tasks.md`
- 已完成方案归档至本地（不入 git）
- `plan/` 只保留当前活动方案

## 当前目标

1. 保持多宿主安装与使用路径清晰可用
2. 继续保留飞书 URL -> Markdown -> 出图/规划链路
3. 保持中文手绘技术解释图的视觉与叙事优势

## 当前焦点

- 验证 Claude Code 端到端原生生图链路
- 明确 GitHub 源安装下内部资产随仓库分发的长期处理策略
- 保持 README、SKILL、辅助脚本三者口径一致

## 深入阅读

- [background.md](background.md) — 项目背景与长期上下文
- [design.md](design.md) — 当前技术设计与分发约束
- [tasks.md](tasks.md) — 未完成长期项与延后项
