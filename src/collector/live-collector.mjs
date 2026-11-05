#!/usr/bin/env node
// 直播数据桥：把直播间的弹幕/点赞/礼物/进场归一化成事件契约 v1，转发给头像打印机。
// 用法：node live-collector.mjs [房间号] [WS端口] [平台]
//   平台默认 douyin；generic 表示不驱动浏览器，等外部 POST /ingest 推流。
//   也可用环境变量 PRINTCAST_PLATFORM 指定（控制台「直播」设置会透传）。
// 房间号也可写入 .bridge-room 文件；WS 端口默认 8765。
// CDP 端口优先级（与 findTarget() 代码一致）：自建无头 Chrome(:9223) → BrowserOS neo(:9110) → 已开调试端口的 Chromium(:9222)
// 页面(http://127.0.0.1:8080)会自动连接 ws://127.0.0.1:8765，无需手动操作。
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { startWSServer } from '../server/bridge-server.mjs';
import {
  parseChatLine, mapGift, isJunkName, normKey, pbDecode, isExplicitAvatarUrl, isAvatarUrl,
  collectUsers, extractUser, diffNew, allocateLikes, eachEnvelope
} from './parse.mjs';
import { resolvePlatform } from './platforms/index.mjs';
import { normalizeEvent, extractEvents, LIMITS } from './platforms/contract.mjs';
import { COLLECT } from './collect-script.mjs';
import zlib from 'node:zlib';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// 平台由 --platform / PRINTCAST_PLATFORM 决定；未知值回落默认平台，服务不因配置错误起不来。
const PLATFORM = resolvePlatform(process.env.PRINTCAST_PLATFORM || process.argv[4]);
const ROOM_RE = PLATFORM.roomPattern || /live\.douyin\.com\/(\d+)/;
const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
];


// —— 页面内采集脚本（不依赖混淆类名，按文本特征定位） ——
const sleep = ms => new Promise(r => setTimeout(r, ms));
const stamp = () => new Date().toTimeString().slice(0, 8);

function getJson(url, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = http.request(url, { method }, res => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => { try { resolve(JSON.parse(d)) } catch (e) { reject(e) } });
    });
    req.on('error', reject);
    req.end();
  });
}

async function listPages(port) {
  const list = await getJson('http://127.0.0.1:' + port + '/json/list');
  return (Array.isArray(list) ? list : []).filter(t => t.type === 'page' && t.webSocketDebuggerUrl);
}

async function openTab(port, url) {
  try {
    await getJson('http://127.0.0.1:' + port + '/json/new?url=' + encodeURIComponent(url), 'PUT');
  } catch {
    await getJson('http://127.0.0.1:' + port + '/json/new?' + encodeURIComponent(url)).catch(() => { });
  }
  for (let i = 0; i < 30; i++) {
    await sleep(500);
    try {
      const hit = (await listPages(port)).find(t => (t.url || '').indexOf(url.replace(/^https?:\/\//, '').split('?')[0]) >= 0);
      if (hit) return hit;
    } catch { return null }
  }
  return null;
}

async function findTarget(room) {
  const roomUrl = PLATFORM.roomUrl(room);
  for (const port of (process.env.PRINTER_CDP_PORT ? [Number(process.env.PRINTER_CDP_PORT)] : [9223, 9110, 9222])) {
    let pages;
    try { pages = await listPages(port) } catch { continue }
    let hit = pages.find(t => { const m = (t.url || '').match(ROOM_RE); return m && m[1] === room });
    if (!hit && process.env.PRINTER_CDP_PORT) continue;
    if (!hit) {
      console.log('[' + stamp() + '] 在 :' + port + ' 没找到房间标签页，新开一个（不动你已开的页面）…');
      hit = await openTab(port, roomUrl);
      if (!hit) continue;
    }
    return { port, target: hit };
  }
  return null;
}

async function launchStandaloneChrome(room) {
  const exe = CHROME_CANDIDATES.find(p => fs.existsSync(p));
  if (!exe) throw new Error('没有可用的 CDP 浏览器，也未找到 Chrome/Edge 可执行文件');
  const dir = path.join(__dirname, '.bridge-profile');
  fs.mkdirSync(dir, { recursive: true });
  console.log('[' + stamp() + '] 弹出直播间窗口(:9223)…可在里面登录抖音，登录后头像抓取更全');
  spawn(exe, [
    '--remote-debugging-port=9223', '--user-data-dir=' + dir,
    '--no-first-run', '--no-default-browser-check', '--lang=zh-CN',
    '--window-position=120,90', '--window-size=1180,800',
    '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
    '--disable-background-timer-throttling', '--disable-features=IntensiveWakeUpThrottling,CalculateNativeWinOcclusion',
    PLATFORM.roomUrl(room)
  ], { detached: true, stdio: 'ignore' }).unref();
  for (let i = 0; i < 50; i++) {
    await sleep(500);
    try { await getJson('http://127.0.0.1:9223/json/version'); return } catch { }
  }
  throw new Error('自建浏览器启动超时');
}

function attachCDP(target) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(target.webSocketDebuggerUrl);
    let mid = 0;
    const pend = new Map();
    const rpc = (method, params = {}, sessionId) => new Promise((res, rej) => {
      const id = ++mid;
      pend.set(id, { res, rej });
      ws.send(JSON.stringify(sessionId ? { id, method, params, sessionId } : { id, method, params }));
    });
    ws.onopen = async () => {
      try {
        await rpc('Runtime.enable');
        await rpc('Network.enable');
        resolve({ ws, rpc });
      } catch (e) { reject(e) }
    };
    ws.onmessage = ev => {
      let m;
      try { m = JSON.parse(ev.data) } catch { return }
      if (m.id && pend.has(m.id)) {
        const p = pend.get(m.id);
        pend.delete(m.id);
        m.error ? p.rej(new Error(m.error.message || 'cdp error')) : p.res(m.result);
        return;
      }
      if (m.method && cdpEventSink) { try { cdpEventSink(m) } catch { } }
    };
    ws.onerror = () => reject(new Error('CDP WebSocket 连接失败'));
  });
}

