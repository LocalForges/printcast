#!/usr/bin/env bash
# 构建展示端：web-src/（分片源码 + 分层样式）→ web/app/app.js + app.css。
# 产物已入库，clone 后无需执行本脚本即可运行；只在改了展示端源码后重跑。
# Vite 复用本机已安装的副本（根目录或 studio/），避免重复安装依赖。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

node scripts/build-display.mjs

if [ -x node_modules/.bin/vite ]; then
  VITE="$ROOT/node_modules/.bin/vite"
elif [ -x studio/node_modules/.bin/vite ]; then
  VITE="$ROOT/studio/node_modules/.bin/vite"
else
  echo "未找到 Vite：请先执行 npm install（或 bash scripts/build-studio.sh）" >&2
  exit 1
fi
"$VITE" build --config vite.config.js
echo "✓ 展示端已构建到 web/app/（改动后请把产物一并提交）"
