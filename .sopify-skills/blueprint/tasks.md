# Tasks — 全局任务追踪

## Phase 0: 目录重组

- [x] P0-1: 将 `ian-handdrawn-ppt/references/` 移到根级 `references/`
- [x] P0-2: 将 `ian-handdrawn-ppt/assets/` 移到根级 `assets/`
- [x] P0-3: 将 `ian-handdrawn-ppt/SKILL.md` 移到根级 `SKILL.md`
- [x] P0-4: 删除空的 `ian-handdrawn-ppt/` 目录
- [x] P0-5: 更新 .gitignore（.env, __pycache__ 等）
- [x] P0-6: 创建 .env.example（FEISHU_APP_ID, FEISHU_APP_SECRET）

## Phase 1: SKILL.md 改造

- [x] P1-1: 重写 SKILL.md 头部（name: doc-to-sketch，去掉 Ian 绑定）
- [x] P1-2: 在 workflow Step 1 中增加飞书 URL 的 ingest 分支
- [x] P1-3: 更新 Resource Map 路径（从子目录改为根级）
- [x] P1-4: 扩展 intake.md 增加飞书文档 URL 作为合法输入类型

## Phase 2: Skill 内部飞书文档获取能力

- [x] P2-1: 实现 scripts/feishu_fetch.py — 鉴权 + 文档获取 + Block 解析 → Markdown
- [x] P2-2: 支持分页获取 Blocks
- [x] P2-3: Block → Markdown 映射（heading/text/list/code/image/table/callout/divider）
- [x] P2-4: 错误处理（无权限/文档不存在/token 过期）
- [x] P2-5: 基础测试

## Phase 3: 分发与文档

- [ ] P3-1: 创建 package.json（可选，用于 npx skills add 分发）
- [x] P3-2: README.md 全重写（安装、使用、飞书集成说明）
- [x] P3-3: examples/ 更新（飞书文档示例 prompt）
- [x] P3-4: NOTICE.md 最终检查
