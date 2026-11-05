# printcast 更新日志

> 直播内容驱动的 3D 头像打印台。本文件记录面向用户的重大变更；底层重构与测试进展见各版本说明。

---

## 纯净中文版 + 展示端前端工程化（2026-11-05 · dev 分支）

按「移除其余版本、开启前端工程化、彻底改版」一次收口，**架构边界不变**：控制台唯一写源、展示端只读、运行时零第三方依赖。

### 1. 只留一套中文展示端

- 删除英文三件套 `web/index-en.html` / `web/app.en.mjs` / `src/audio/gift-speech-en.mjs`。英文版是**陈旧分叉**（缺 HUD 字幕、缺 3 处 `data-bind`），删除不丢任何功能，服务端也无专门路由。
- 删除遗留页：`web/broadcast.html`（纯跳转壳）、`web/live.html`（永远停在「正在接入…」的竖屏空壳）、`site/cover-*.html` 三个零入链封面生成器，以及宣传页 `site/features.html` / `site/guide.html`。
- **保留** `web/live-view.html`：`desktop.py` 实际拉起的 WebRTC 投屏镜像窗口，是功能页不是语言版本。本轮重写了它：恢复必需的 `three` importmap、修 `resize_scene` 同步返回却调 `.catch` 的 TypeError、补 `aria-live` 与视频标签、让「镜像不可用」自救链接真正可见。
- 收口 `--room` 打开目标、`branding.links` 默认外链（宣传页下线后默认为空）、CLI 提示、桌面转发注释、文档与全部测试引用。

### 2. 前端工程化：源码分层 + 构建产物入库

- 新建 `web-src/`：`parts/` 按职责把 124KB 单文件切成运行时 / 三维场景 / 打印引擎 / 交互层四片；`core/` 放可独立 import 的真模块；`styles/` 放令牌、骨架、HUD、浅色主题四层 CSS。
- `vite.config.js` + `scripts/build-display.sh` 把源码构建为 `web/app/app.js`（Three.js 一并打包，离线自包含）与 `web/app/app.css`，**产物入库**，clone 后无需 npm 即可运行。`web/index.html` 保持 URL 契约不变，只引用产物。Vite 只在构建期使用，展示端不引入 Vue 等运行时框架。
- 构建脚本复用已安装的 Vite（根或 `studio/node_modules`），`web-src/` 与 `web/` 同级使 `../src/**`、`../assets/**` 相对 import 零改写。
- 删掉 `web/app.zh.mjs` / `web/app.css`；5 个原本靠切单文件字符串跑的测试改读按构建顺序拼合的分片源码，CI 增加 `node --check web/app/app.js` 与产物无漂移检查。

### 3. 页面与状态问题

- **队列有硬上限了**：新增 `web-src/core/queue-policy.js`（真 ES 模块，浏览器与 Node 共用），剧本出场入队前检查上限（40 件）与 `seq` 去重，避免 5 秒自动出场叠加 1× 打印速度时无限堆积卡死；`seen` 集合设上界，不再无界增长。
- **进度语义分开**：`describeAppearanceProgress()`（后端出场序列）与 `describePrintProgress()`（展示端打印百分比）不再混用；控制台大卡标题由「现在正在打印」改为「当前出场角色」，并注明打印进度以打印台画面为准。
- **浅色主题重写**：删掉 `app.css` 里互相打架的两套 `!important` 补丁与 `.print-hud` 死样式；新增令牌层，补齐 `.metric`（旧版深底深字不可读）、`.empty`、`.item b`、内联深色输入框等覆盖，合并断点并补 480px 小屏档。

回归：`pytest` 135 项全绿、`node --test` 87 项全绿（新增 `queue-policy.test.mjs`，重写 `html-structure.test.mjs`）。冒烟：入口与两端产物全部 200；已下线的 6 个页面全部 404。

> 说明：渲染引擎是命令式的 Three.js 每帧循环，分片之间共享一个模块作用域；纯逻辑与策略已抽为真模块并可独立测试。作用域进一步显式化需带 GPU 的逐段回归，留作下一阶段。

