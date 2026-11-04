# printcast 更新日志

> 直播内容驱动的 3D 头像打印台。本文件记录面向用户的重大变更；底层重构与测试进展见各版本说明。

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
- 控制台：打开 `/studio`；展示端：打开 `/web/index.html`（或 `/web/broadcast.html` 出场广播页）。
