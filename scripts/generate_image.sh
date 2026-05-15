#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# generate_image.sh — 可选本地图像生成 fallback
#
# 当宿主没有原生图片生成功能时，用户可以手动调用此脚本，
# 将已生成的 prompt 发送到用户配置的外部图片生成服务，得到 PNG。
#
# 这不是 doc-to-sketch 的默认工作流。
# 默认路径是宿主原生图片生成（如 Codex 内置 image model）。
#
# 环境变量（必须）:
#   IMAGE_API_KEY     用户自己的 API 密钥（含鉴权前缀，如 Bearer sk-xxx 或 sk-xxx）
#   IMAGE_API_URL     图片生成 API 端点
#
# 环境变量（可选）:
#   IMAGE_MODEL       模型名称（默认: gpt-image-2）
#
# 用法:
#   scripts/generate_image.sh --prompt-file prompt.txt --output out.png
#   scripts/generate_image.sh --prompt "内容" --size 1920x1080
# ---------------------------------------------------------------------------

# 默认值
SIZE="2520x1080"
OUTPUT_DIR="."
PROMPT=""
PROMPT_FILE=""
MODEL="${IMAGE_MODEL:-gpt-image-2}"

usage() {
  cat <<EOF
用法: $(basename "$0") [选项]

选项:
  --prompt-file, -f  从文件读取 prompt（推荐，避免 shell 转义问题）
  --prompt, -p       直接传入 prompt 文本
  --size, -s         图片尺寸（默认: 2520x1080）
  --output-dir, -o   保存目录（默认: 当前目录）
  --help, -h         显示帮助

环境变量:
  IMAGE_API_KEY      API 密钥（必须，含鉴权前缀，如 "Bearer sk-xxx" 或 "sk-xxx"）
  IMAGE_API_URL      API 端点（必须）
  IMAGE_MODEL        模型名称（默认: gpt-image-2）

示例:
  # 从文件读 prompt
  scripts/generate_image.sh -f prompt.txt -s 1920x1080 -o output/

  # 直接传 prompt（短文本适用）
  scripts/generate_image.sh -p "一个简单的技术架构图" -o output/
EOF
  exit 1
}

# ---- 解析参数 ----
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt-file|-f) PROMPT_FILE="$2"; shift 2 ;;
    --prompt|-p)      PROMPT="$2"; shift 2 ;;
    --size|-s)        SIZE="$2"; shift 2 ;;
    --output-dir|-o)  OUTPUT_DIR="$2"; shift 2 ;;
    --help|-h)        usage ;;
    *) echo "未知参数: $1"; usage ;;
  esac
done

# ---- 读取 prompt ----
# --prompt-file 优先于 --prompt
if [[ -n "$PROMPT_FILE" ]]; then
  if [[ ! -f "$PROMPT_FILE" ]]; then
    echo "错误: prompt 文件不存在: $PROMPT_FILE"
    exit 1
  fi
  PROMPT=$(cat "$PROMPT_FILE")
fi

if [[ -z "$PROMPT" ]]; then
  echo "错误: 必须通过 --prompt-file 或 --prompt 提供 prompt"
  usage
fi

# ---- 校验环境变量 ----
if [[ -z "${IMAGE_API_KEY:-}" ]]; then
  echo "错误: 请设置环境变量 IMAGE_API_KEY（你的图片服务 API 密钥）"
  echo "      export IMAGE_API_KEY=your_api_key"
  exit 1
fi

if [[ -z "${IMAGE_API_URL:-}" ]]; then
  echo "错误: 请设置环境变量 IMAGE_API_URL（图片生成 API 端点）"
  echo "      export IMAGE_API_URL=https://api.example.com/v1/images/generations"
  exit 1
fi

# ---- 检查依赖 ----
for cmd in curl python3; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "错误: 需要安装 $cmd"
    exit 1
  fi
done

# ---- 准备输出 ----
mkdir -p "$OUTPUT_DIR"

# 文件名：prompt 前 20 字符 + 时间戳
SAFE_PROMPT=$(echo "$PROMPT" | tr -cs '[:alnum:]' '_' | head -c 20 | sed 's/_$//')
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="${SAFE_PROMPT}_${TIMESTAMP}.png"
FILEPATH="${OUTPUT_DIR}/${FILENAME}"

echo "⏳ 正在生成图片..."
echo "   Size:   ${SIZE}"
echo "   Model:  ${MODEL}"
echo "   输出:   ${FILEPATH}"

# ---- 调用 API ----
TMPFILE=$(mktemp "${TMPDIR:-/tmp}/gen_image_resp.XXXXXX")
trap 'rm -f "$TMPFILE"' EXIT

# 用 python3 构造 JSON，避免 shell 转义问题
JSON_PAYLOAD=$(python3 -c "
import json, sys
print(json.dumps({
    'size': sys.argv[1],
    'prompt': sys.argv[2],
    'model': sys.argv[3]
}))
" "$SIZE" "$PROMPT" "$MODEL")

curl --silent --location --request POST "$IMAGE_API_URL" \
  --header "Authorization: ${IMAGE_API_KEY}" \
  --header "Content-Type: application/json" \
  --header "Accept: */*" \
  --output "$TMPFILE" \
  --data-raw "$JSON_PAYLOAD"

# ---- 解析响应 ----
python3 -c "
import json, base64, sys

resp_path = sys.argv[1]
out_path  = sys.argv[2]

with open(resp_path, 'r') as f:
    raw = f.read()

if not raw.strip():
    print('❌ API 返回空响应')
    sys.exit(1)

try:
    r = json.loads(raw)
except json.JSONDecodeError as e:
    print(f'❌ API 响应不是有效 JSON: {e}')
    print(f'   预览: {raw[:300]}')
    sys.exit(1)

if 'error' in r:
    msg = r['error'].get('message', r['error']) if isinstance(r['error'], dict) else r['error']
    print(f'❌ API 返回错误: {msg}')
    sys.exit(1)

data = r.get('data', [])
if not data:
    print('❌ 响应中没有 data 字段')
    print(f'   键: {list(r.keys())}')
    sys.exit(1)

b64_str = data[0].get('b64_json') or data[0].get('b64') or ''
if not b64_str:
    print('❌ 未能提取 base64 数据')
    print(f'   data[0] 键: {list(data[0].keys())}')
    sys.exit(1)

# 去掉 data URI 前缀
if b64_str.startswith('data:'):
    b64_str = b64_str.split(',', 1)[1]

# 补齐 base64 padding
padding = 4 - len(b64_str) % 4
if padding != 4:
    b64_str += '=' * padding

img_bytes = base64.b64decode(b64_str)
with open(out_path, 'wb') as f:
    f.write(img_bytes)

size_mb = len(img_bytes) / (1024 * 1024)
print(f'✅ 图片已保存: {out_path} ({size_mb:.1f} MB)')
" "$TMPFILE" "$FILEPATH"

FILE_SIZE=$(du -h "$FILEPATH" 2>/dev/null | cut -f1)
echo "   文件大小: ${FILE_SIZE}"
