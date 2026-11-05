# printcast

> **Print + Broadcast** —— 把直播间弹幕、礼物与**剧本化内容**，按序打进 3D 现实。
>
> *Turn live-stream chat, gifts and scripted content into 3D avatar prints.*

一个在浏览器里跑的三维打印直播台：观众的评论、点赞、礼物会触发一场逐层挤出的 3D 打印动画，成品自动出分、转运、上架；也支持按「内容包」顺序播放指定人物（如明朝十六帝、故事人物出场表），讲到谁就打谁。

- **完全开源免费（MIT）**，无任何付费或授权限制，可自由下载、使用、修改、分发。
- **零 npm 依赖**：采集层、传输层、渲染层全部手写，Three.js 已 vendored 在 `assets/`，**核心几何渲染完全离线可跑**；3D 场景贴图与音效需按需拉取（见快速开始第 1 步），缺失时降级为无贴图/静音。工作台 `/studio/` 的产物已入库，clone 即用。
- **纯净中文版**：展示端只保留 `web/index.html` 一套中文实现；英文版、跳转壳、竖屏空壳页与宣传页已全部下线。

---

## 快速开始

项目已按正式 Python 结构组织（虚拟环境 + `pyproject.toml` + 可安装包 + 命令行入口）。

```bash
# 1) 可选：还原 3D 场景贴图与音效（约 33MB，未随 git 提交）
#    跳过也能启动服务与工作台，只是背景贴图/音效缺失；不需要 npm 或外网也能跑核心渲染。
bash scripts/vendor-assets.sh

# 2) 一键启动（macOS / Linux）：脚本自动建 .venv、editable install、开浏览器
bash scripts/start.sh --server-only

#    Windows：双击 scripts/start.bat（桌面窗口版）
#    或命令行：python -m printcast --server-only
```

手动安装（等价做法）：

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .                     # 核心零依赖，注册 printcast 命令
pip install -e ".[desktop]"          # 可选：桌面窗口版才需要 pywebview
python -m printcast --server-only    # 或简写：printcast --server-only
```

依赖分层：**核心服务零第三方依赖**（纯标准库，`--server-only` 可在空白 venv 里跑），桌面窗口需 `pywebview`，接入真实直播需 Node.js。

> **`--server-only` 不会卡住不响应**：它会一直占着终端，因为 HTTP 服务就跑在这个进程里。
> 启动后终端会打印 `printcast 服务已启动：http://127.0.0.1:8080/`，并自动用默认浏览器打开页面。
> 若浏览器没弹出，手动访问打印出来的地址即可；加 `--no-open-browser` 可关闭自动打开。

### 命令与配置

| 命令 | 作用 |
|---|---|
| `printcast` / `python -m printcast` | 桌面窗口版（需 `pywebview`） |
| `printcast --server-only` | 仅 HTTP 服务 + 自动开浏览器，用于纯前台调试 |
| `printcast --port 8090` | 指定 HTTP 端口（默认 8080，被占时自动顺延） |
| `printcast --room 123456 --capture` | 启动后直接打开直播间并开始抓取 |
| `printcast --seed [--overwrite]` | 把内置示例内容包（明朝十六帝 + 三国/水浒/红楼/西游）写入 SQLite（`data/printcast.db`）并同步导出 `data/packs/*.json` 后退出；加 `--overwrite` 可覆盖已存在的同名包重新播种 |
| `printcast --schedule [PACK...]` | 预览指定内容包的出场顺序后退出（不跟包名则列出全部可用包）；可配合 `--mode`/`--strategy`/`--count` |
| `printcast --db info` | 打印数据库后端、各表行数、完整性校验（PRAGMA integrity_check）与当前镜像状态，不改动数据 |
| `printcast --db export` | 把库内容导出成与旧版同构的 JSON（`data/packs/*.json` + `data/media/index.json` + `data/settings.json`），便于 git 比对 / 备份 / 分发 |
| `printcast --db verify` | 校验库完整性（设置存在、每个内容包的字符数 > 0、媒体索引自洽），全部通过才返回 ok |

环境变量（不引入 dotenv 依赖，直接 `export` 即可）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `PRINTCAST_PORT` | `8080` | HTTP 服务首选端口 |
| `PRINTCAST_LIVE_DEBUG_PORT` | `9224` | 直播窗口的 CDP 调试端口 |

### 旧命令兼容

`python src/desktop/desktop_launcher.py --server-only` 与 `from desktop_launcher import ...` **继续可用**：
`src/desktop/` 下两个文件已改为薄转发到 `printcast` 包，保证旧 bat 脚本与外部引用不失效。新代码请统一用 `python -m printcast` / `from printcast.xxx import ...`。

