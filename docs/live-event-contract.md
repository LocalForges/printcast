# 直播事件契约 v1（平台扩展入口）

采集层与展示层之间只有这一份契约。**任何平台**只要能产出符合本契约的事件，就能接入本项目，
无需改动本仓库的 Python 侧或渲染侧。

## 1. 传输方式（两种，二选一）

| 方式 | 适用 | 入口 |
| --- | --- | --- |
| 浏览器采集 | 抖音（本仓库内置） | 采集器驱动本机浏览器读取直播间页面，内部产出事件 |
| HTTP 推流 | B 站 / 快手 / 视频号 / 自建弹幕源 | `POST http://127.0.0.1:8765/ingest` |

推流模式下把控制台「直播」里的平台切到 **通用推流**，数据桥不再驱动浏览器，只等推流。

## 2. 事件字段

```jsonc
{
  "v": 1,                       // 契约版本，缺省按 1 处理
  "platform": "generic",        // 平台 id：douyin | generic | 未来新增
  "source": "ingest",          // ingest | browser（服务端按入口自动填）
  "type": "comment",            // comment | gift | like | join | follow
  "name": "小明",               // 必填，1–24 字符；控制字符会被剔除
  "avatar": "https://…/a.jpg",  // 可选，仅接受 http(s) 绝对地址，否则丢弃走首字徽章
  "text": "打印我",             // type=comment 必填，≤200 字符
  "gift": "beer",               // type=gift：beer | lollipop | heart | other
  "raw": "大啤酒",              // type=gift：原始礼物名，≤40 字符
  "count": 2,                   // type=gift/like：1–999，越界收口
  "ts": 1762318000000           // 可选，毫秒时间戳；缺省取服务端当前时间
}
```

单条、数组或 `{"events": [...]}` 三种请求体都支持；单次最多 50 条。

## 3. 一个最小接入脚本

```bash
curl -s http://127.0.0.1:8765/ingest \
  -H 'content-type: application/json' \
  -d '{"type":"comment","name":"小明","text":"打印我","avatar":"https://example.com/a.jpg"}'
# → {"ok":true,"accepted":1,"rejected":[]}
```

若设置了环境变量 `PRINTCAST_INGEST_TOKEN`，必须额外带 `-H 'x-ingest-token: <令牌>'`，
否则返回 401。服务只监听 `127.0.0.1`，令牌用于同机多用户场景。

## 4. 常见回执

| 状态 | 含义 |
| --- | --- |
| 200 `accepted>0` | 已进入打印通道 |
| 200 `rejected:[…]` | 该条非法（类型未知 / 缺 name / 评论缺 text），其余照收 |
| 400 | JSON 解析失败 |
| 401 | 令牌不匹配 |
| 405 | 非 POST |
| 413 | 请求体超过 64 KB |

## 5. 新增一个平台（两种粒度）

**A. 只推流（推荐，零改代码）**：写个脚本把平台事件映射成上面的字段，POST 到 `/ingest`。

**B. 内置适配器**：在 `src/collector/platforms/` 加一个模块，导出
`{ id, label, needsBrowser, needsRoom, supportsIngest, parseRoom, roomUrl, describe }`，
然后在 `platforms/index.mjs` 的 `REGISTRY` 登记一行，并在 `settings.py` 的
`_sanitize_settings` 平台白名单里加上该 id。上层（采集主流程、控制台）不需要改。

## 6. 边界与约束

- 展示端**只读**：事件只能经数据桥进入，渲染页不写任何配置。
- 头像只接受 http(s)：相对路径、`data:` 一律丢弃，避免把任意本地路径塞进渲染层。
- 事件先归一化再记账：`roster`（花名册）、`total`（分类计数）、`lastAgo`（最后一帧）
  对两种来源口径一致，控制台状态条因此可以统一显示。
- `/health` 会带上 `platform` 与 `stats`，老桥没有这些字段时下游按空处理。
