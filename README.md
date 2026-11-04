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

项目已按正式 Python 结构组织（虚拟环境 + `pyproject.toml` + 可安装包 + 命令行入口）。

```bash
# 1) 还原大体积二进制资源（音频/贴图/截图，约 33MB，未随 git 提交）
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
| `printcast --seed [--overwrite]` | 把内置示例内容包（明朝十六帝 + 三国/水浒/红楼/西游）写入 `data/packs` 后退出；加 `--overwrite` 可覆盖已存在的同名包重新播种 |
| `printcast --schedule [PACK...]` | 预览指定内容包的出场顺序后退出（不跟包名则列出全部可用包）；可配合 `--mode`/`--strategy`/`--count` |

环境变量（不引入 dotenv 依赖，直接 `export` 即可）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `PRINTCAST_PORT` | `8080` | HTTP 服务首选端口 |
| `PRINTCAST_LIVE_DEBUG_PORT` | `9224` | 直播窗口的 CDP 调试端口 |

### 旧命令兼容

`python src/desktop/desktop_launcher.py --server-only` 与 `from desktop_launcher import ...` **继续可用**：
`src/desktop/` 下两个文件已改为薄转发到 `printcast` 包，保证旧 bat 脚本、`site/guide.html` 与外部引用不失效。新代码请统一用 `python -m printcast` / `from printcast.xxx import ...`。

### macOS 注意

- **不要用 Safari 调试**：页面依赖 WebGL2 与 `importmap`，Safari 13（10.15 自带）都不支持。请用 Chrome / Edge / Chromium 打开。
- **`--app` 独立窗口需要 Chromium 系浏览器**：脚本会自动在 `/Applications` 下按 Chrome → Chromium → Edge → Brave 顺序查找；都没有时「独立场景窗口」不可用（其余功能正常）。
- 窗口后端自动切换：macOS 用 `cocoa`，Windows 用 `edgechromium`。
- 若终端一直没有任何输出，用 `python -V` 和 `which python` 确认解释器是否指向 `.venv/bin/python`。


> **为什么必须走 HTTP**：`web/app.zh.mjs` 用原生 ES modules 加载 `../src/**/*.mjs` 与 `importmap`，`file://` 协议会被 CORS 拦死。

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
│   ├── audio/        语音层   printer-audio.mjs  gift-speech.mjs  gift-speech-en.mjs
│   └── desktop/      兼容层   desktop_launcher.py  scene_relay.py（薄转发，勿写新代码）
├── web/              运行页面
│   ├── index.html / index-en.html   DOM 骨架（各约 3KB）
│   ├── app.css                      共用样式（中英完全一致）
│   ├── app.zh.mjs / app.en.mjs      全部交互逻辑（打印队列、Three.js 场景、WebRTC 选主、语音）
│   └── live-view.html / live.html   独立场景窗口 / 竖屏直播画面
├── site/             宣传页    features.html  guide.html  cover-*.html
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
| `src/printcast/{schema,storage,importer,templates,api}.py` | **数据层**：领域模型（单一事实来源）、JSON 原子写、CSV/JSON 导入校验、模板生成、REST 分发 | → `config` |
| `src/printcast/{scheduler,samples,broadcast}.py` | **出场调度层**：顺序引擎（三模式 + 多包组合、seed 可复现）、内置示例包、经 SceneRelay 实时广播 | → `schema`/`relay` |
| `desktop/`（旧） | 两个薄转发模块，仅为兼容旧 bat / guide / 外部引用 | → `printcast` |

> 命名原则：采集层不绑定平台（不叫 douyin-*，为多平台适配铺路）；JS 用 kebab-case、Python 用 snake_case；文件名即职责。

**数据层是真正的业务逻辑，但不是前后端分离**：内容包 CRUD、导入校验、图片上传集中在 `src/printcast/` 的 `schema/storage/api` 一组纯模块里，通过 `/__api/*` 暴露给工作台页面。渲染主页面（111KB 的 WebGL/队列/信令逻辑）仍然独立、不进构建链——我们没有为了「架构好看」就给整站套上 HTTP 框架，只在真正需要 CRUD 的地方加了薄薄一层同域 API。真正的实时边界依旧是 WebSocket（`ws://127.0.0.1:8765`，Node 采集层 ↔ 浏览器渲染层）。