### macOS 注意

- **不要用 Safari 调试**：页面依赖 WebGL2 与 `importmap`，Safari 13（10.15 自带）都不支持。请用 Chrome / Edge / Chromium 打开。
- **`--app` 独立窗口需要 Chromium 系浏览器**：脚本会自动在 `/Applications` 下按 Chrome → Chromium → Edge → Brave 顺序查找；都没有时「独立场景窗口」不可用（其余功能正常）。
- 窗口后端自动切换：macOS 用 `cocoa`，Windows 用 `edgechromium`。
- 若终端一直没有任何输出，用 `python -V` 和 `which python` 确认解释器是否指向 `.venv/bin/python`。


> **为什么必须走 HTTP**：`web/app/app.js` 是 ES module，投屏窗口 `live-view.html` 还用 `importmap` 加载 `../assets/**`，`file://` 协议会被 CORS 拦死。

## 界面预览

<p align="center">
  <img src="docs/screenshots/01-3d-scene.jpg" width="49%" alt="3D打印现场（AI生图背景）">
  <img src="docs/screenshots/04-main-page.jpg" width="49%" alt="主界面与直播连接面板"><br>
  <img src="docs/screenshots/02-rules-panel.png" width="32%" alt="规则演示台">
  <img src="docs/screenshots/03-print-log.png" width="32%" alt="打印记录">
  <img src="docs/screenshots/05-controls.png" width="32%" alt="控制与声音面板">
</p>

## 项目结构

按「采集 → 传输 → 渲染 → 桌面」四层切分；Python 侧已完整包化，JS 侧仍是原生 ES modules（零构建、零 npm 依赖）：

