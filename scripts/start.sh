#!/usr/bin/env bash
# printcast 启动器（macOS / Linux）
#
#   bash scripts/start.sh                 # 桌面窗口版（需 pywebview）
#   bash scripts/start.sh --server-only  # 仅 HTTP 服务 + 自动开浏览器
#   bash scripts/start.sh --port 8090    # 指定端口
#
# 首次运行会自动创建 .venv 并做 editable install；之后直接复用。
set -euo pipefail
export PIP_DISABLE_PIP_VERSION_CHECK=1

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
  echo "▸ 首次运行：创建虚拟环境 $VENV"
  python3 -m venv "$VENV"
fi

# 检查是否已安装本包；未安装则做 editable install（核心零依赖，秒级完成）。
if ! "$PY" -c "import printcast" >/dev/null 2>&1; then
  echo "▸ 安装 printcast（editable）"
  "$PY" -m pip install -q -e .
fi

# 桌面窗口版需要 pywebview；仅在用户没指定 --server-only 时提示。
if [[ "${*:-}" != *"--server-only"* ]] && ! "$PY" -c "import webview" >/dev/null 2>&1; then
  echo "▸ 桌面窗口需要 pywebview，正在安装…"
  "$PY" -m pip install -q -e ".[desktop]"
fi

echo "▸ Python: $("$PY" -V 2>&1)"
exec "$PY" -m printcast "$@"
