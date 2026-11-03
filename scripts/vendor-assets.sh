#!/usr/bin/env bash
# 一键拉取运行时二进制资源（贴图 / 音频 / 文档截图 / 平台封面）。
# 这些文件体积大（约 33MB），未随 git 提交，此处按原相对路径从上游仓库还原。
#
# 用法：在仓库根目录执行  bash scripts/vendor-assets.sh
# 可选：bash scripts/vendor-assets.sh <branch>   指定上游分支（默认 main）
set -u
UPSTREAM_REPO="${UPSTREAM_REPO:-rhfbgfgfdg999999/3d-printer-live}"
BRANCH="${1:-main}"
base="https://raw.githubusercontent.com/$UPSTREAM_REPO/$BRANCH"

fetch() {
  local url="$1" out="$2"
  mkdir -p "$(dirname "$out")"
  for t in $(seq 1 8); do
    local code
    code=$(curl -sS -m 120 --retry 4 --retry-delay 3 -o "$out" -w "%{http_code}" "$url" 2>/dev/null)
    if [ "$code" = "200" ] && [ -s "$out" ]; then
      echo "OK   $out ($(wc -c <"$out") bytes)"
      return 0
    fi
    sleep 2
  done
  echo "FAIL $out  <- $url"
  return 1
}

echo "=== 1/5 vendored 代码依赖（three.module.js，约 1.3MB）==="
fetch "$base/assets/three.module.js" "assets/three.module.js"

echo "=== 2/5 音频 ==="
fetch "$base/assets/printing-writing.wav" "assets/printing-writing.wav"
fetch "$base/assets/robot-arm.wav" "assets/robot-arm.wav"
fetch "$base/assets/audio-check.wav" "assets/audio-check.wav"

echo "=== 3/5 场景贴图（房间背景 / 头像图集）==="
for p in avatar-atlas garden home-window-v2 home linen live-rules-exact live-rules night oak plaster study workshop; do
  fetch "$base/assets/generated/$p.png" "assets/generated/$p.png"
done

echo "=== 4/5 礼物原始图标 ==="
for i in beer heart like lollipop; do
  fetch "$base/assets/generated/original-icons/$i.png" "assets/generated/original-icons/$i.png"
done

echo "=== 5/5 文档截图与平台封面（仅宣传页/封面生成器需要）==="
for s in 01-3d-scene.jpg 02-rules-panel.png 03-print-log.png 04-main-page.jpg 05-controls.png; do
  fetch "$base/docs/screenshots/$s" "docs/screenshots/$s"
done
fetch "$base/docs/tutorial-cover.jpg" "docs/tutorial-cover.jpg"
fetch "$base/tiktok-cover.png" "tiktok-cover.png"
fetch "$base/youtube-cover.png" "youtube-cover.png"

echo "=== vendor-assets done ==="
du -sh assets docs tiktok-cover.png youtube-cover.png 2>/dev/null