let currentRoom = '';
let hubRef = null; // 模块级 hub 引用：emitLike/pollFollowers 等在 run() 外也要能广播（原先引用未定义的 hub 会抛错被吞）。
let cdpRef = null;
export function _injectCdpForTest(ref) { cdpRef = ref; }
export function _handleWSFrameForTest(buf) { handleWSFrame(buf) }
export function _injectHubForTest(h) { hubRef = h }
export function _avatarStateForTest() { return { avatars: { ...avatars }, roster: [...roster.entries()], cache: [...avatarCache.entries()], normMap: [...normMap.entries()] } }
let lastLikes = null, clientCount = 0, chatSeen = false, historySkipped = false, owner = '';
const roster = new Map(), likeState = { idx: 0, used: new Map() }, lastSeen = new Map();
const seen = new Set(), avatars = {};
const total = { comment: 0, gift: 0, like: 0, join: 0 };
let likeTokens = 20, likeTokensAt = Date.now(), lastThrottleLog = 0, lastEventAt = 0, lastNavFix = 0, lastWsLikeAt = 0, lastWsJoinAt = 0, cdpEventSink = null, lastFollowerCount = null, lastFollowerPoll = 0;

// 协议级入口：WebSocket 二进制帧 → gunzip → 逐信封识别 → 喂头像 / 广播事件。
// 这是"零点击也能拿到头像"的主路径，页面 DOM 采集只是兜底。
function handleWSFrame(buf) {
  try {
    let payload = buf;
    const idx = buf.indexOf(Buffer.from([0x1f, 0x8b]));
    if (idx >= 0) { try { payload = zlib.gunzipSync(buf.subarray(idx)); } catch { return } }
    eachEnvelope(payload, (method, pl) => {
      const mt = method.match(/^Webcast(Chat|Like|Member|Social|Gift|RoomUserSeq)Message$/);
      if (!mt) return;
      // 消息体里每个 User 结构都自带头像，全部喂进花名册（RoomUserSeq 一次带多名活跃观众）。
      const users = collectUsers(pl);
      for (const u of users) feedAvatar(u.name, u.avatar, '协议帧');
      const type = mt[1] === 'Like' ? 'like' : mt[1] === 'Social' ? 'follow' : mt[1] === 'Member' ? 'join' : null;
      const actor = users[0];
      if (!actor || !type) return;
      if (type === 'like') emitLike(actor);
      else if (type === 'follow') emitFollow(actor);
      else if (type === 'join') emitJoinWS(actor);
    });
  } catch { }
}

// —— 头像持久缓存：跨重启、跨房间复用，回访观众零延迟命中 ——
const AVATAR_CACHE_FILE = path.join(__dirname, 'avatar-cache.json');
const AVATAR_CACHE_MAX = 3000;
const avatarCache = new Map(), avatarCacheNorm = new Map();
const normMap = new Map();
let cacheDirty = false;

function loadAvatarCache() {
  try {
    const data = JSON.parse(fs.readFileSync(AVATAR_CACHE_FILE, 'utf8'));
    for (const [n, a] of Object.entries(data.items || {})) {
      if (typeof a !== 'string' || !isExplicitAvatarUrl(a) || isJunkName(n)) continue;
      avatarCache.set(n, a);
      const k = normKey(n);
      if (k && !avatarCacheNorm.has(k)) avatarCacheNorm.set(k, a);
    }
    if (avatarCache.size) console.log('[' + stamp() + '] 📦 已载入历史头像缓存 %d 人（回访观众秒出头像）', avatarCache.size);
  } catch { }
}

function saveAvatarCache() {
  if (!cacheDirty) return;
  cacheDirty = false;
  try {
    const items = {};
    let i = 0;
    for (const [n, a] of avatarCache) { items[n] = a; if (++i >= AVATAR_CACHE_MAX) break; }
    const tmp = AVATAR_CACHE_FILE + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify({ version: 1, savedAt: Date.now(), items }));
    fs.renameSync(tmp, AVATAR_CACHE_FILE);
  } catch { }
}

// Map 按插入序迭代：重设同一键会保持原位，所以先 delete 再 set 才能把最近活跃的排到队尾，
// 超出上限时被裁掉的永远是最久未出现的头像。
function feedAvatarCache(name, avatar) {
  if (avatarCache.get(name) !== avatar) {
    avatarCache.delete(name);
    avatarCache.set(name, avatar);
    cacheDirty = true;
  }
  const k = normKey(name);
  if (k) { avatarCacheNorm.delete(k); avatarCacheNorm.set(k, avatar); }
}