---

## 采集平台适配层 · 配置即时生效 · 控制台信息层重做（2026-11-05 晚）

三件事一起收口：**采集要为多平台做准备**、**改配置不用等**、**当前在打什么一眼能看到**。

### 1. 采集：适配器 + 通用推流口（平台无关的稳定边界）

- **事件契约 v1**（`src/collector/platforms/contract.mjs`）冻结为唯一边界：`{v, platform, source, type, name, avatar, text?, gift?, raw?, count?, ts}`；`type ∈ comment|gift|like|join|follow`。浏览器采集与外部推流都先归一化再进打印队列，下游只认契约不认平台。契约文档见 `docs/live-event-contract.md`。
- **平台注册表**（`platforms/index.mjs`）：内置 `douyin`（浏览器 CDP 采集，`needsBrowser/needsRoom=true`）与 `generic`（不驱动浏览器，等推流）；未知 id 回落默认平台，配置写错也不会让服务起不来。新增平台 = 加一个 adapter 模块 + 注册表登记一行 + 后端白名单加 id，**主流程不用改**。
- **通用推流入口 `POST /ingest`**（`src/server/bridge-server.mjs`）：按契约推事件即可接入 B 站 / 快手 / 视频号 / 自建弹幕源。传输层只做方法（405）、可选令牌（`PRINTCAST_INGEST_TOKEN` → 401）、体积（64KB → 413）、JSON（400）；单次最多 50 条，逐条回执 `accepted / rejected`。业务侧统一记账（花名册 / 分类计数 / 最后一帧时间），与浏览器采集口径一致。
- **`/health` 增补** `platform` 与 `stats`；`probe.bridge_status()` 透传，`/__api/status` 新增 `capture` 块（`platform / configured / demoFill / ingestUrl`）。
- **修掉一个老 bug**：采集器上报的 `identity` 是 `src/collector` 目录，探测端却拿**仓库根**比对，两者永不相等 → 控制台一直显示「数据桥未启动」，点启动必报「超时」（其实桥已起来）。现改为上报仓库根；`wait_bridge` 超时同时从 3s 放宽到 6s，避免慢机器误判。

### 2. 配置即时生效（不再等 5 秒）

- `relay.ALLOWED_TYPES` 新增 `settings-changed`；设置写成功（POST/PUT/DELETE `/__api/settings`，2xx）后由服务端广播一条**只含信号不含值**的消息，展示端收到即重读 `/__api/settings`，仍以 GET 为唯一权威来源。
- 展示端复用**既有 `/__scene-events` 长轮询**接收该信令，5s 轮询降为兜底；并改为**仅在页面可见时轮询**（OBS/投屏常驻后台不空转），切回前台立即补一次。
- 展示端设置统一走 `window.__PC`：`settings-loader.js` 新增 `reload()`（重新拉取并应用品牌/展示层），渲染模块不再各自 `fetch`，杜绝「双源」。

### 3. 控制台信息层重做（少点几下、少猜几次）

- **顶部状态条**：本机服务 / 采集（平台 + 最新事件多久前，点一下即可启停桥）/ 剧本播放（自动播放间隔或已暂停）/ 3D 打印（剧本是否接入打印）；平台与设置不一致时显示「平台待重启」，避免「改了没生效」的困惑。
- **当前打印主视觉**：头像真实渲染（加载失败回退首字），补上所属内容包、第 N 位、模式、进度（第 X / 共 Y 位、第几轮）、台词与标签。
- **「打这个」**：内容包抽屉里每个角色旁直接点名出场，把「回内容源面板 → 手输角色 ID → 点名」四步压成一次点击；未开播时按钮禁用并说明原因。
- **采集面板**：平台下拉（抖音 / 通用推流）；选通用推流时直接给出可复制的 `/ingest` 地址、curl 示例与字段说明；`live.demoFill`（无采集时用演示人物填充）就地可开关。
- 修掉展示端首帧 `settings` 为空导致的渲染报错（打印规则与采集面板加空态守卫），并把控制台抽屉的头像口径与展示端 `mediaUrl` 对齐（`*.svg → /avatars/`、raster → `/media/`），演示包头像在控制台也能看到。