```
printcast/
├── pyproject.toml       依赖 / 入口点 / pytest / ruff 配置
├── requirements.txt     兼容 pip -r 的空依赖声明
├── src/
│   ├── printcast/       Python 包（可 pip install -e .）
│   │   ├── __main__.py      python -m printcast
│   │   ├── cli.py           argparse + 三种运行形态 + 重启
│   │   ├── config.py        路径/端口/平台/浏览器候选，环境变量覆盖
│   │   ├── probe.py         端口探测、数据桥健康检查（裸直连，绕开系统代理）
│   │   ├── relay.py         SceneRelay：有界 WebRTC 信令 + 类型白名单（+ view-appearance）
│   │   ├── server.py        HTTP 静态服务 + `/__api/*`（调度/广播）+ 本机端点
│   │   ├── scheduler.py     出场顺序调度引擎（sequence/weighted/trigger + 多包组合，seed 可复现）
│   │   ├── samples.py       内置内容包（明朝十六帝 + 三国/水浒/红楼/西游）一键 seed
│   │   ├── broadcast.py     出场广播控制器（驱动 SceneRelay 的 view-appearance）
│   │   └── desktop.py       DesktopApi（唯一 import webview 的模块）
│   ├── collector/    采集层   live-collector.mjs  parse.mjs  collect-script.mjs  bridge-probe.mjs  rules-exporter.mjs
│   ├── server/       传输层   bridge-server.mjs
│   ├── render/       渲染层   scene-channel.mjs  scene-output.mjs  render-budget.mjs
│   ├── rules/        规则层   print-settings.mjs  demo-rules.mjs
│   ├── audio/        语音层   printer-audio.mjs  gift-speech.mjs
│   └── desktop/      兼容层   desktop_launcher.py  scene_relay.py（薄转发，勿写新代码）
├── web-src/          展示端源码（构建期）
│   ├── parts/        按职责分片：运行时 / 场景 / 打印引擎 / 交互层
│   ├── core/         可独立 import 的纯逻辑（队列策略、进度语义）
│   ├── styles/       分层样式：令牌 / 骨架 / HUD / 浅色主题
│   └── imports.txt  构建入口的依赖清单
├── web/              运行页面（产物已入库，clone 即用）
│   ├── index.html         唯一中文入口（纯 DOM 骨架）
│   ├── app/app.js         构建产物（Three.js 已打包，离线自包含）
│   ├── app/app.css        构建产物（分层样式合并）
│   ├── settings-loader.js 统一配置入口
│   ├── live-view.html     投屏镜像窗口（WebRTC 接收端，原生 ES module）
│   └── studio-dist/       控制台构建产物
├── tests/            测试      *.test.mjs  test_*.py  conftest.py
├── scripts/          脚本      build-display.sh  build-studio.sh  start*.bat  vendor-assets.sh
├── tests/            测试      *.test.mjs  test_*.py  conftest.py
├── scripts/          脚本      start.sh  start*.bat  run-*-forever.bat  vendor-assets.sh
├── assets/           静态资源  three.module.js  OrbitControls  Reflector  贴图  音频
├── docs/ exports/    截图封面 / 朗读文案导出
└── ROADMAP.md  LICENSE  .gitignore
```

采集层内部再切三块，各管一件事，互不纠缠：

| 文件 | 职责 |
|---|---|
| `parse.mjs` | 纯函数：弹幕行解析、protobuf wire-format 遍历、`eachEnvelope` 信封识别、头像 URL 判定、点赞公平分配。无副作用，测试直接 import |
| `collect-script.mjs` | 注入到直播间页面执行的采集脚本字符串。只按文本特征定位（弹幕行形态、头像 URL、在线观众入口），**不依赖抖音混淆后的类名** |
| `live-collector.mjs` | 进程本体：CDP 挂接、端口探测、协议帧入口 `handleWSFrame`、头像三层兜底、令牌桶限流、断线重连、房间切换 |

| 层 | 职责 | 依赖方向 |
|---|---|---|
| `collector/` | 挂本机 Chrome CDP，双链路抓弹幕；手写 protobuf 解码做头像零点击直读；三层兜底 + 持久缓存 | → `server/` |
| `server/` | 只用 Node stdlib 手写的 WebSocket 服务（`ws://127.0.0.1:8765`），带 `/health` 与端口自动回退 | 无 |
| `render/` | Three.js 打印仿真、场景输出管线、自适应渲染预算 | → `assets/` |
| `rules/` | 8 个打印开关、演示队列、30 秒空闲补位 | 无 |
| `audio/` | 程序化音效 + 中英双语 TTS 文案 | → `assets/` |
| `src/printcast/` | Python 侧：静态服务、桌面窗口、本机控制端点、WebRTC 信令中继 | 核心零依赖，仅 `desktop.py` 需 pywebview |
| `src/printcast/{db}.py` | **SQLite 数据层**（标准库 `sqlite3`，WAL，短连接 + 表级锁）：packs / characters / media / settings / audit / runtime_state / meta 七张表；首次启动幂等从 JSON 迁移，对外隐藏「库 vs JSON」差异 | → `config` |
| `src/printcast/{schema,storage,importer,templates,api}.py` | **数据访问层**：领域模型（单一事实来源）、库读写封装、CSV/JSON 导入校验、模板生成、REST 分发；`storage.save_pack / delete_pack / list_packs` 等签名保持不变，内部已走 `db` | → `db` / `config` |
| `src/printcast/{scheduler,samples,broadcast}.py` | **出场调度层**：顺序引擎（三模式 + 多包组合、seed 可复现）、内置示例包、经 SceneRelay 实时广播 | → `schema`/`relay` |
| `desktop/`（旧） | 两个薄转发模块，仅为兼容旧 bat / guide / 外部引用 | → `printcast` |

> 命名原则：采集层不绑定平台（不叫 douyin-*，为多平台适配铺路）；JS 用 kebab-case、Python 用 snake_case；文件名即职责。

**数据层是真正的业务逻辑，但不是前后端分离**：内容包 CRUD、导入校验、图片上传集中在 `src/printcast/` 的 `schema/storage/api` 一组纯模块里，通过 `/__api/*` 暴露给工作台。展示端现已纳入 Vite 构建链（源码 `web-src/` → 产物 `web/app/` 入库），但 Vite **只在构建期**使用：运行时仍是原生 ES module、Three.js 继续 vendored，clone 后不装 npm 也能跑。

### 控制台与展示端的边界（本里程碑明确）

- **控制台 = 唯一的配置与状态来源**：`/studio`（Vue 工作台）与本地 Python API（`api.py` + `settings.py`）负责写一切——内容包、出场广播、打印规则、品牌与展示文案。展示端**绝不直接写配置**。
- **展示端只读取、只渲染**：`web/settings-loader.js` 是展示端唯一的配置入口，只发一次 `GET /__api/settings`（返回 `{ok, settings}`，必须取 `settings` 本体）；`web-src/parts/` 的渲染模块经 `window.__PC.ready` 复用同一份设置，不再各自 fetch。
- **控制命令只在控制台**：出场广播的开始 / 下一个 / 点名 / 重置全部在 `/studio`；展示端的打印规则面板为只读并指向 `/studio`。
- **所有控制台设置都有真实消费方**：
  | 设置 | 消费方 |
  |---|---|
  | `branding.*` | `settings-loader` 的 `[data-bind]` / `[data-bind-html]` / `[data-links]` / `--accent` |
  | `display.theme` / `showDemoBadge` / `showAnnounce` / `announceText` | `settings-loader` + `app.css` 浅色主题与公告条样式 |
  | `printer.rules` / `autoDemo` / `demoGapMs` / `idleFill` / `idleSeconds` | 两个渲染模块的 `printRules` 与自动演示开关 |
  | `broadcast.defaultPacks` / `strategy` / `mode` / `loop` | 工作台广播表单初值（未开播时） |
  | `broadcast.autoStart` | `server.auto_start_broadcast()`：服务启动即按默认参数开播，配置异常静默跳过 |
  | `broadcast.speech` / `scriptedPrint` | M1 出场打印的门控 |
  | `live.defaultRoom` / `platform` | 展示端回填房间号输入框与占位文案 |
- **鉴权**：所有 `/__api/*` 与 `/__` 本机端点要求 Host 为 `127.0.0.1` / `localhost` / `::1` 加当前端口，且 `Sec-Fetch-Site` 若存在只能是 `same-origin` / `none`（缺失时放行，Safari 不发该头），防止外部站点借本地服务读写数据或拉起进程；`/__health` 除外（仅供存活探测）。
- **操作日志由服务端统一埋点**（P1）：`src/printcast/audit.py` 基于 SQLite `audit` 表记录所有本机写操作（设置、内容包、图片、广播、数据桥、窗口控制），失败动作同样留痕；前端只读取 `GET /__api/audit`，**不靠浏览器上报**。展示端高频信令不记录。`audit` 表 500 条上限、字段截断、不记请求体，清空（DELETE）时保留一条 `audit.clear` 记录以维持可回溯性；原先的 `data/audit.jsonl` 已不再使用（见「SQLite 数据落库」）。
- **设置页 iframe 预览不破坏边界**（P1）：预览加载的是真实展示页（自己 `GET /__api/settings`），控制台**不向 iframe 注入草稿配置**；只有已保存的设置会呈现，保存成功后自动刷新 iframe。可切换目标页与缩放比例，也可暂停预览省渲染资源。
- **静态页面全面参数化**：原先内嵌在 HTML 里的品牌名、广告条、联系方式、强调色已全部移除；`site/` 宣传页亦清除第三方署名与水印，仅保留 printcast 自有品牌。旧版硬编码广告条由控制台的 `display.showAnnounce` + `announceText` + `branding.links` 取代（默认关闭，无任何硬编码内容）。
- **回归护栏**：`tests/settings-loader.test.mjs` 用最小 DOM 桩在 Node 里跑真实装载器，锁死「只 GET / 取 settings 本体 / 展示端不写配置」；`tests/test_settings.py` 覆盖布尔与数值收口、危险协议拒绝、未知分区剔除与 autoStart。

### SQLite 数据落库（数据层改造）

原先数据层是 **JSON 文件 + 原子写**（内容包 `data/packs/*.json`、设置 `data/settings.json`、日志 `data/audit.jsonl`），广播进度与场景事件则是**纯内存**——多线程并发下读改写会丢更新、重启即丢状态。本次改造把全部状态收口到**单文件 SQLite**（`data/printcast.db`，标准库 `sqlite3`，WAL 模式，零第三方依赖）：

- **七张表**：`packs`（内容包本体）、`characters`（人物，外键关联 packs，承载 tags/weight/order/speech/avatar）、`media`（图片索引）、`settings`（单行 JSON）、`audit`（操作日志）、`runtime_state`（广播进度 / 当前角色 / seed / startedAt，`startedAt` 缺省为进程启动时间）、`meta`（schema 版本 + 迁移标记）。
- **首次启动幂等迁移**：`db.ensure_db()` 在建库后，若检测到旧版 JSON 文件且 `meta` 未标记迁移，会把它们整库导入并打标；之后**单一事实来源是数据库**，JSON 仅作为可比对 / 备份 / 分发格式，由 `export_json()` 在每次写后尽力镜像（`data/printcast.db*`、`data/settings.json`、`data/audit.jsonl` 均已被 `.gitignore` 排除，不入库）。
- **并发安全**：关键写用 `BEGIN IMMEDIATE` + 表级 `threading.Lock`，读改写不再丢更新；`audit` 的「清空留痕」在单事务内 `DELETE` 再 `INSERT`，原子完成。
- **广播进度持久化**：`broadcast.next/trigger/reset` 实时写 `runtime_state`；`BroadcastController(restore=True)` 能在服务重启后从库恢复「当前角色 / seq / seed / startedAt」并继续正确推进。
- **对外契约不变**：`storage.*` / `settings.*` / `audit.*` 的函数签名与返回形状保持原样，所有 `/__api/*` 行为与 P1 一致；新增 `GET /__api/db` 只读暴露后端类型、各表行数与 `integrity_check`，供工作台「系统」页展示。

> 设计取舍：刻意采用「SQLite 库 + JSON 镜像」双写，而非纯 JSON 或纯数据库——库解决并发与持久化，JSON 保留人类可读 / git 比对 / 跨机分发能力，且迁移对存量用户完全透明（旧 `data/` 在有库之前仍是唯一真相）。

**Python 包内部的依赖方向**：`cli → desktop/server/api → probe/relay → config`。`config` 不依赖任何兄弟模块；`desktop.py` 是唯一 import `webview` 的文件，所以 `--server-only` 不装桌面依赖也能启动；`api.py` 是纯函数分发层，`tests/test_api.py` 可直接调 `api.dispatch()` 而不起 HTTP 服务。

## 前端结构（HTML / CSS / ES 模块）

展示端已开启前端工程化，不再是 124KB 单页：

| 层 | 位置 | 说明 |
|---|---|---|
| 源码 | `web-src/parts/*.js` | 按职责分为运行时 / 三维场景 / 打印引擎 / 交互层四片 |
| 纯逻辑 | `web-src/core/queue-policy.js` | 真 ES 模块，浏览器与 Node 测试共用；负责队列上限、去重与进度语义 |
| 样式 | `web-src/styles/*.css` | 令牌、骨架、HUD、浅色主题分层，不再靠 `!important` 补丁互相覆盖 |
| 构建 | `vite.config.js` + `scripts/build-display.sh` | Vite 仅构建期使用；产物固定为 `web/app/app.js` / `app.css` 并入库 |
| 入口 | `web/index.html` | 只留 DOM，引用产物；URL 契约 `/web/index.html` 保持不变 |

`web-src/` 与旧 `web/` 同级，因此 `../src/**`、`../assets/**` 的相对 import 无需改写；构建产物把 Three.js 一并打包，离线自包含。分片之间共享一个模块作用域（渲染引擎是命令式的 Three.js 循环），纯逻辑与策略另放在 `core/` 下作为可测真模块。改了展示端源码请执行 `bash scripts/build-display.sh` 并把 `web/app/` 一并提交，CI 会用 `git diff --exit-code` 拦截产物漂移。

> `web/live-view.html` 是独立投屏窗口，故意**不**进构建链：它靠原生 importmap 解析 `OrbitControls.js` 的裸模块名 `three`，保留 `three` 的 importmap 声明是必需的。

中英两份逻辑目前仍是独立文件（差异约 15%，主要是文案与 TTS），合并为「单一模块 + i18n 字典」是下一步，见 [ROADMAP.md](ROADMAP.md)。

## 运行机制

打开后自动加载测试头像，逐层打印、出分、转运到前方横向传送带，前后流水并行。暂停同时冻结打印和流水线；跳过只丢弃当前打印中的物品。

**空闲补位**：连续 30 秒没有任何观众消息会自动补一张测试头像（之后每 30 秒最多一张、队列最多预留 2 张），真实消息一到立刻让位。

**镜头**：可拖动视角检查模型，随时「＋保存当前视角」（最多 10 个命名镜头），随手拖动的视角与上次所用镜头都会自动记忆，刷新回到上次机位。

**画质五档**：极速低配（关反射/阴影/扫光，集显流畅）/ 标准 / 2×精细 / 4×超清 / 影院级 2×（内部渲染 2×，叠加 SSAA 抗锯齿约 4×，反射与阴影贴图同步升档）。选择自动记忆。

**后台推进**：页面隐藏时打印由后台时钟继续推进，切回来自动恢复渲染。

## 数据工作台（内容包 / 导入 / 上传）

除了「实时直播驱动」，printcast 还支持**预先编排内容**——这正是「按内容包顺序播放指定人物（明朝十六帝、故事人物出场表）」的实现载体。打开 `http://127.0.0.1:8080/studio/`（服务启动后自动可用）即可使用，全程本机运行、不上传云端。

工作台采用「左侧导航 + 主工作区」的**中控台**布局，默认打开 **总览**：当前正在打印的角色、本机服务 / 数据桥 / 出场广播三灯状态、内容包与已出场计数，以及订阅 `/__scene-events` 的实时事件流。高频操作（开始广播 / 下一个 / 重置进度 / 拉起打印台与直播小窗 / 启停数据桥）都在一屏内完成，不用滚动、不用刷新。侧栏按「运行 / 资产 / 编排 / 配置」分组共 9 个视图（总览、出场广播、内容包、数据导入、图片资源、排期预演、控制台设置、系统、操作日志）。工作台自身的深浅主题存于 `localStorage`，与展示端 `display.theme` 互不影响。

| 功能 | 说明 |
|---|---|
| 总览中控台 | 2 秒轮询 `GET /__api/status` + 事件流长轮询；显示当前出场角色、链路状态、实时事件与快捷干预 |
| 内容包管理 | 搜索 / 排序；点标题打开**抽屉**查看人物表（头像、台词、权重、标签），可编辑保存、上下调序、增删人物、复制成新包、导出 JSON、导入 JSON；一个内容包 = 一组有序人物，由规则层按 `mode` 调度 |
| 模板下载 | 下载 CSV / JSON 模板，字段与系统完全一致，Excel 双击不乱码（带 BOM） |
| 数据导入 | 粘贴或上传 CSV，逐行校验、**绝不静默丢行**；错误会标注到具体行，一次改完再提交 |
| 图片上传 | 头像图片直接上传（PNG/JPEG/WebP，魔数+扩展名+大小三重校验），供内容包抽屉的人物头像下拉选用 |
| 排期预演 | 出场序列渲染成**时间轴卡片带**：固定 `seed` 复现、可复制复现链接、逐位本地预演、一键按预演参数开播（广播 `state.seed` 可核对） |
| 操作日志 | 9 个视图之一：按动作 / 关键词 / 失败筛选本机写操作，含成功失败统计与清空（保留清空记录） |
| 设置预览 | 右侧嵌真实展示页缩放 iframe，保存设置后自动刷新；可选择广播页 / 打印台 / 直播小窗 |

**为什么引入构建链**：工作台是唯一用上框架的页面——表格、表单校验、上传进度、错误列表正好是声明式 UI 的强项。它走独立的 **Vue 3 + Vite** 工程（`studio/`），产物落在 `web/studio-dist/`，由主服务以 `/studio/` 前缀托管；**主渲染页（`web/index.html`，111KB 原生 ES modules）不进构建链**，保持「核心零 npm 依赖、离线可跑」。

```bash
# 工作台开发（热更新）：先起主服务，再起 dev server（:5174 会把 /__api 代理到主服务）
python -m printcast --server-only
cd studio && npm install && npm run dev

# 重新构建生产产物（一键：安装依赖 + vite build，产物落到 web/studio-dist/）
bash scripts/build-studio.sh
```

> `web/studio-dist/` 的**构建产物已随仓库入库**（约 150 KB），因此全新 clone 后 `/studio/` 开箱即用，无需先装 Node 依赖。改了 `studio/` 源码后要重跑 `bash scripts/build-studio.sh`，并把新产物一并提交；否则线上仍是旧界面。若产物被误删，服务会显示带构建指引的引导页而不是裸 404。主渲染页与 Python 侧始终无需此步。

> 数据默认存在仓库根的 `data/`（用户内容包与上传图片不入库；示例包可提交）。
> 想改字段（如新增「朝代」「朝代起止」）？只改 `src/printcast/schema.py` 一处，CSV 模板、导入校验、前端表单会自动同步。

## 内容包出场顺序调度（明朝皇帝 / 故事人物）

把「预先编排的内容」按可配置的顺序播放出来，这正是「讲到谁就打谁」的核心。内置 **明朝十六帝**（按在位顺序 `order` 1–16）+ **三国演义 / 水浒传 / 红楼梦 / 西游记** 四个故事包，一键 `--seed` 即可用，也可在 `/studio/` 用 CSV 模板导入自定义内容包（如「清朝十二帝」「封神榜」）。

调度引擎 `src/printcast/scheduler.py` 是顺序逻辑的唯一事实来源，支持三种模式与三种多包组合：

| 维度 | 取值 | 含义 |
|---|---|---|
| `mode` | `sequence` | 严格按 `characters[].order` 升序出场（默认） |
| `mode` | `weighted` | 按 `weight` 加权随机抽取，同 `seed` 完全可复现 |
| `mode` | `trigger` | 绑定事件触发（`trigger` 字段），缺省落到 `defaultId` |
| 多包 `strategy` | `concat` | 整包先后拼接（A 全出完再出 B） |
| 多包 `strategy` | `interleave` | 按包轮流出场（A1,B1,A2,B2…） |
| 多包 `strategy` | `merged` | 跨包按 `order` 升序合并（1,1,2,2…） |

使用方式：

- **命令行预览**（不启动服务）：

  ```bash
  python -m printcast --seed                                   # 写入内置示例包
  python -m printcast --seed --overwrite                       # 覆盖已存在的内容包重新播种
  python -m printcast --schedule ming-emperors                 # 预览明朝十六帝出场顺序
  python -m printcast --schedule sanguo shuihu --strategy interleave   # 三国水浒轮流出场
  python -m printcast --schedule xiyouji --mode trigger        # 西游记按事件触发
  ```

- **工作台排期预演**：`/studio/` 的「排期预演」选内容包 + 策略 + 模式 + 数量 + **固定 seed** + 循环，拉 `GET /__api/schedule` 渲染成可点击的时间轴卡片带；「复制复现链接」得到完整参数 URL，「本地预演」在工作台内逐位高亮（**不触发真实广播 / 打印**），「按此配置开播」把同一 seed 交给广播控制器，`state.seed` 可核对。纯数字 seed 在前端统一收口成 number，避免 `Random('123')` 与 `Random(123)` 产生不同序列。

- **出场 HUD 字幕**：出场角色的姓名 / 台词 / 标签 / 来源直接叠在打印台画面上（`view-appearance` 经 `/__scene-events` 送达），不再另开卡片页；开始 / 下一个 / 点名 / 重置全部在 `/studio` 的广播控制区操作。

- **HTTP 端点**：

  | 端点 | 说明 |
  |---|---|
  | `GET /__api/schedule?pack=ming-emperors&mode=weighted&seed=20261104&count=8&loop=0` | 纯函数计划预览（无状态），返回出场顺序、`progress` 以及回显的 `seed` / `count`；`count` 上限 300，固定 seed 时序列完全可复现 |
  | `POST /__api/broadcast` | 有状态控制：`{action: start\|next\|trigger\|reset, packs, mode, strategy, seed, charId, loop}`，把「下一个出场角色」经 `view-appearance` 广播给所有订阅 `/__scene-events` 的客户端 |
  | `GET /__api/settings` | 读取全部控制台设置（branding / display / printer / broadcast / live），展示端只读此端点 |
  | `PUT /__api/settings` | 以深合并方式写入设置并即时持久化（原子写 + 输入净化）；仅控制台（Studio）调用，展示端不写 |
  | `DELETE /__api/settings` | 恢复出厂设置，仅控制台调用 |
  | `GET /__api/status` | 控制台总览聚合：服务端口与运行时长、数据桥探测（3s 缓存避免轮询堆积）、广播当前状态与 `startedAt` / `seed`、内容包 / 图片计数。只返回后端真实持有的状态，不臆造展示端内存里的打印队列长度 |
  | `GET /__api/audit?limit=100&action=pack.save&q=ming` | 控制台专属：按动作 / 关键词倒序查本机写操作，附全量统计 `stats`（总数 / 成功 / 失败 / 最近时间 / 动作清单 / 上限） |
  | `DELETE /__api/audit` | 清空操作日志（仅控制台），服务端随后补记一条 `audit.clear` |

> 扩展更多人物零代码：在 `/studio/` 导入自定义内容包，或在 `data/packs/` 直接放 JSON，调度引擎会按 `order`/`weight`/`trigger` 自动驱动。剧本出场与直播事件共用同一 `SceneRelay` 通道与同一条打印队列。

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

`bash scripts/start.sh`（macOS / Linux）或 `scripts/start.bat`（Windows）启动桌面窗口版。两者都会优先使用项目内的 `.venv`，并统一走 `python -m printcast`。填写房间号 → 打开直播间窗口登录 → 点击开始抓取。停止抓取会停掉本应用启动的采集进程；关闭主窗口会清理登录窗口与采集进程。首次使用请关闭旧版进程以免占用端口（新窗口用独立登录配置，需重新登录）。依赖：Python、pywebview、Node.js；**WebView2 Runtime 仅 Windows 需要**。

窗口后端自动切换：macOS 用 `cocoa`，Windows 用 `edgechromium`。`src/desktop/` 下的旧脚本已改为薄转发，但新代码一律写进 `src/printcast/`。

## 测试

```bash
pip install -e ".[test]"                  # 安装 pytest（可选）
python -m pytest                          # 127 个用例：数据层 / 信令 / 出场调度 / 广播 / HTTP 端点 / 兼容转发 / SQLite 落库 / 操作日志
cd tests && node --test *.test.mjs        # 75 个 node:test 用例（含前端结构防回退 / 工作台 API 契约）
```

覆盖分层：

| 测试 | 验证内容 |
|---|---|
| `test_api.py` | 数据层全链路：schema 驱动、内容包 CRUD、模板生成、CSV/JSON 导入逐行校验、图片上传（魔数校验 + 中文名保留）、路径穿越防护、**`/__api/db` 只读状态端点** |
| `test_server.py` | 静态资源、no-store 头、文档根、`/__` 端点鉴权、存活探针、端口复用、信令 publish→poll、非法路径拦截、**API 经 GET 路由到 api 层**、广播状态重启恢复、畸形广播体 400 不误推进、DELETE `/settings/anything` 不再清空配置 |
| `test_db.py` | **SQLite 落库**：建库幂等迁移、WAL、并发写不丢更新、JSON 镜像导出/导入往返、删除后恢复性重建、verify 完整性、广播进度持久化与恢复 |
| `test_audit.py` | P1 操作日志（已迁 SQLite `audit` 表）：持久化 / 倒序与筛选 / 字段截断 / 清空保留 `audit.clear` / API 路由；schedule 的 seed 回显、可复现与 count 上限 |
| `test_compat.py` | 旧 `desktop_launcher` / `scene_relay` 薄转发仍指向同一实现 |
| `test_scene_relay.py` | 有界信令：隔离客户端、不重放旧 offer |
| `test_scheduler.py` | 出场调度引擎：三模式（sequence/weighted/trigger）、多包组合（concat/interleave/merged）、seed 可复现、进度/历史/循环 |
| `test_audit.py` | P1 操作日志：持久化 / 倒序与筛选 / 损坏行跳过 / 上限裁剪 / 字段截断 / 清空 / API 路由，以及 schedule 的 seed 回显、可复现与 count 上限 |
| `test_pack_roundtrip.py` | P1 内容包抽屉数据契约：编辑保存、复制成新包、导出 JSON 再导入、非法编辑 422 不落盘，锁死 tags 数组→分号串（防 M0 脏值回归） |
| `test_broadcast.py` | 广播控制器经 `SceneRelay` 发布 `view-appearance`、HTTP `/__api/broadcast` 端到端（开始/下一个/触发/重置） |
| `html-structure.test.mjs` | HTML 不含内联 style/script、引用可解析、模块 import 全命中、importmap 齐全 |
| `tests/*.test.mjs` | 采集层 protobuf 解码、打印队列、画质预算、语音文案、礼物抢占；`studio-api.test.mjs` 用最小 fetch 桩锁死工作台请求契约（schedule 复现参数、日志筛选、seed 类型、内容包保存 / 导入） |
| `test_native_output.py` | GPU + WebView 端到端检查，**手动运行**（`python tests/test_native_output.py`），不参与 pytest 收集 |

## 首次拉取说明

大体积二进制（音频 wav / 背景贴图 png / 文档截图，约 33MB）未随 git 提交，执行一次 `bash scripts/vendor-assets.sh` 即可从上游按原相对路径还原，之后完全离线可运行。`assets/three.module.js`（1.3MB）是渲染层唯一硬依赖，已直接入库，无需联网。

**素材缺失降级**：若未执行 `vendor-assets.sh`，`web-src/parts/` 在贴图 / 音频 / 头像加载失败时**不再 404 黑屏或弹出「请重启服务」**，而是降级为纯色材质 + 静音，并显示一条 `role="status"` 提示；OBS 采集的独立场景窗口（`?scene=1`）保持画面干净。

## 贡献与提交

```bash
git clone https://github.com/LocalForges/printcast.git
cd printcast
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test,desktop]"
bash scripts/vendor-assets.sh       # 还原二进制资源
python -m pytest                    # 135 项全绿（含 test_db / test_audit / test_server 子测试）
cd tests && node --test *.test.mjs  # 87/87 应当全绿（含 queue-policy / html-structure / settings-loader）
```

改了 Python 侧请跑 `python -m pytest`；改了采集层请跑 `tests/bridge.test.mjs`；**改展示端请改 `web-src/parts/` 或 `web-src/styles/`，再执行 `bash scripts/build-display.sh` 重建产物**，不要直接编辑 `web/app/`，也不要往 HTML 里塞内联脚本（`html-structure.test.mjs` 会拦下）。新增 Python 模块放 `src/printcast/`。

CI：`.github/workflows/ci.yml` 在每次 push / PR 时跑 `pytest`、`node --test`、展示端产物语法检查，以及 `build-studio.sh` + `build-display.sh` 的构建一致性校验；任一失败即阻断合并。未重建就提交的 `web/app/` / `web/studio-dist/` 产物差异会被 CI 抓到。

## 路线图

衍生方向落地计划见 [ROADMAP.md](ROADMAP.md)：AI 真实 3D 头像、多平台适配、云端 SaaS、电商闭环、观众数据中台、多机编排、硬件外设、合规本地化、测试产品化、虚拟主播联动。

## 许可

[MIT](LICENSE)。本仓库基于 [3d-printer-live](https://github.com/rhfbgfgfdg999999/3d-printer-live)（志哥AI 出品，MIT）重构：重排为分层结构、统一英文命名、修复画质档位口径与端口注释、清理死文件。