// 事件现场按昵称查历史缓存；命中就顺势灌进本房间的 avatars，后续直接走内存。
function lookupAvatar(name) {
  const k = normKey(name);
  const hit = avatarCache.get(name) || (k && avatarCacheNorm.get(k)) || '';
  if (hit && !avatars[name]) avatars[name] = hit;
  return hit || '';
}

// 所有头像入口统一走这里：本房间 avatars + 归一化索引 + 持久缓存 + 花名册 + 活跃时间。
function feedAvatar(name, avatar, via = '页面') {
  if (!name || !avatar || isJunkName(name)) return;
  const k = normKey(name);
  if (avatars[name] !== avatar) avatars[name] = avatar;
  if (k) normMap.set(k, avatar);
  feedAvatarCache(name, avatar);
  if (roster.get(name) !== avatar) {
    if (!roster.has(name)) {
      likeState.used.clear();
      console.log('[' + stamp() + '] 🧑 首次入库 %s 的头像（%s）', name, via);
    }
    roster.set(name, avatar);
    lastSeen.set(name, Date.now());
  }
}

// 事件出口（契约 v1）：浏览器采集与通用推流共用同一条通道与同一套记账，
// 这样「谁在榜上、总数多少、最后一帧多久前」对两种来源口径一致。
function publishLiveEvent(raw, source) {
  const ev = normalizeEvent(raw, { platform: PLATFORM.id, source });
  if (!ev) return null;
  lastEventAt = Date.now();
  if (!lastSeen.has(ev.name)) lastSeen.set(ev.name, Date.now());
  if (ev.avatar) feedAvatar(ev.name, ev.avatar, source === 'ingest' ? '推流头像' : '页面头像');
  else if (!roster.has(ev.name)) roster.set(ev.name, '');
  if (ev.type === 'comment') total.comment++;
  else if (ev.type === 'gift') total.gift++;
  else if (ev.type === 'like') total.like += ev.count || 1;
  else if (ev.type === 'join') total.join++;
  hubRef?.broadcast(ev);
  return ev;
}

// /ingest 的业务侧：归一化 + 计数 + 进入打印通道。传输层校验在 bridge-server。
function ingestEvents(payload, limit = LIMITS.eventsPerRequest) {
  const list = extractEvents(payload).slice(0, limit);
  let accepted = 0;
  const rejected = [];
  for (const raw of list) {
    if (publishLiveEvent(raw, 'ingest')) accepted++;
    else rejected.push(String(raw && raw.type ? raw.type : 'unknown'));
  }
  return { accepted, rejected };
}

// 点赞令牌桶：20 个令牌，每 400ms 回 1 个，单次最多放行 3 个。
// 抖音在人气高峰会连续推送 Like 帧，不限速会把下游打印队列瞬间打满。
function emitLike(user) {
  const nowMs = Date.now();
  likeTokens = Math.min(20, likeTokens + (nowMs - likeTokensAt) / 400);
  likeTokensAt = nowMs;
  const allowed = Math.min(3, Math.floor(likeTokens));
  likeTokens -= allowed;
  lastWsLikeAt = nowMs;
  if (allowed <= 0) {
    if (nowMs - lastThrottleLog > 10000) { lastThrottleLog = nowMs; console.log('[' + stamp() + '] ❤️ 点赞高峰限速中'); }
    return;
  }
  total.like += allowed;
  lastEventAt = nowMs;
  hubRef.broadcast({ type: 'like', name: user.name, avatar: user.avatar || '', count: allowed });
  console.log('[' + stamp() + '] ❤️ %s 点赞 +%d（协议级）', user.name, allowed);
}

function emitFollow(user) {
  if (!user || !user.name) return;
  total.join++;
  lastEventAt = Date.now();
  hubRef.broadcast({ type: 'follow', name: user.name, avatar: user.avatar || '' });
  console.log('[' + stamp() + '] ⭐ %s 关注了直播间 → 打印头像', user.name);
}

function emitJoinWS(user) {
  if (!user || !user.name) return;
  lastWsJoinAt = Date.now();
  total.join++;
  lastEventAt = Date.now();
  hubRef.broadcast({ type: 'join', name: user.name, avatar: user.avatar || '' });
  console.log('[' + stamp() + '] 👋 %s 进入直播间（协议级）', user.name);
}

function resetRoomState() {
  lastLikes = null; chatSeen = false; historySkipped = false; owner = '';
  roster.clear(); lastSeen.clear(); seen.clear();
  for (const k of Object.keys(avatars)) delete avatars[k];
  likeState.used.clear(); likeState.idx = 0;
  hoverTried.clear();
  total.comment = total.gift = total.like = total.join = 0;
}

