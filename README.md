# printcast

> **Print + Broadcast** —— 把直播间弹幕、礼物与**剧本化内容**，按序打进 3D 现实。
>
> *Turn live-stream chat, gifts and scripted content into 3D avatar prints.*

一个在浏览器里跑的三维打印直播台：观众的评论、点赞、礼物会触发一场逐层挤出的 3D 打印动画，成品自动出分、转运、上架；也支持按「内容包」顺序播放指定人物（如明朝十六帝、故事人物出场表），讲到谁就打谁。

- **完全开源免费（MIT）**，无任何付费或授权限制，可自由下载、使用、修改、分发。
- **零 npm 依赖**：采集层、传输层、渲染层全部手写，Three.js 已 vendored 在 `assets/`，可完全离线运行。
- **中英双语**：`web/index.html` / `web/index-en.html` 独立文件、独立语音包，互不影响。

---

## 快速开始

```bash
# 1) 还原大体积二进制资源（音频/贴图/截图，约 33MB，未随 git 提交）
bash scripts/vendor-assets.sh

# 2) 启动
#    Windows：双击 scripts/start.bat
#    或手动起 HTTP 服务（必须走 HTTP，直接双击 HTML 会被浏览器的 ES modules 限制）
python src/desktop/desktop_launcher.py --server-only
#    然后打开 http://127.0.0.1:8080/web/index.html
```

依赖：Python 3（桌面版另需 `pywebview` + WebView2 Runtime）、Node.js（接入真实直播时）。

> **为什么必须走 HTTP**：页面用原生 ES modules 加载 `../src/**/*.mjs`，`file://` 协议会被 CORS 拦死。

## 界面预览

<p align="center">
  <img src="docs/screenshots/01-3d-scene.jpg" width="49%" alt="3D打印现场（AI生图背景）">
  <img src="docs/screenshots/04-main-page.jpg" width="49%" alt="主界面与直播连接面板"><br>
  <img src="docs/screenshots/02-rules-panel.png" width="32%" alt="规则演示台">
  <img src="docs/screenshots/03-print-log.png" width="32%" alt="打印记录">
  <img src="docs/screenshots/05-controls.png" width="32%" alt="控制与声音面板">
</p>

## 项目结构

按「采集 → 传输 → 渲染 → 桌面」四层切分，每一层只依赖它下面的一层：

```
printcast/
├── src/
│   ├── collector/    采集层   live-collector.mjs  bridge-probe.mjs  rules-exporter.mjs
│   ├── server/       传输层   bridge-server.mjs
│   ├── render/       渲染层   scene-channel.mjs  scene-output.mjs  render-budget.mjs
│   ├── rules/        规则层   print-settings.mjs  demo-rules.mjs
│   ├── audio/        语音层   printer-audio.mjs  gift-speech.mjs  gift-speech-en.mjs
│   └── desktop/      桌面层   desktop_launcher.py  scene_relay.py
├── web/              运行页面  index.html  index-en.html  live-view.html  live.html
├── site/             宣传页    features.html  guide.html  cover-*.html
├── tests/            测试      *.test.mjs  test_*.py  check-popup.mjs  test-bridge-ports.mjs
├── scripts/          脚本      start*.bat  run-*-forever.bat  vendor-assets.sh
├── assets/           静态资源  three.module.js  OrbitControls  Reflector  贴图  音频
├── docs/ exports/    截图封面 / 朗读文案导出
└── extract-original-icons.py  wx-copy.js  ROADMAP.md  LICENSE  .gitignore
```

| 层 | 职责 | 依赖方向 |
|---|---|---|
| `collector/` | 挂本机 Chrome CDP，双链路抓弹幕；手写 protobuf 解码做头像零点击直读；三层兜底 + 持久缓存 | → `server/` |
| `server/` | 只用 Node stdlib 手写的 WebSocket 服务（`ws://127.0.0.1:8765`），带 `/health` 与端口自动回退 | 无 |
| `render/` | Three.js 打印仿真、场景输出管线、自适应渲染预算 | → `assets/` |
| `rules/` | 8 个打印开关、演示队列、30 秒空闲补位 | 无 |
| `audio/` | 程序化音效 + 中英双语 TTS 文案 | → `assets/` |
| `desktop/` | WebView2 封装、多窗口 WebRTC 信令、领导者选举（同一时刻只有一个窗口真正打印） | → 全部 |

> 命名原则：采集层不绑定平台（不叫 douyin-*，为多平台适配铺路）；JS 用 kebab-case、Python 用 snake_case；文件名即职责。

## 运行机制

打开后自动加载测试头像，逐层打印、出分、转运到前方横向传送带，前后流水并行。暂停同时冻结打印和流水线；跳过只丢弃当前打印中的物品。