回归：`pytest` **135 项全绿**（新增 `tests/test_settings_changed.py`）；`node --test` **87 项全绿**（新增 `tests/ingest.test.mjs` 覆盖契约归一化、平台注册表、`/ingest` 的 200/400/401/405/413）。冒烟：PUT 设置后订阅端立刻收到 `settings-changed`；`/__start-bridge?platform=generic` 返回 `ok:true` 且 identity 匹配；`POST /ingest` 两条合法 + 一条非法 → `accepted:2, rejected:["bad"]`；`/health` 统计 `comment=1, gift=1, roster=1`；`/__api/status.capture.ingestUrl` 为 `http://127.0.0.1:8765/ingest`。

---

## 控制台→打印台实时同步 · 剧本播放并入内容源 · 演示数据开箱即用（2026-11-05）

针对四条反馈（设置不同步、剧本播放独立菜单、直播无演示数据、操作不够直观）的一次收敛，全部遵循「控制台写 / 展示端只读 / 零第三方依赖」。

- **设置实时同步到打印台**：展示端（`web/app.zh.mjs`、`app.en.mjs`）原先只在加载时 `fetch('/__api/settings')` 一次，且自带一份写 `localStorage` 的规则编辑器，形成双源。现改为**每 5 秒轮询 `/__api/settings`** 并重应用 `printer.rules / autoDemo / demoGapMs / idleFill / idleSeconds`、`broadcast.scriptedPrint`、`live.*` 与品牌展示；删除打印台本地规则编辑与 localStorage 写入，控制台成为唯一可写源，改完约 5 秒内自动生效（含控制台内嵌的打印台预览），无需刷新页面。
- **「剧本播放」并入内容源**：删除导航里的独立「剧本播放」一级菜单与整页模板，其全部控件（内容包 / 策略 / 模式 / 循环 / seed / 开始·下一个·播放·暂停·点名·重置 / 状态行）并入「头像打印」页的内容源分段控件——选「剧本播放」即内联显示，选「实时直播」显示直播控制，消除重复入口与操作困惑。
- **演示数据开箱即用**：`samples.py` 新增内置「演示人物」内容包（24 位虚拟观众），并**生成彩色首字 SVG 头像**落到 `data/media/`；新增只读静态路由 `/avatars/<name>.svg`（路径穿越防护，`Content-Type: image/svg+xml`）服务这些头像——媒体系统的媒体 id 仅接受 12 位 hex 的 raster，SVG 不计上传校验，故单开此路由。`/__api/packs` 首屏即有 `demo-people`，头像真实可见。
- **启动自动种子 + 直播演示填充**：服务启动时幂等调用 `samples.seed_builtin_packs()`，全新库也立即有数据；新增 `live.demoFill`（默认开），未接真实采集时自动用演示人物出场；默认 `broadcast.defaultPacks` 切到 `demo-people`，开机即播即为演示头像。
- **易用性收尾**：「头像打印」页新增**「一键体验」**（选演示包→开播→打开打印台）；导航精简（运行=头像打印；资产=内容包/导入/图片；编排=排期预演；配置=设置/系统/日志）；系统/日志/设置里残留的「出场广播/广播」统一为「剧本播放/内容源」。

回归：pytest **126 项全绿**；Studio 重建通过（`index-BPdx3Nxu.js` / `index-DyPETmzK.css`，含「一键体验 / 演示人物 / 未接采集时用演示人物填充」）。冒烟：`/avatars/demo-0.svg` → 200 `image/svg+xml`、`/media/*.png` 不受影响、`/__api/settings` 默认 `defaultPacks=[demo-people]`、`autoStart=true`、`demoFill=true`，重启后自动播放 `demo-people`（`current=橘子汽水, avatar=demo-0.svg`）。

---

## 出场广播自动播放 + 开机即播（2026-11-05）

