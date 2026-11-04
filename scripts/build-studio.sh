#!/usr/bin/env bash
# 构建数据工作台（Vue + Vite）生产产物到 web/studio-dist/。
# 主服务以 /studio/ 前缀托管该目录，因此构建后打开 http://127.0.0.1:8080/studio/ 即可使用。
# 仅需在有改 studio/ 源码时重新运行；纯 Python / 渲染页改动无需此步。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../studio"
if [ ! -d node_modules ]; then
  echo "首次构建，安装依赖…"
  npm install
fi
npm run build
echo "✓ 工作台已构建到 web/studio-dist/（由 python -m printcast 的 /studio/ 托管）"