**空闲补位**：连续 30 秒没有任何观众消息会自动补一张测试头像（之后每 30 秒最多一张、队列最多预留 2 张），真实消息一到立刻让位。

**镜头**：可拖动视角检查模型，随时「＋保存当前视角」（最多 10 个命名镜头），随手拖动的视角与上次所用镜头都会自动记忆，刷新回到上次机位。

**画质五档**：极速低配（关反射/阴影/扫光，集显流畅）/ 标准 / 2×精细 / 4×超清 / 影院级 2×（内部渲染 2×，叠加 SSAA 抗锯齿约 4×，反射与阴影贴图同步升档）。选择自动记忆。

**后台推进**：页面隐藏时打印由后台时钟继续推进，切回来自动恢复渲染。

## 接入真实直播

**一键双窗口**：`scripts/start-all.bat` —— 启动打印服务 + 弹出「直播间窗口」（真实 Chrome，可扫码登录，登录后头像抓取更全）+ 独立应用窗口打开打印程序。

也可分开：`scripts/start.bat`（打印服务）+ `scripts/start-bridge.bat`（采集）。

页面自动连接 `ws://127.0.0.1:8765`，右上角亮起「● 直播数据 · 数据桥已连接 · 房间号」。中英双语可切换；「🎬 独立场景窗口」可把 3D 现场弹成纯画面窗口（适合 OBS 窗口采集或第二屏），此时打印由场景窗口接管，主窗口只计数。

**数据格式**（WS 文本 JSON）：

```json
{"name": "观众昵称", "avatar": "https://..."}
{"nickname": "...", "avatarUrl": "..."}
```

**事件映射**：

| 事件 | 行为 |
|---|---|
| 评论（含 666、999） | 1 张小图（评论也要排队） |
| 点赞 | 按「本场点赞」增量，1 赞 1 张小图；抖音不公开点赞人，采集层在花名册上交错轮换归属，**每个点赞都带真实昵称与头像**，同一人每轮最多 3 次 |
| 爱心 / 小心心 | 1 张大图 |
| 啤酒 | 2 张大图 |
| 棒棒糖 | 3 张大图 |
| 其他礼物 | 1 张大图 |
| 进场 / 关注 | 播报欢迎，不打印 |

礼物插队最前，评论排在点赞之前，点赞高峰约每 0.4 秒放行一张防刷屏。

**头像三层保障**：

1. **协议级直读**——直接解码直播间 WebSocket 协议帧，每条评论/点赞/进场/关注/礼物消息与活跃榜都自带头像，零点击零延迟入库，写入 `avatar-cache.json` 跨重启跨房间复用。
2. **页面多来源采集**——观众列表/贡献条/进出场滚动累积，弹幕昵称与面板昵称归一化模糊匹配。
3. **资料卡补取**——未匹配的观众自动点昵称开资料卡，每昵称最多 4 批 × 3 个点击位置，4 秒后可再试；没人发言时每 45 秒也给最近活跃无头像观众补点 2 次。全失败则生成彩色首字头像。

**CDP 端口优先级**：自建无头 Chrome(`:9223`，可登录) → BrowserOS neo(`:9110`) → 已开调试端口的 Chromium(`:9222`)。

> 页面与采集层均只读公开弹幕，不登录、不发弹幕、不赠送礼物。请仅使用你有权使用的数据接入方式。

## WebView2 桌面版

`scripts/start.bat` 与 `scripts/start-all.bat` 均启动独立 WebView2 应用。填写房间号 → 打开直播间窗口登录 → 点击开始抓取。停止抓取会停掉本应用启动的采集进程；关闭主窗口会清理登录窗口与采集进程。首次使用请关闭旧版进程以免占用端口（新窗口用独立登录配置，需重新登录）。依赖：Python、pywebview、WebView2 Runtime、Node.js。

## 测试

```bash
cd tests && node --test *.test.mjs        # 53 个 node:test 用例
python -m pytest test_scene_relay.py -q   # Python 信令测试
node check-popup.mjs                      # CDP 弹窗集成（需桌面版在跑）
```

## 首次拉取说明

大体积二进制（音频 wav / 背景贴图 png / 文档截图，约 33MB）未随 git 提交，执行一次 `bash scripts/vendor-assets.sh` 即可从上游按原相对路径还原，之后完全离线可运行。

## 路线图

衍生方向落地计划见 [ROADMAP.md](ROADMAP.md)：AI 真实 3D 头像、多平台适配、云端 SaaS、电商闭环、观众数据中台、多机编排、硬件外设、合规本地化、测试产品化、虚拟主播联动。

## 许可

[MIT](LICENSE)。本仓库基于 [3d-printer-live](https://github.com/rhfbgfgfdg999999/3d-printer-live)（志哥AI 出品，MIT）重构：重排为分层结构、统一英文命名、修复画质档位口径与端口注释、清理死文件。