### 控制台与展示端的边界（本里程碑明确）

- **控制台 = 唯一的配置与状态来源**：`/studio`（Vue 工作台）与本地 Python API（`api.py` + `settings.py`）负责写一切——内容包、出场广播、打印规则、品牌与展示文案。展示端**绝不直接写配置**。
- **展示端只读取、只渲染**：`web/settings-loader.js` 是展示端唯一的配置入口，只发一次 `GET /__api/settings`（返回 `{ok, settings}`，必须取 `settings` 本体），渲染品牌名、标语、页脚链接、强调色、主题、`演示模式` 徽标、公告条与直播间号默认值；渲染主页（`app.zh.mjs` / `app.en.mjs`）经 `window.__PC.ready` 复用同一份设置，不再各自 fetch。
- **控制命令只在控制台**：`broadcast.html` 已改为**只读出场卡片**（仅 GET 状态与订阅 `/__scene-events`），开始 / 下一个 / 点名 / 重置全部移到 `/studio` 的广播控制区；渲染主页的打印规则面板在控制台设置生效后转为**只读**并指向 `/studio`。
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
- **鉴权**：所有 `/__api/*` 与 `/__` 本机端点仅接受 Host 为 `127.0.0.1:<port>` 且 `Sec-Fetch-Site: same-origin` 的请求，防止外部站点借本地服务读写数据或拉起进程；`/__health` 除外（仅供存活探测）。
- **静态页面全面参数化**：原先内嵌在 HTML 里的品牌名、广告条、联系方式、强调色已全部移除；`site/` 宣传页亦清除第三方署名与水印，仅保留 printcast 自有品牌。旧版硬编码广告条由控制台的 `display.showAnnounce` + `announceText` + `branding.links` 取代（默认关闭，无任何硬编码内容）。
- **回归护栏**：`tests/settings-loader.test.mjs` 用最小 DOM 桩在 Node 里跑真实装载器，锁死「只 GET / 取 settings 本体 / 展示端不写配置」；`tests/test_settings.py` 覆盖布尔与数值收口、危险协议拒绝、未知分区剔除与 autoStart。

**Python 包内部的依赖方向**：`cli → desktop/server/api → probe/relay → config`。`config` 不依赖任何兄弟模块；`desktop.py` 是唯一 import `webview` 的文件，所以 `--server-only` 不装桌面依赖也能启动；`api.py` 是纯函数分发层，`tests/test_api.py` 可直接调 `api.dispatch()` 而不起 HTTP 服务。

## 前端结构（HTML / CSS / ES 模块）

`web/index.html` 原本是 120KB 单文件（108KB 内联 `<script>` + 82 个函数）。现已彻底拆开：

| 文件 | 内容 | 体积 |
|---|---|---|
| `index.html` / `index-en.html` | 纯 DOM 骨架 + `importmap` + 两个引用 | 3.2 / 3.9 KB |
| `app.css` | 中英共用样式（两份原本字节相同） | 5.7 KB |
| `app.zh.mjs` / `app.en.mjs` | 全部交互逻辑 | 111 / 114 KB |

拆分依据：`<script type="module">` 内联时相对 import 基于 **HTML 所在目录**，抽到同目录的 `.mjs` 后基于**模块所在目录** —— 两者都是 `web/`，所以 `../src/**/*.mjs` 一条都不用改。`importmap`（`"three": "../assets/three.module.js"`）必须留在 HTML 里，因为它按 HTML 位置解析。执行时机同为 deferred，DOM 就绪后运行，行为不变。

> **为什么没有拆得更细**：这 82 个函数共享几十个模块级变量（场景对象、打印队列、WebRTC 连接），继续切成多个内聚模块需要把状态显式提到共享模块并逐段做 GPU 回归。当前这一步做到了「HTML 只留 DOM、CSS 与逻辑全部外置、零回归」，是可以在无 GPU 环境里安全验证的最大步。`tests/html-structure.test.mjs` 会阻止有人把内联脚本贴回去。