「画面不能播放」的根因是展示端只读、必须由控制台持续「推进下一个」才会动，而此前**没有任何自动推进机制**，且默认 `autoStart=false`，于是展示页一直停在「等待出场」。本轮补齐自动播放：

- **服务端定时器自动推进**：`BroadcastController` 新增 `play(intervalMs, loop)` / `pause()`，用守护 `Timer` 线程按间隔自动 `next()` 出场；序列结束按 `loop` 决定重置续播或停止。`_play_gen` 代次令牌避免暂停后滞留 tick 重新挂起播放。`playing` / `intervalMs` 写入 `runtime_state`，重启后自动续播。
- **端点**：`POST /__api/broadcast/play` 与 `/pause`（action 取自 URL 子路径或 body；间隔下限 200ms、上限 60s）。
- **开机即播**：`auto_start_broadcast` 在配置 `autoStart` + `defaultPacks` 时启动，并在 `autoPlay=true` 时直接自动播放（恢复的上次广播若未播也续播）。默认配置已设为 `autoStart/autoPlay=true`、`defaultPacks=[ming-emperors]`、间隔 5s、循环。
- **Studio 控制**：出场广播页新增「自动播放 / 暂停播放」按钮与「自动播放中 / 已暂停」状态。
- **注意**：设置以 SQLite 为唯一事实来源，`data/settings.json` 仅是镜像；改配置请走 `/__api/settings` 或 `settings.save_settings`，直接改 JSON 无效。

回归：`tests/test_broadcast_play.py` 4 项端到端测试全绿（启动不自动推进、`play` 持续推进、`pause` 停止、序列结束停播、非法间隔 400）。

---

## 数据落库 + 缺陷修复 + M2 资产降级 + CI（2026-11-05）

三项用户指令：**1. 修复已知问题；2. 数据落库；3. 原始测试数据落盘落库并跑通**。本轮在保持「控制台写 / 展示端只读」边界与零第三方依赖的前提下完成。

- **SQLite 数据落库**：新增 `src/printcast/db.py`（标准库 `sqlite3`，WAL，短连接 + 表级锁）。七张表 `packs/characters/media/settings/audit/runtime_state/meta`；首次启动幂等从旧版 JSON 迁移，之后**数据库为单一事实来源**，JSON 仅作为可比对 / 备份 / 分发镜像（每次写后尽力 `export_json`）。`storage.*` / `settings.*` / `audit.*` 的对外签名与返回形状不变，`/__api/*` 行为与 P1 完全一致。
  - **并发安全**：关键写用 `BEGIN IMMEDIATE` + 表级锁，消除读改写丢更新、非原子 trim、index 读改写 TOCTOU。
  - **广播进度持久化**：`runtime_state` 记录当前角色 / seq / seed / startedAt；`BroadcastController(restore=True)` 重启后完整恢复并继续正确推进（先前纯内存、重启即丢）。
  - **新增只读端点** `GET /__api/db`：暴露后端类型、各表行数、`PRAGMA integrity_check`，供工作台「系统」页展示。
- **修复确证缺陷**（审查 30 条后落地）：`_json` 单响应与 `OSError 41`（前序已修，本轮补回归）、`/__api/broadcast` 前缀误匹配导致 plan 被当成未知路径、畸形 JSON 广播体静默落库、字符串 seed 与 URL 整型 seed 不一致、`DELETE /__api/settings/anything` 误清空配置、`--schedule` CLI 用 `ap['index']` 崩溃、场景信令 `after` 类型、状态缓存线程安全等。广播状态恢复接上 `auto_start_broadcast`。
- **M2 资产缺失降级**：`web/app.zh.mjs` / `app.en.mjs` 在贴图 / 音频 / 头像加载失败时降级为纯色材质 + 静音，左下角显示 `role="status"` 提示（列出缺失类别 + 还原命令），不再 404 黑屏或弹出「请重启服务」；OBS 场景窗口保持干净。
- **CLI 与可见性**：`--db info/export/verify` 三个子命令；`--seed --overwrite` 改走数据库并同步落盘 JSON。
- **CI 骨架**：新增 `.github/workflows/ci.yml`，push / PR 时跑 pytest + `node --test` + Studio 构建校验，任一失败即阻断。
- **原始测试数据落盘落库跑通**：内置 5 个示例包（明朝十六帝 + 三国 / 水浒 / 红楼 / 西游，共 58 位人物）连同默认设置、媒体索引写入 `data/printcast.db` 并导出 `data/packs/*.json`；隔离临时数据目录的端到端冒烟验证 11 个 URL 全 200、同 seed 两次序列一致、广播 start/next 产生 `view-appearance`、畸形体 400 不误推进、日志可按动作 / 关键词 / 失败筛选、服务重启后进度 / 当前角色 / seed / startedAt 完整恢复、服务端异常 0。

