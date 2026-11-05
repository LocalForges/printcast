// 采集事件契约 v1：平台无关的唯一边界。
//
// 任何采集来源（本仓库的抖音浏览器采集、外部脚本的 HTTP 推流、将来新平台的
// 适配器）都必须先归一化成这里的形状，再进入打印队列。下游（打印台）只认
// 这份契约，不认平台。
//
// 纯函数、无副作用：可被 Node 测试直接 import，也可在 collector 之外复用
// （例如给第三方写推流脚本时，直接引用同一份校验逻辑）。
import { mapGift } from '../parse.mjs';

export const CONTRACT_VERSION = 1;

export const EVENT_TYPES = Object.freeze(['comment', 'gift', 'like', 'join', 'follow']);

// 边界值集中在这里：改上限只改一处，测试与文档都引用它。
export const LIMITS = Object.freeze({
  nameMax: 24,
  textMax: 200,
  avatarMax: 512,
  countMax: 999,
  platformMax: 32,
  eventsPerRequest: 50,
  bodyBytes: 64 * 1024,
});

// 制表/换行视作分隔符，其余控制字符直接剔除（否则 '小\u0000明' 会被拆成带空格的昵称）。
const SEPARATOR = /[\t\n\r\u000b\u000c]/g;
const CONTROL = /[\u0000-\u001f\u007f]/g;

function clean(value, max) {
  return String(value == null ? '' : value)
    .replace(SEPARATOR, ' ')
    .replace(CONTROL, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, max);
}

// 头像只接受 http(s) 绝对地址：推流方给相对路径或 data: 一律丢弃走首字徽章，
// 避免把 /media/ 之外的任意路径塞进展示端。
function cleanAvatar(value) {
  const url = clean(value, LIMITS.avatarMax);
  return /^https?:\/\/[^\s]+$/i.test(url) ? url : '';
}

function cleanCount(value) {
  const n = Math.floor(Number(value));
  if (!Number.isFinite(n) || n < 1) return 1;
  return Math.min(n, LIMITS.countMax);
}

/**
 * 归一化一条事件。
 * @param {object} raw 原始事件（可来自采集器或 HTTP 推流）
 * @param {{platform?: string, source?: string}} ctx
 * @returns {object|null} 合法事件；非法返回 null（调用方计入 rejected，不抛异常）
 */
export function normalizeEvent(raw, ctx = {}) {
  if (!raw || typeof raw !== 'object') return null;
  const type = String(raw.type || '').trim().toLowerCase();
  if (!EVENT_TYPES.includes(type)) return null;
  const name = clean(raw.name, LIMITS.nameMax);
  if (!name) return null;
  const platform = clean(ctx.platform || raw.platform || 'generic', LIMITS.platformMax) || 'generic';
  const ev = {
    v: CONTRACT_VERSION,
    platform,
    source: clean(ctx.source || raw.source || 'ingest', 16) || 'ingest',
    type,
    name,
    avatar: cleanAvatar(raw.avatar),
    ts: Number.isFinite(Number(raw.ts)) ? Number(raw.ts) : Date.now(),
  };
  if (type === 'comment') {
    const text = clean(raw.text, LIMITS.textMax);
    if (!text) return null;
    ev.text = text;
  } else if (type === 'gift') {
    const rawGift = clean(raw.raw || raw.gift, 40);
    ev.gift = clean(raw.gift, 16).toLowerCase() || mapGift(rawGift);
    ev.raw = rawGift;
    ev.count = cleanCount(raw.count);
  } else if (type === 'like') {
    ev.count = cleanCount(raw.count);
  }
  return ev;
}

/** 把一条请求体拆成事件数组（支持单条或 {events:[...]}），供 /ingest 使用。 */
export function extractEvents(payload) {
  if (Array.isArray(payload)) return payload;
  if (payload && typeof payload === 'object' && Array.isArray(payload.events)) return payload.events;
  if (payload && typeof payload === 'object') return [payload];
  return [];
}