中英两份逻辑目前仍是独立文件（差异约 15%，主要是文案与 TTS），合并为「单一模块 + i18n 字典」是下一步，见 [ROADMAP.md](ROADMAP.md)。

## 运行机制

打开后自动加载测试头像，逐层打印、出分、转运到前方横向传送带，前后流水并行。暂停同时冻结打印和流水线；跳过只丢弃当前打印中的物品。

**空闲补位**：连续 30 秒没有任何观众消息会自动补一张测试头像（之后每 30 秒最多一张、队列最多预留 2 张），真实消息一到立刻让位。

**镜头**：可拖动视角检查模型，随时「＋保存当前视角」（最多 10 个命名镜头），随手拖动的视角与上次所用镜头都会自动记忆，刷新回到上次机位。

**画质五档**：极速低配（关反射/阴影/扫光，集显流畅）/ 标准 / 2×精细 / 4×超清 / 影院级 2×（内部渲染 2×，叠加 SSAA 抗锯齿约 4×，反射与阴影贴图同步升档）。选择自动记忆。

**后台推进**：页面隐藏时打印由后台时钟继续推进，切回来自动恢复渲染。

## 数据工作台（内容包 / 导入 / 上传）

除了「实时直播驱动」，printcast 还支持**预先编排内容**——这正是「按内容包顺序播放指定人物（明朝十六帝、故事人物出场表）」的实现载体。打开 `http://127.0.0.1:8080/studio/`（服务启动后自动可用）即可使用，全程本机运行、不上传云端。

| 功能 | 说明 |
|---|---|
| 内容包管理 | 列出 / 删除内容包；一个内容包 = 一组有序人物（如 16 位皇帝），由规则层按 `mode` 调度 |
| 模板下载 | 下载 CSV / JSON 模板，字段与系统完全一致，Excel 双击不乱码（带 BOM） |
| 数据导入 | 粘贴或上传 CSV，逐行校验、**绝不静默丢行**；错误会标注到具体行，一次改完再提交 |
| 图片上传 | 头像图片直接上传（PNG/JPEG/WebP，魔数+扩展名+大小三重校验），供内容包引用 |

**为什么引入构建链**：工作台是唯一用上框架的页面——表格、表单校验、上传进度、错误列表正好是声明式 UI 的强项。它走独立的 **Vue 3 + Vite** 工程（`studio/`），产物落在 `web/studio-dist/`，由主服务以 `/studio/` 前缀托管；**主渲染页（`web/index.html`，111KB 原生 ES modules）不进构建链**，保持「核心零 npm 依赖、离线可跑」。

```bash
# 工作台开发（热更新）：先起主服务，再起 dev server（:5174 会把 /__api 代理到主服务）
python -m printcast --server-only
cd studio && npm install && npm run dev

# 重新构建生产产物（一键：安装依赖 + vite build，产物落到 web/studio-dist/）
bash scripts/build-studio.sh
```

> `web/studio-dist/` 是构建产物、不入库，首次拉取后跑一次 `bash scripts/build-studio.sh` 即可；改了 `studio/` 源码后再跑一次。主渲染页与 Python 侧无需此步。

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

- **工作台预览**：`/studio/` 新增「出场顺序预览」区块，选内容包 + 模式 + 策略，实时拉 `GET /__api/schedule` 查看计划列表。

- **实时出场卡片**：打开 `/broadcast.html` 充当「当前出场」显示面板，经 `SceneRelay` 的 `view-appearance` 消息实时刷新（角色名 / 头像 / 播报）；底部控制条可「开始 / 下一个 / 触发事件 / 重置」，支持循环。

- **HTTP 端点**：

  | 端点 | 说明 |
  |---|---|
  | `GET /__api/schedule?pack=ming-emperors&mode=sequence&strategy=concat&count=8` | 纯函数计划预览（无状态），返回出场顺序与元数据 |
  | `POST /__api/broadcast` | 有状态控制：`{action: start\|next\|trigger\|reset, packs, mode, strategy, seed, charId, loop}`，把「下一个出场角色」经 `view-appearance` 广播给所有订阅 `/__scene-events` 的客户端 |
  | `GET /__api/settings` | 读取全部控制台设置（branding / display / printer / broadcast / live），展示端只读此端点 |
  | `PUT /__api/settings` | 以深合并方式写入设置并即时持久化（原子写 + 输入净化）；仅控制台（Studio）调用，展示端不写 |

