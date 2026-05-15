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

## Phase 4: 可选图像生成 fallback

- [x] P4-1: 将 gen-image.sh 清理为 scripts/generate_image.sh
  - 去除硬编码 key 和 provider URL
  - 通用环境变量: IMAGE_API_KEY, IMAGE_API_URL, IMAGE_MODEL
  - 支持 --prompt-file（主）和 --prompt（辅）
  - 默认 --size 保留 2520x1080
- [x] P4-2: .env.example 补图像 provider 配置说明（通用，不绑定特定 provider）
- [x] P4-3: README 加「可选本地图像 fallback」小节
  - 默认路径 = 宿主原生出图
  - 需用户自配 provider + key
  - 会将 prompt 发到用户配置的第三方服务
- [x] P4-4: SKILL.md 加条件性说明（仅当宿主无出图能力 + 用户已配置 fallback 时使用）

### 验收标准

- 默认情况下，doc-to-sketch 仍优先使用宿主原生生图能力
- 只有在宿主无生图能力且用户已配置 fallback 时，才允许调用本地脚本
- Non-goal: 不用 fallback 替代现有主链路；fallback 仅用于补齐宿主能力缺口