// 关注检测：轮询登录账号菜单里的粉丝数，涨粉即打印头像（归属最近活跃观众）。
async function pollFollowers() {
  if (!cdpRef || !owner) return;
  if (Date.now() - lastFollowerPoll < 30000) return;
  lastFollowerPoll = Date.now();
  try {
    const posRaw = (await cdpRef.rpc('Runtime.evaluate', {
      expression: `(() => {
        const imgs = [...document.querySelectorAll('img')].filter(i => { const r = i.getBoundingClientRect(); return r.top < 130 && r.left > innerWidth * 0.55 && r.width >= 22 && r.width <= 90 && r.height >= 22 && /douyinpic/.test(i.currentSrc || i.src || ''); });
        const el = imgs[0];
        if (!el) return 'null';
        const r = el.getBoundingClientRect();
        return JSON.stringify({ x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) });
      })()`,
      returnByValue: true
    })).result.value;
    if (!posRaw || posRaw === 'null') return;
    const { x, y } = JSON.parse(posRaw);
    await cdpRef.rpc('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
    await sleep(500);
    await cdpRef.rpc('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x + 2, y: y + 2 });
    await sleep(700);
    const fansRaw = (await cdpRef.rpc('Runtime.evaluate', {
      expression: `(() => { const m = (document.body.innerText || '').match(/粉丝(\\d{3,9})/); return m ? m[1] : ''; })()`,
      returnByValue: true
    })).result.value;
    await cdpRef.rpc('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 2, y: 2 }).catch(() => { });
    const fans = fansRaw ? parseInt(fansRaw, 10) : null;
    if (fans == null) return;
    if (lastFollowerCount != null && fans > lastFollowerCount) {
      const n = Math.min(fans - lastFollowerCount, 10);
      const pool = [...roster.entries()].filter(([nm]) => nm !== owner).sort((a, b) => (lastSeen.get(b[0]) || 0) - (lastSeen.get(a[0]) || 0));
      for (let i = 0; i < n && pool.length; i++) {
        const [name, avatar] = pool[i % pool.length];
        total.join++;
        lastEventAt = Date.now();
        hubRef.broadcast({ type: 'follow', name, avatar: avatar || '' });
        console.log('[' + stamp() + '] ⭐ 新关注（粉丝 ' + lastFollowerCount + '→' + fans + '）→ 打印 ' + name);
      }
    }
    lastFollowerCount = fans;
  } catch { }
}

// 串行悬停，避免多条评论同时移动鼠标导致资料卡串人。
// hoverTried 记每个昵称的批次次数与上次时间：冷却 4 秒，最多 4 批（12 次点击轮），之后交给首字兜底。
const hoverTried = new Map();
const HOVER_COOLDOWN_MS = 4000, HOVER_MAX_BATCHES = 4;
let hoverQueue = Promise.resolve();
function hoverResolveAvatars(names) {
  const room = currentRoom;
  const work = hoverQueue.then(() => room === currentRoom ? resolveHoverBatch(names) : undefined);
  hoverQueue = work.catch(() => {});
  return work;
}
export async function clickNickname(rpc, x, y) {
  await rpc('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  await rpc('Input.dispatchMouseEvent', { type: 'mousePressed', button: 'left', clickCount: 1, x, y });
  await rpc('Input.dispatchMouseEvent', { type: 'mouseReleased', button: 'left', clickCount: 1, x, y });
}

const CARD_OPEN = `!![...document.querySelectorAll('[role="dialog"],dialog')].find(e => { const r=e.getBoundingClientRect(); return r.width>0 && r.height>0; })`;
export async function dismissProfileCard(rpc, force = false) {
  const read = async expression => (await rpc('Runtime.evaluate', {expression,returnByValue:true})).result.value;
  const open = await read(CARD_OPEN);
  if (!open && !force) return true;
  const point = await read(`(() => {
    const editors = [...document.querySelectorAll('[contenteditable="true"],textarea')];
    for (const editor of editors) {
      if (editor.closest('[role="dialog"],dialog')) continue;
      const r=editor.getBoundingClientRect();
      if(r.width<10 || r.height<5 || r.bottom>innerHeight || r.top<0) continue;
      const x=r.left+Math.min(20,r.width/2), y=r.top+r.height/2;
      const hit=document.elementFromPoint(x,y);
      if(hit && (hit===editor || editor.contains(hit))) return {x,y};
    }
    return null;
  })()`);
  if (!point) return false;
  // Only focus the comment editor; never type, press Enter, or click Send.
  await clickNickname(rpc, point.x, point.y);
  for (let i=0;i<5;i++) {
    await sleep(100);
    if (!await read(CARD_OPEN)) return true;
  }
  return false;
}

export async function resolveHoverBatch(names) {
  if (!cdpRef) return;
  for (const name of names) {
    const rec = hoverTried.get(name);
    if (rec && (rec.n >= HOVER_MAX_BATCHES || Date.now() - rec.t < HOVER_COOLDOWN_MS)) continue;
    hoverTried.set(name, { t: Date.now(), n: (rec?.n || 0) + 1 });
    let avRaw = '';
    try {
      // 同一昵称最多点3轮，每轮换一个点击位置（靠左 / 靠左起点 / 居中 / 靠右），提高资料卡命中率。
      for (let round = 0; round < 3 && !avRaw; round++) {
      if (!await dismissProfileCard(cdpRef.rpc)) { console.warn('资料卡未关闭，暂停本轮点击，避免误入主页'); return; }
      const posRaw = (await cdpRef.rpc('Runtime.evaluate', {
        expression: `(() => {
          const name = ${JSON.stringify(name)};
          // 先在弹幕区找昵称；弹幕滚得快找不到时，退而全页找（观众列表/粉丝面板里的同款昵称也能开资料卡）。
          const scopes = window.__chatRoot && window.__chatRoot.isConnected ? [window.__chatRoot, document] : [document];
          let els = [];
          for (const scope of scopes) {
            els = [...scope.querySelectorAll('span,a,div')].filter(e => {
              if (e.closest?.('[role="dialog"],dialog')) return false;
              const text = (e.textContent || '').trim();
              const r = e.getBoundingClientRect();
              const matches = text === name || text === name + '：' || text === name + ':' || (!e.children.length && (text.startsWith(name + '：') || text.startsWith(name + ':')));
              return matches && r.width > 2 && r.height > 2 && r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.left < innerWidth;
            });
            if (els.length) break;
          }
          const el = els[els.length - 1];
          if (!el) return '[]';
          const r = el.getBoundingClientRect();
          if (r.width < 2 || r.top < 40) return '[]';
          const y = Math.round(r.top + r.height / 2);
          const ends = [['左', Math.min(30, r.width / 2)], ['靠左', Math.min(12, r.width / 2)], ['中', r.width / 2], ['右', r.width - Math.min(14, r.width / 3)]];
          const out = [];
          for (const [label, off] of ends) {
            const x = Math.round(r.left + off);
            const hit = document.elementFromPoint(x, y);
            if (!hit || !(hit === el || el.contains(hit))) continue;
            if (out.some(p => p.x === x && p.y === y)) continue;
            out.push({ x, y, label });
          }
          return JSON.stringify(out);
        })()`,
        returnByValue: true
      })).result.value;
      const points = JSON.parse(posRaw || '[]');
      if (!points.length) { console.log('头像补取：未定位到可见昵称 ' + name); break; }
      const spot = points[Math.min(round, points.length - 1)];
      await clickNickname(cdpRef.rpc, spot.x, spot.y);
      // 点击后等待资料卡出现，并持续轮询等头像图片读取完成（卡片开着最多等约4秒）。
      let cardSeen = false;
      for (let attempt = 0; attempt < 16 && !avRaw; attempt++) {
      await sleep(250);
      const rawCard = (await cdpRef.rpc('Runtime.evaluate', {
        expression: `(() => {
          const name = ${JSON.stringify(name)};
          let card = false;
          for (const dialog of document.querySelectorAll('[role="dialog"],dialog')) {
            const heading = [...dialog.querySelectorAll('h1,h2,h3,h4,[role="heading"]')].find(e => (e.textContent || '').trim() === name);
            if (!heading || !dialog.getBoundingClientRect().width) continue;
            card = true;
            const images = [...dialog.querySelectorAll('img')].filter(img => {
              const src = img.currentSrc || img.src || '', r = img.getBoundingClientRect();
              return img.complete && img.naturalWidth > 0 && r.width >= 40 && r.height >= 40 && r.width / r.height > .8 && r.width / r.height < 1.2 && /douyinpic|byteimg/.test(src) && !/badge|medal|grade_level|icon/.test(src);
            }).sort((a,b) => b.getBoundingClientRect().width - a.getBoundingClientRect().width);
            if (images.length) return JSON.stringify({ card: true, avatar: images[0].currentSrc || images[0].src });
          }
          // Require an exact nickname inside a compact card; never scan a broad page ancestor.
          const labels = [...document.querySelectorAll('span,a,div,h1,h2,h3,h4')].filter(e => (e.textContent || '').trim() === name && ![...e.children].some(c => (c.textContent || '').trim() === name));
          const pops = [];
          for (const label of labels) {
            let e = label.parentElement;
            for (let i = 0; i < 5 && e; i++, e = e.parentElement) {
              const t = e.innerText || '', r = e.getBoundingClientRect();
              if (t.length > 300) break;
              if (/粉丝|关注/.test(t) && r.width > 0 && r.height > 0 && e.querySelector('img')) {
                const imgs = [...e.querySelectorAll('img')].filter(img => /aweme-avatar|tos-cn-avt|sc=avatar/.test(img.currentSrc || img.src || ''));
                if (imgs.length === 1) pops.push(e);
                break;
              }
            }
          }
          for (const e of pops) {
            card = true;
            for (const img of e.querySelectorAll('img')) {
              const s = img.currentSrc || img.src || '';
              if (/(aweme-avatar|tos-cn-avt|sc=avatar)/i.test(s)) {
                if (img.complete && img.naturalWidth > 0 && !/grade_level|badge|medal|icon|\\.svg/i.test(s)) return JSON.stringify({ card: true, avatar: s });
              }
            }
          }
          return JSON.stringify({ card, avatar: '' });
        })()`,
        returnByValue: true
      })).result.value;
        let read = {}; try { read = JSON.parse(rawCard || '{}') } catch { }
        if (read.avatar) { avRaw = read.avatar; break }
        if (read.card) cardSeen = true;
        else if (!cardSeen && attempt >= 2) break;
      }
      await cdpRef.rpc('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 2, y: 2 }).catch(() => { });
      if (avRaw) {
        feedAvatar(name, avRaw, '资料卡');
        console.log('[' + stamp() + '] 🪪 点击资料卡获取到头像：' + name + '（第' + (round + 1) + '次点击·' + spot.label + '）');
      } else {
        console.log('头像补取：第' + (round + 1) + '次点击（' + spot.label + '）' + (cardSeen ? '头像未读取完成' : '资料卡未出现') + ' ' + name);
        // 到评论区点一下，关闭资料卡或清掉残留弹层，再换位置重试。
        await dismissProfileCard(cdpRef.rpc, true).catch(() => false);
        await sleep(350);
      }
      }
    } catch (err) { console.warn('点击头像补取失败：' + err.message); }
    finally {
      if (!await dismissProfileCard(cdpRef.rpc).catch(() => false)) console.warn('资料卡仍显示，下次获取前将先关闭资料卡');
    }
  }
}

async function run(hub) {
  hubRef = hub;
  const room = currentRoom;
  let found = await findTarget(room);
  if (!found) {
    if (process.env.PRINTER_CDP_PORT) throw new Error('独立直播窗口未就绪，请完成登录后重新开始抓取');
    await launchStandaloneChrome(room);
    found = await findTarget(room);
  }
  if (!found) throw new Error('无法获得直播间页面（尝试过 :9110 :9222 :9223）');
  const { port, target } = found;
  console.log('[' + stamp() + '] 已挂接浏览器 :%d → %s', port, target.url);
  const { ws, rpc } = await attachCDP(target);
  cdpRef = { ws, rpc };
  if (((target.url || '').match(ROOM_RE) || [])[1] !== currentRoom) {
    await rpc('Page.navigate', { url: PLATFORM.roomUrl(currentRoom) }).catch(() => { });
    await sleep(4000);
  }
  console.log('[' + stamp() + '] 📺 直播间 ' + PLATFORM.roomUrl(currentRoom) + ' 采集中，每 0.3 秒刷新 + 协议流解码');
  cdpEventSink = m => {
    if (m.method === 'Target.attachedToTarget' && m.params && m.params.sessionId) {
      const sid = m.params.sessionId;
      cdpRef.rpc('Network.enable', {}, sid).catch(() => { });
      cdpRef.rpc('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: false, flatten: true }, sid).catch(() => { });
    } else if (m.method === 'Network.webSocketFrameReceived' && m.params && m.params.response && m.params.response.payloadData) {
      const p = m.params.response;
      try {
        if (p.opcode === 2) handleWSFrame(Buffer.from(p.payloadData, 'base64'));
        else if (typeof p.payloadData === 'string' && p.payloadData.length > 40) handleWSFrame(Buffer.from(p.payloadData, 'utf8'));
      } catch { }
    }
  };
  await cdpRef.rpc('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: false, flatten: true }).catch(() => { });

  // 断线重连：永久重试但每次都带 catch，绝不让 unhandled rejection 杀掉进程。
  const reconnect = () => setTimeout(() => {
    run(hub).catch(e => {
      console.error('[' + stamp() + '] ❌ ' + (e.message || e) + '，3 秒后重试');
      reconnect();
    });
  }, 3000);
  const fail = err => {
    clearInterval(timer);
    cdpRef = null;
    console.log('[' + stamp() + '] 连接断开（%s），3 秒后重连…', err.message || err);
    try { ws.close() } catch { }
    reconnect();
  };
  ws.onerror = () => { };
  ws.onclose = () => fail(new Error('CDP closed'));

  function emit(ev) {
    const out = publishLiveEvent(ev, 'browser');
    if (!out) return;
    if (out.type === 'comment') console.log('[' + stamp() + '] 💬 %s：%s%s', out.name, out.text || '', out.avatar ? ' 🪪' : ' △无头像');
    else if (out.type === 'gift') console.log('[' + stamp() + '] 🎁 %s 送出 %s x%d → %s', out.name, out.raw, out.count, out.gift);
    else if (out.type === 'like') console.log('[' + stamp() + '] ❤️ %s 点赞 +%d%s', out.name, out.count, out.avatar ? '（带头像）' : '');
    else if (out.type === 'join') console.log('[' + stamp() + '] 👋 %s 进入直播间', out.name);
  }

  let commentResolution = Promise.resolve();
  function handle(s) {
    if (s.owner) owner = s.owner;
    for (const [n, a] of Object.entries(s.avatars || {})) {
      if (!a || !n || n === owner || isJunkName(n)) continue;
      if (!roster.has(n) && !(s.lines || []).some(line => parseChatLine(line)?.name === n)) continue;
      if (!roster.has(n)) likeState.used.clear();
      feedAvatar(n, a, '页面头像');
    }
    const normAvatars = {};
    for (const [n, a] of Object.entries(s.avatars || {})) { const k = normKey(n); if (k && a && !normAvatars[k]) normAvatars[k] = a; }
    if (s.likes != null) {
      if (lastLikes == null) lastLikes = s.likes;
      else if (s.likes > lastLikes && Date.now() - lastWsLikeAt > 30000) {
        const delta = Math.min(s.likes - lastLikes, 100);
        const pool = [...roster.entries()].sort((x, y) => (Number(!!y[1]) - Number(!!x[1])) || ((lastSeen.get(y[0]) || 0) - (lastSeen.get(x[0]) || 0)));
        const events = allocateLikes(delta, pool, likeState);
        const nowMs = Date.now();
        likeTokens = Math.min(20, likeTokens + (nowMs - likeTokensAt) / 400);
        likeTokensAt = nowMs;
        const budget = Math.floor(likeTokens);
        const allowed = Math.min(events.length, budget);
        likeTokens -= allowed;
        if (events.length > allowed && nowMs - lastThrottleLog > 10000) {
          lastThrottleLog = nowMs;
          console.log('[' + stamp() + '] ❤️ 点赞风暴限速中（高峰期限流，平时秒放行）');
        }
        for (const ev of events.slice(0, allowed)) emit({ type: 'like', ...ev });
        if (delta > 0 && !events.length && !roster.size) console.log('[' + stamp() + '] ❤️ 点赞 +%d（观众名单还没就绪，先不打印）', delta);
      }
      lastLikes = s.likes;
    }
    const parsedNames = [];
    // 挂接前已滚过的历史弹幕只做头像同步，不打印——开局不该吐一堆旧评论，且它们的协议帧早已消失、头像注定补不齐。
    if (!historySkipped && (s.lines || []).length) {
      historySkipped = true;
      let skipped = 0;
      for (const line of s.lines) if (!seen.has(line)) { seen.add(line); skipped++; }
      if (skipped) console.log('[' + stamp() + '] ⏭ 跳过挂接前已存在的 %d 条历史弹幕（不打印旧评论）', skipped);
    }
    for (const line of diffNew(s.lines || [], seen)) {
      const ev = parseChatLine(line);
      if (!ev) continue;
      const key = normKey(ev.name);
      const avatar = avatars[ev.name] || (key && (normMap.get(key) || normAvatars[key])) || lookupAvatar(ev.name) || roster.get(ev.name) || '';
      if (!roster.has(ev.name)) likeState.used.clear();
      roster.set(ev.name, avatar);
      lastSeen.set(ev.name, Date.now());
      if (ev.kind !== 'comment') parsedNames.push(ev.name);
      if (ev.kind === 'comment' || ev.kind === 'gift') {
        // Preserve every comment, including repeated text; resolve its avatar before dispatch.
        commentResolution = commentResolution.then(async () => {
          if (room !== currentRoom) return;
          // 协议帧与弹幕几乎同时到达且必带头像：先短暂等待，命中就免去一次资料卡点击。
          if (!avatars[ev.name] && !(key && normMap.get(key)) && !avatar) {
            for (let i = 0; i < 12 && room === currentRoom; i++) {
              await sleep(200);
              if (avatars[ev.name] || (key && normMap.get(key))) break;
            }
          }
          if (room !== currentRoom) return;
          if (!avatars[ev.name] && !(key && normMap.get(key)) && !avatar) await hoverResolveAvatars([ev.name]);
          if (room !== currentRoom) return;
          const resolved = avatars[ev.name] || (key && normMap.get(key)) || avatar;
          if (ev.kind === 'gift') emit({ type: 'gift', name: ev.name, gift: mapGift(ev.gift), raw: ev.gift, count: ev.count, avatar: resolved || '' });
          else emit({ type: 'comment', name: ev.name, text: ev.text, avatar: resolved || '' });
        }).catch(err => console.error('评论头像补取失败：', err.message));
      }
      else if (ev.kind === 'follow') emit({ type: 'follow', name: ev.name, avatar });
      else if (ev.kind === 'join' && Date.now() - lastWsJoinAt > 30000) emit({ type: 'join', name: ev.name, avatar });
    }
    if (parsedNames.length) {
      const need = [...new Set(parsedNames.filter(n => !roster.get(n)))];
      if (need.length) hoverResolveAvatars(need.slice(0, 2));
    }
    pollFollowers();
  }

  const timer = setInterval(async () => {
    if (ws.readyState !== 1) return;
    try {
      const r = await rpc('Runtime.evaluate', { expression: COLLECT, returnByValue: true });
      if (r && r.result && r.result.value) {
        const s = r.result.value;
        // Leave login / verification pages alone; only an explicit room switch navigates.
        if (s.href && PLATFORM.hostHint && !s.href.includes(PLATFORM.hostHint + '/' + currentRoom)) return;
        if (!chatSeen && (s.lines.length || s.likes != null)) {
          chatSeen = true;
          console.log('[' + stamp() + '] ✅ 已读到直播数据：弹幕 %d 条，点赞计数 %s', s.lines.length, s.likes);
        }
        handle(s);
      }
    } catch (e) { fail(e) }
  }, 300);

  const watch = setInterval(() => {
    const n = hub.clientCount();
    if (n !== clientCount) {
      if (n > clientCount) {
        hub.broadcast({ type: 'hello', room: currentRoom, people: [...roster.entries()].sort((a, b) => Number(!!b[1]) - Number(!!a[1])).slice(0, 8).map(([name, avatar]) => ({ name, avatar })) });
        console.log('[' + stamp() + '] 🖨 打印页面已连接（共 %d 个）', n);
      } else console.log('[' + stamp() + '] 打印页面断开（剩 %d 个）', n);
      clientCount = n;
    }
    if (hub.clientCount()) hub.broadcast({ type: 'ping', room: currentRoom, ts: Date.now(), people: [...roster.entries()].sort((a, b) => Number(!!b[1]) - Number(!!a[1])).slice(0, 8).map(([name, avatar]) => ({ name, avatar })), stats: { comment: total.comment, like: total.like, gift: total.gift, join: total.join, lastAgo: lastEventAt ? Date.now() - lastEventAt : null, roster: roster.size } });
  }, 2000);
  watch.unref?.();

  // 空闲补取：即使没人发言，也定期给最近活跃、还没有头像的观众再点几次资料卡。
  const sweep = setInterval(() => {
    if (!cdpRef || !hub.clientCount()) return;
    const need = [...roster.keys()].filter(n => !avatars[n])
      .sort((a, b) => (lastSeen.get(b) || 0) - (lastSeen.get(a) || 0)).slice(0, 2);
    if (need.length) hoverResolveAvatars(need);
  }, 45000);
  sweep.unref?.();
}

// 切换房间（set-room 消息与 .bridge-room 文件变更共用）：重置状态、广播、导航新房间。
function applyRoom(room, persist) {
  if (room === currentRoom) {
    hubRef?.broadcast({ type: 'hello', room, people: [...roster.entries()].slice(0, 6).map(([name, avatar]) => ({ name, avatar })) });
    return;
  }
  currentRoom = room;
  if (persist) { try { fs.writeFileSync(path.join(__dirname, '.bridge-room'), room) } catch { } }
  console.log('[' + stamp() + '] 📺 切换直播间 → ' + room);
  resetRoomState();
  hubRef?.broadcast({ type: 'hello', room, people: [] });
  const url = PLATFORM.roomUrl(room);
  if (cdpRef && url) cdpRef.rpc('Page.navigate', { url }).catch(() => { });
}

// 通用推流模式的常驻心跳：形状与浏览器模式一致（hello/ping + 榜单 + 统计），
// 让打印台与控制台无需区分来源就能显示「桥活着 / 最近一帧多久前」。
function startHeartbeat(hub) {
  setInterval(() => {
    if (!hub.clientCount()) return;
    const people = [...roster.entries()]
      .sort((a, b) => Number(!!b[1]) - Number(!!a[1]))
      .slice(0, 8).map(([name, avatar]) => ({ name, avatar }));
    hub.broadcast({
      type: 'ping', v: 1, platform: PLATFORM.id, room: currentRoom, ts: Date.now(), people,
      stats: {
        comment: total.comment, like: total.like, gift: total.gift, join: total.join,
        lastAgo: lastEventAt ? Date.now() - lastEventAt : null, roster: roster.size,
      },
    });
  }, 2000).unref?.();
}

async function main() {
  const argRoom = PLATFORM.parseRoom(process.argv[2] || '');
  let fileRoom = '';
  try { fileRoom = PLATFORM.parseRoom(fs.readFileSync(path.join(__dirname, '.bridge-room'), 'utf8')) } catch { }
  currentRoom = argRoom || fileRoom || currentRoom;
  if (PLATFORM.needsRoom && !currentRoom) { console.error('请提供直播间号：node live-collector.mjs 房间号（也可写入 .bridge-room 文件，或在打印程序里切换房间）'); process.exit(1); }
  loadAvatarCache();
  setInterval(saveAvatarCache, 30000).unref?.();
  process.on('exit', saveAvatarCache);
  // 自动跟随 .bridge-room：应用重开别的直播窗口或手改文件，无需重启数据桥。
  if (PLATFORM.needsRoom) setInterval(() => {
    let next = '';
    try { next = PLATFORM.parseRoom(fs.readFileSync(path.join(__dirname, '.bridge-room'), 'utf8')) } catch { }
    if (next && next !== currentRoom) applyRoom(next, false);
  }, 2000).unref?.();
  const wsPort = Number(process.argv[3]) || 8765;
  const hub = startWSServer(wsPort, {
    // identity 必须是**仓库根**：探测端（printcast.probe.bridge_status）拿它与 ROOT 比对，
    // 用来区分「本仓库起的桥」和「其它目录起的桥」。早期这里上报 __dirname（src/collector），
    // 与 ROOT 永不相等，导致控制台一直显示「数据桥未启动」并把成功启动误报成超时。
    identity: path.resolve(__dirname, '..', '..'), fallbackPorts: process.argv[3] ? 0 : 9,
    onStatus: p => console.log('[' + stamp() + '] ✅ 数据桥服务 ws://127.0.0.1:' + p + '（等待打印页面接入）'),
    onError: err => {
      console.error('[' + stamp() + '] ❌ 端口 ' + wsPort + ' 启动失败（' + err.code + '），可能有另一个数据桥在运行，本实例退出');
      process.exit(1);
    },
    // 通用推流入口：外部平台脚本 POST /ingest，事件与浏览器采集走同一条通道。
    onIngest: payload => ingestEvents(payload),
    // /health 附带平台与统计，控制台状态条据此显示「采集源 / 最近一帧多久前」。
    onHealth: () => ({
      platform: PLATFORM.id,
      room: currentRoom,
      stats: {
        comment: total.comment, like: total.like, gift: total.gift, join: total.join,
        lastAgo: lastEventAt ? Date.now() - lastEventAt : null, roster: roster.size,
      },
    }),
    onMessage: raw => {
      let m; try { m = JSON.parse(raw) } catch { return }
      if (m.type !== 'set-room') return;
      const id = PLATFORM.parseRoom(m.room);
      if (!id) return;
      applyRoom(id, true);
    }
  });
  hubRef = hub;
  if (!PLATFORM.needsBrowser) {
    console.log('[' + stamp() + '] 🔌 ' + PLATFORM.label + '模式：不驱动浏览器，等待外部推流 POST http://127.0.0.1:' + wsPort + '/ingest');
    console.log('[' + stamp() + ']    事件契约：{type: comment|gift|like|join|follow, name, text?, gift?, count?, avatar?}');
    startHeartbeat(hub);
    return;
  }
  console.log('房间号 ' + currentRoom + '。正在弹出直播间窗口（可在里面登录抖音）；来源优先级：自建窗口(:9223) → BrowserOS(:9110) → 调试Chromium(:9222)');
  try { await run(hub) } catch (e) {
    console.error('[' + stamp() + '] ❌ ' + e.message);
    console.error('提示：先打开 BrowserOS neo（会自动用 :9110），或重试本命令。');
    // 启动失败必须退进程，否则 WS 服务把事件循环吊住，变成占着 8765 端口的僵尸。
    saveAvatarCache();
    process.exit(1);
  }
  process.on('SIGINT', () => { saveAvatarCache(); process.exit() });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