> 扩展更多人物零代码：在 `/studio/` 导入自定义内容包，或在 `data/packs/` 直接放 JSON，调度引擎会按 `order`/`weight`/`trigger` 自动驱动。`/broadcast.html` 与渲染主页共享同一 `SceneRelay` 通道，可作为 OBS 第二屏或主控大屏。

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
python -m pytest                          # 81 个用例（76 主用例 + 5 子测试）：数据层 / 信令 / 出场调度 / 广播 / HTTP 端点 / 兼容转发
cd tests && node --test *.test.mjs        # 57 个 node:test 用例（含前端结构防回退）
```

覆盖分层：

| 测试 | 验证内容 |
|---|---|
| `test_api.py` | 数据层全链路：schema 驱动、内容包 CRUD、模板生成、CSV/JSON 导入逐行校验、图片上传（魔数校验 + 中文名保留）、路径穿越防护 |
| `test_server.py` | 静态资源、no-store 头、文档根、`/__` 端点鉴权、存活探针、端口复用、信令 publish→poll、非法路径拦截、**API 经 GET 路由到 api 层** |
| `test_compat.py` | 旧 `desktop_launcher` / `scene_relay` 薄转发仍指向同一实现 |
| `test_scene_relay.py` | 有界信令：隔离客户端、不重放旧 offer |
| `test_scheduler.py` | 出场调度引擎：三模式（sequence/weighted/trigger）、多包组合（concat/interleave/merged）、seed 可复现、进度/历史/循环 |
| `test_broadcast.py` | 广播控制器经 `SceneRelay` 发布 `view-appearance`、HTTP `/__api/broadcast` 端到端（开始/下一个/触发/重置） |
| `html-structure.test.mjs` | HTML 不含内联 style/script、引用可解析、模块 import 全命中、importmap 齐全 |
| `tests/*.test.mjs` | 采集层 protobuf 解码、打印队列、画质预算、语音文案、礼物抢占 |
| `test_native_output.py` | GPU + WebView 端到端检查，**手动运行**（`python tests/test_native_output.py`），不参与 pytest 收集 |

## 首次拉取说明

大体积二进制（音频 wav / 背景贴图 png / 文档截图，约 33MB）未随 git 提交，执行一次 `bash scripts/vendor-assets.sh` 即可从上游按原相对路径还原，之后完全离线可运行。`assets/three.module.js`（1.3MB）是渲染层唯一硬依赖，已直接入库，无需联网。

## 贡献与提交

```bash
git clone https://github.com/LocalForges/printcast.git
cd printcast
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test,desktop]"
bash scripts/vendor-assets.sh       # 还原二进制资源
python -m pytest                    # 81/81 应当全绿（76 主用例 + 5 子测试）
cd tests && node --test *.test.mjs  # 57/57 应当全绿
```

改了 Python 侧请跑 `python -m pytest`；改了采集层请务必跑 `tests/bridge.test.mjs`（覆盖 protobuf 信封识别、头像归属、点赞限流）；**改页面逻辑请改 `web/app.zh.mjs` 与 `web/app.en.mjs`，不要往 HTML 里塞内联脚本**（`html-structure.test.mjs` 会拦下）；改完起本地 HTTP 服务用浏览器打开 `/web/index.html` 看控制台。新增 Python 模块放 `src/printcast/`，不要写回 `src/desktop/`。

## 路线图

衍生方向落地计划见 [ROADMAP.md](ROADMAP.md)：AI 真实 3D 头像、多平台适配、云端 SaaS、电商闭环、观众数据中台、多机编排、硬件外设、合规本地化、测试产品化、虚拟主播联动。

## 许可

[MIT](LICENSE)。本仓库基于 [3d-printer-live](https://github.com/rhfbgfgfdg999999/3d-printer-live)（志哥AI 出品，MIT）重构：重排为分层结构、统一英文命名、修复画质档位口径与端口注释、清理死文件。