回归：pytest **127 项全绿**（新增 `test_db.py`，扩充 `test_audit` / `test_server` / `test_scene_relay` 覆盖落库与重启恢复）、node **75/75**（新增 `studio-api.test.mjs` 锁死前端请求契约）、Studio 构建通过（139 KB js / 15 KB css，产物已重构建入库）；`data/printcast.db`、`data/settings.json`、`data/audit.jsonl` 已加入 `.gitignore`，不入库。

---

## 工作台内容真正可管理（P1，2026-11-04）

P0 把工作台变成了中控台，P1 解决的是「内容不可管理」：以前内容包只能列 ID 与删除，序列只是一串文字列表，设置改完要手动开新窗口验证。本次全部补齐，且**展示端一行未改**。

- **内容包抽屉**：列表支持搜索与按标题 / ID / 人数 / 更新时间排序；点标题打开右侧抽屉查看人物表（头像、名称、ID、顺序、权重、标签、台词），可编辑、增删人物、上下调序、从已上传图片里选头像。保存走 `POST /__api/packs` 逐字段校验，错误按行列在抽屉里；改 ID 会明确提示「另存为新包，原包保留」。另可复制成新包、导出 JSON、从 JSON 导入（走 `/__api/import?commit=1`）。
  - 数据契约护栏：抽屉把 schema 规范化出的 `tags` 数组还原成分号串后再提交，避免 M0 修过的「数组被 stringify 成脏标签」回归（`tests/test_pack_roundtrip.py`）。
- **出场序列时间轴**：`/__api/schedule` 的出场序列渲染成可点击的卡片带（头像、台词、包、权重、循环轮次），支持固定 `seed` 复现、复制完整复现链接、逐位本地预演（**仅工作台内高亮，不触发真实广播与打印**）、「按此配置开播」把同一 seed 交给广播控制器。后端回显 `seed` / `count`、`count` 上限 300、`state()` 回显 `seed` 以便核对；纯数字 seed 在前端统一收口，规避 `Random('123')` 与 `Random(123)` 不一致。
- **设置页实时预览**：右侧嵌真实展示页的缩放 iframe（广播页 / 3D 打印台 / 直播小窗，40%–65%），保存设置后自动刷新、可手动刷新或暂停。iframe 自己 `GET /__api/settings`，控制台**不注入草稿配置**，边界不变。
- **本机操作日志**：新增 `src/printcast/audit.py` + `GET/DELETE /__api/audit`，服务端统一埋点覆盖设置、内容包、图片、广播、数据桥、窗口控制，失败动作同样留痕；工作台第 9 个视图支持按动作 / 关键词 / 失败筛选与全量统计。日志是 JSON Lines、500 条上限、字段截断、不记请求体，清空后仍保留一条 `audit.clear`。展示端高频信令不记录。
- **边界不变**：控制台写、展示端只读；日志由服务端记录而非浏览器上报；预演不伪造后端状态；没有引入 UI 框架或新增 npm 依赖（产物 136 KB js / 15 KB css）。

