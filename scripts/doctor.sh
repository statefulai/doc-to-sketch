#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# doctor.sh — doc-to-sketch 配置自检 + 保守建议
#
# 自检当前环境配置状态，给出保守建议的使用路径。
# 不安装任何东西，不修改任何配置，纯检测 + 引导。
#
# 用法:
#   scripts/doctor.sh
# ---------------------------------------------------------------------------

echo "🩺 doc-to-sketch 配置自检"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Track capability level
LEVEL=0  # 0=only blueprint, 1=fallback API, 2=native image gen

# ---- 1. 检测宿主图像生成能力 ----
echo "1️⃣  图像生成能力"
echo ""

# Runtime capability detection is unreliable from a shell script.
# We can only check for strong signals (environment variables set by the host runtime itself).
# Directory existence (~/.codex, ~/.claude) does NOT mean "current session has image gen".
NATIVE_IMAGE=false

if [[ -n "${OPENAI_IMAGE_GENERATION:-}" ]] || [[ -n "${ANTHROPIC_IMAGE_GENERATION:-}" ]]; then
    # These are hypothetical runtime flags; no known agent sets them today.
    echo "   ✅ 检测到宿主运行时声明了图像生成能力"
    NATIVE_IMAGE=true
    LEVEL=2
else
    echo "   ⚠️  无法从脚本层面可靠判断当前宿主是否有原生图像生成"
    echo ""
    echo "      已知具备原生生图的宿主："
    echo "        • Codex（在 Codex sandbox 内运行时）"
    echo "        • Claude Code（claude 命令行内运行时）"
    echo ""
    echo "      如果你确认当前宿主有生图能力 → 你处于 Path A"
    echo "      如果不确定 → 按 Path B/C 使用更安全"
fi
echo ""

# ---- 2. 检测 fallback API 配置 ----
echo "2️⃣  Fallback API 配置"
echo ""

if [[ -n "${IMAGE_API_KEY:-}" ]] && [[ -n "${IMAGE_API_URL:-}" ]]; then
    echo "   ✅ IMAGE_API_KEY 已配置"
    echo "   ✅ IMAGE_API_URL = ${IMAGE_API_URL}"
    echo "   📦 MODEL = ${IMAGE_MODEL:-gpt-image-2}（默认）"
    if [[ $LEVEL -lt 1 ]]; then LEVEL=1; fi
elif [[ -n "${IMAGE_API_KEY:-}" ]]; then
    echo "   ⚠️  IMAGE_API_KEY 已配置，但缺少 IMAGE_API_URL"
    echo "      请设置: export IMAGE_API_URL=https://api.example.com/v1/images/generations"
elif [[ -n "${IMAGE_API_URL:-}" ]]; then
    echo "   ⚠️  IMAGE_API_URL 已配置，但缺少 IMAGE_API_KEY"
    echo "      请设置: export IMAGE_API_KEY=your_api_key"
else
    echo "   ℹ️  未配置 fallback API（IMAGE_API_KEY / IMAGE_API_URL 均未设置）"
    echo "      如需配置，参考 .env.example"
fi
echo ""

# ---- 3. 检测飞书凭证 ----
echo "3️⃣  飞书文档读取"
echo ""

FEISHU_TOKEN="$HOME/.doc-to-sketch/token.json"
if [[ -f "$FEISHU_TOKEN" ]]; then
    echo "   ✅ 飞书授权 token 已存在（${FEISHU_TOKEN}）"
elif [[ -n "${FEISHU_APP_ID:-}" ]] && [[ -n "${FEISHU_APP_SECRET:-}" ]]; then
    echo "   ✅ 自建飞书应用凭证已配置（FEISHU_APP_ID）"
    echo "      首次使用时会打开浏览器完成 OAuth 授权"
else
    echo "   ℹ️  飞书未授权（首次使用飞书 URL 时会自动引导授权）"
fi
echo ""

# ---- 4. 检测脚本依赖 ----
echo "4️⃣  脚本依赖"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$SCRIPT_DIR/generate_image.sh" ]]; then
    echo "   ✅ generate_image.sh 存在"
else
    echo "   ⚠️  generate_image.sh 未找到（fallback 功能不可用）"
fi

if command -v python3 &>/dev/null; then
    echo "   ✅ python3 可用（$(python3 --version 2>&1 | cut -d' ' -f2)）"
else
    echo "   ⚠️  python3 未安装（飞书文档读取和 fallback 需要）"
fi

if command -v curl &>/dev/null; then
    echo "   ✅ curl 可用"
else
    echo "   ⚠️  curl 未安装（fallback API 调用需要）"
fi
echo ""

# ---- 5. 总结 ----
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

case $LEVEL in
    2)
        echo "🎨 保守建议路径: Path A（完整出图）"
        echo ""
        echo "   你可以直接说:"
        echo "   \"Use \$doc-to-sketch 把这篇文章做成 1 张封面图 + 3 张正文配图。\""
        echo ""
        echo "   skill 会使用宿主原生图像生成，一步到位输出 PNG 页面图。"
        ;;
    1)
        echo "🔧 保守建议路径: Path B（API Fallback 出图）"
        echo ""
        echo "   你可以说:"
        echo "   \"Use \$doc-to-sketch 把这篇文章做成 1 张封面图 + 3 张正文配图。\""
        echo ""
        echo "   skill 会先规划，然后询问是否使用你配置的 API 生成图片。"
        echo "   （会消耗你的 API 额度，prompt 会发送到外部服务）"
        ;;
    0)
        echo "📋 保守建议路径: Path C（Blueprint + Prompt 输出）"
        echo ""
        echo "   本脚本无法可靠判断宿主是否有原生生图能力，以最安全路径建议。"
        echo "   如果你确认当前宿主支持原生生图（如 Codex / Claude Code），可直接按 Path A 使用。"
        echo ""
        echo "   按 Path C 使用时，你可以说:"
        echo "   \"Use \$doc-to-sketch 把这篇文章做成中文手绘技术图 deck。\""
        echo ""
        echo "   skill 会输出完整的页面规划 + 每页的 prompt 文件。"
        echo "   拿到 prompt 后，你可以:"
        echo "     1. 粘贴到 ChatGPT / Midjourney / DALL-E 生成图片"
        echo "     2. 配置 IMAGE_API_KEY + IMAGE_API_URL 升级到 Path B"
        echo "     3. 在 Codex / Claude Code 中使用，直接走 Path A"
        ;;
esac

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📖 详细配置说明: .env.example"
echo "🩺 重新检测: scripts/doctor.sh"