回归：pytest 106 项 + 5 subtests 全绿（新增 `test_audit.py` / `test_pack_roundtrip.py`，扩充 `test_server.py` 端到端埋点）、node 72/72（新增 `studio-api.test.mjs` 锁死前端请求契约）、Studio 构建通过；隔离临时数据目录的端到端冒烟确认 9 个 URL 全 200（含 iframe 预览参数）、固定 seed 两次序列完全一致、`state.seed` 回显、广播 `next` 产生 `view-appearance`、日志查询与清空留痕、服务端异常 0。

---

## 工作台升级为直播中控台（2026-11-04）

此前 `/studio/` 是 7 个表单区块平铺的长滚动页，最常用操作排在最底部，且后端已实现的控制端点一个都没接。本次按「总览优先、状态可见、单屏可干预」重做：

- **信息架构**：从单列长页改为「顶栏状态灯 + 左侧分组导航 + 主工作区多视图」，8 个视图按运行 / 资产 / 编排 / 配置分组；默认打开总览。原有内容包、模板、导入、图片、排期、设置、广播功能全部保留。
- **总览仪表盘**：「现在正在打印」大卡（角色 / 包 / 进度 / 运行时长）、三灯状态、4 张指标卡、实时事件流、运行链路诊断、主操作区。事件流订阅 `/__scene-events` 长轮询，把 M1「出场即打印」链路变成可见的，不用再靠猜。
- **状态单一来源**：新增 `GET /__api/status` 聚合服务 / 数据桥 / 广播 / 资产计数，2 秒轮询；`BroadcastController` 记录 `startedAt`。只暴露后端真实持有的状态——打印队列长度属于展示端内存，不臆造、也不让展示端反向汇报，边界不变。
- **接上此前闲置的后端能力**：数据桥启停、拉起 3D 打印台 / 直播小窗窗口，现在都能从控制台一键完成。
- **设置区**：分组折叠、脏标记「有未保存的修改」、恢复出厂设置（新增 `DELETE /__api/settings`）、颜色选择器、开关化布尔、保存后一键打开对应展示页验证。
- **交互与视觉**：删除 / 重置改为内联二次确认，去掉原生 `confirm()`；深色优先 + 可切换浅色，统一设计 token、状态语义色、等宽数字。工作台主题是自身偏好，不污染展示端主题。
- **零新增依赖**：产物仍为 Vue 3 单文件 + 原生 CSS（108 KB js / 10 KB css），未引入任何 UI 框架。

回归：pytest 92 + 5 subtests、node 66/66、Studio 构建通过；端到端冒烟确认 `/__api/status` 形状正确、广播 start/next 产生 `view-appearance` 事件、单响应无叠加 404、9 个页面与产物 200、服务端异常计数 0。

---

## 稳定性修复（2026-11-04 晚）

针对实测反馈「工作台连接受阻 / `/__scene-events` 刷 404 / 内容包读不到」：

- **双响应根因**：`server.py::_json()` 没有返回值，`do_GET` 的路由循环因此判断失效——自定义端点发完响应后仍掉进静态文件回退，再叠一个 404，污染浏览器连接并持续抛 `OSError: [Errno 41] Protocol wrong type for socket`。现返回哨兵值，并给 `send_error` 加了写失败兜底。
- **本机鉴权过严**：Host 白名单从仅 `127.0.0.1` 扩到 `127.0.0.1` / `localhost` / `::1`；`Sec-Fetch-Site` 缺失时不再一律拒绝（Safari 等非 Chromium 浏览器不发该头）。跨站 `cross-site` 与外部 Host 仍拒绝。此前用 `localhost` 打开工作台会让所有 `/__api/*` 返回 403，表现为内容包列表空、工作台连不上。
- **工作台开箱即用**：`web/studio-dist/` 构建产物（约 96 KB）纳入版本库，全新 clone 后 `/studio/` 无需先跑 `bash scripts/build-studio.sh`；产物缺失时服务端返回带构建指引与后端连通检测的引导页，而不是裸 404。
- **工作台重做视觉与连接状态**：浅/深色双主题、分区导航、统一表单与表格；顶部显示后端地址、连通结果与失败原因（含 403 的具体提示）；内容包读取失败时明确提示「内置示例包仍在 `data/packs/`，并未被删除」。
- **页脚链接**：`settings-loader.js` 对含 `[data-links]` 的容器不再整块 `textContent` 覆盖；`index.html` / `index-en.html` 把页脚文案与链接宿主拆成兄弟节点。
- 回归：pytest 89 + 5 subtests、node 66/66、Studio 构建通过；端到端冒烟覆盖 localhost、无 `Sec-Fetch-Site`、`/__scene-events` 单响应，服务端异常计数 0。

---

## 当前版本：控制台 / 展示端分离架构（本里程碑）

本次收口重构，明确了**控制台（后端）** 与**展示端（前端）** 的边界，并把所有展示内容改为由控制台参数化驱动。

### 控制台（Studio + 本地 API）——唯一的配置与状态来源
- 新增 `settings.py` 与 `/__api/settings`（GET 读 / PUT 写），集中管理：品牌名、标语、强调色、页脚链接、主题、叠加文案、演示徽标、公告条、打印规则、出场广播策略、直播参数等。
- 工作台（Studio，Vue 构建产物挂在 `/studio`）升级为真正的控制台：
  - 第 6 区：可视化编辑全部控制台设置并即时保存（含页脚链接增删、主题、公告条）；
  - 第 7 区：出场广播控制台（选择内容包、策略、模式、循环、启停、手动触发、重置），未开播时表单初值来自控制台默认参数。
- 配置写入采用**原子写 + 深合并 + 输入净化**（颜色正则、链接协议白名单拒绝 `javascript:` / `data:`、布尔与数值收口、未知分区剔除），避免脏写与注入。
- **每一项设置都有真实消费方**，杜绝「控制台里有开关、展示端却没读」的假参数化：`broadcast.autoStart` 由服务启动时的 `auto_start_broadcast()` 执行；`printer.*` 由两个渲染模块应用；`display.*` / `branding.*` / `live.*` 由 `settings-loader.js` 渲染。
- 修复 `/__api/settings` 返回 `{ok, settings}` 但渲染端误用整个响应体的 bug（此前 `printer.rules` 与 `broadcast.scriptedPrint` 实际未生效）。

### 展示端——只读取、只渲染
- `web/index.html` / `index-en.html` / `broadcast.html` / `live-view.html` 不再内嵌任何硬编码品牌、广告条或联系方式。
- `web/settings-loader.js` 是展示端**唯一配置入口**：只发一次 GET，渲染品牌、页脚链接、强调色、主题、演示徽标、公告条与直播间号默认值；两个渲染模块经 `window.__PC.ready` 复用同一份设置。
- `broadcast.html` 改为**只读出场卡片**：移除内容包 / 策略 / 开始 / 下一个 / 点名 / 重置等全部控制 UI，控制命令统一归控制台；渲染主页的打印规则面板在控制台生效后转为只读。
- 旧版硬编码广告条由控制台的 `display.showAnnounce` + `announceText` + `branding.links` 取代（默认关闭）；`display.showDemoBadge` 控制演示徽标，开箱即无第三方水印。

### M0 收口（数据 + 残留清理）
- 修复内置内容包标签字段在 `samples.py` 中被错误 stringify 成 `['['开国'', "'帝王']"]` 的脏数据根因（改为传入原始 `;` 分隔字符串，由 schema 归一化）。
- `python -m printcast --seed` 新增 `--overwrite` 开关，可覆盖已存在的内容包重新播种。
- 删除仓库残留文件：根目录 `.probe`、一次性脚本 `extract-original-icons.py`、第三方 `wx-copy.js` 及其对应的广告条 CSS。
- 重写 `release-notes.md`（即本文件），去除上游旧名称与第三方署名。

### M1 打通「讲到谁就打谁」
- 渲染端（`web/app.zh.mjs`）接入 `/__scene-events` 长轮询，监听 `view-appearance` 出场广播事件。
- 收到出场事件后按 `printer.rules` 推入 3D 打印队列（大图、剧本来源标记），并在开启语音时播报，受 `broadcast.scriptedPrint` 与 `printAllowed()` 双重门控。

### 静态页面全面替换
- `site/features.html`、`site/guide.html` 中的第三方广告条、平铺 SVG 水印、角标水印、微信号与 `wx-copy.js` 全部移除，仅保留 printcast 自有品牌与开源声明。
- `cover-gen.html` / `cover-tk.html` / `cover-yt.html` 封面生成器保持 printcast 自有品牌。

---

### M2 头像打印整合：统一门面，去掉「不搭边的玩意」
- **根因**：控制台以「出场广播」为主角，真正的「头像打印」（3D 打印机 + 打印规则 + 直播连接）没有一级入口，打印规则被塞进设置折叠组；`broadcast.html` 是与打印台平行的另一张扁平卡片页，与「讲到谁就打谁」脱节。
- **控制台以「头像打印」为门面**：原「总览」视图重命名为 **头像打印** 并作为默认首页；把打印规则从「控制台设置」整体搬入该视图（实时调整 + 保存）；新增 **内容源切换**（实时直播 / 剧本播放），直播模式可直接启停数据桥、打开抓取窗口。
- **出场广播并入「剧本播放」**：原「出场广播」视图改名为 **剧本播放**，作为头像打印的内容源之一；所有指向 `/web/broadcast.html` 的链接改为 `/web/index.html`（统一头像打印台）。
- **展示页统一**：`broadcast.html` 不再作为独立卡片页，改为 **301 客户端跳转**到统一的 3D 打印台（`index.html`），保留 `?scene=1` 等查询参数；出场姓名 / 台词 / 标签 / 来源作为 **HUD 字幕**叠在打印台上，直播与剧本共用同一画面。
- **头像可见性止血**：`app.zh.mjs` 的 3D 头像贴图加载失败时，从「静默白板」改为 **回退到首字徽章**（`fallbackAvatar`）并记入缺失资源提示；结果缩略图同样加 `onerror` 兜底。内置人物头像留空时即走首字徽章路径，开机即播不再出现白板。
- **术语对齐**：UI 文案中「出场广播」统一改为「剧本播放 / 内容源」；后端 `settings` 分区（printer / broadcast / live）保持不变，仅调 UI 层级与术语，降回归风险。

---

## 历史重大版本

### v2.0.0 直播功能大版本
- **头像抓取**：实时评论 100% 带头像——协议级解码修复（信封误杀 / 昵称张冠李戴 / 事件广播未定义），活跃榜单帧批量入库，头像持久缓存，资料卡补取强化（冷却 4 秒、全页查找、多批重试）。
- **打印规则面板**：评论 / 进场 / 点赞 / 关注 / 礼物是否打印、礼物语音、进场欢迎、30 秒无互动补位共 8 个开关，设置分组化、自动记忆。
- **中英双语**：`index-en.html` 独立英文版 + 英文语音播报，页头一键切换。
- **直播专用小窗（OBS 采集）**：纯 3D 画面应用窗口、可交互镜像、横屏/竖屏 × 720P/1080P 四档、多窗口选举不重复打印。
- **画质五档预设**：极速低配 / 标准 / 2×精细 / 4×超清 / 8×影院。
- **浏览器全功能模式**：开播全流程（开直播窗 / 开始抓取 / 停止抓取）由本地服务直拉，带同源安全防护。
- **稳定性**：数据桥自动跟随直播间切换、修复僵尸进程 / 断线重连崩溃 / 场景模式失效；自动化测试通过。

---

## 运行与下载
- 本地一键：`bash scripts/start.sh`（自动建虚拟环境、装依赖、开浏览器）。
- Windows 双击 `start.bat`；需要真实直播数据时另装 Node.js（LTS）。
- 桌面窗口版（WebView2，仅 Windows 需要）：`pip install -e ".[desktop]"`。
- 控制台：打开 `/studio`（默认进入「头像打印」页）；展示端：打开 `/web/index.html`（头像打印台，原 `/web/broadcast.html` 已并入并跳转至此）。
