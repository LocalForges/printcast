// 打印队列策略：唯一一处决定「能不能进队列」的地方。
// 旧版剧本出场直接 queue.push()，队列无上限、无去重，配合 5 秒自动出场会无限堆积；
// 这里把上限、去重和状态语义显式化，浏览器与 Node 测试共用同一份实现。
export const QUEUE_LIMIT = 40;

/**
 * @param {{length:number, seen:Set, key?:string|number|null, limit?:number}} input
 * @returns {{ok:boolean, reason:string}}
 */
export function shouldEnqueue({ length, seen, key = null, limit = QUEUE_LIMIT }) {
  if (!Number.isFinite(length) || length < 0) return { ok: false, reason: 'invalid' };
  const max = Number.isFinite(limit) && limit > 0 ? Math.floor(limit) : QUEUE_LIMIT;
  if (length >= max) return { ok: false, reason: 'full' };
  if (key !== null && key !== undefined && seen && seen.has(key)) {
    return { ok: false, reason: 'duplicate' };
  }
  return { ok: true, reason: '' };
}

/** 记住已入队的键，并给集合设上界，避免长时间直播后无界增长。 */
export function remember(seen, key, cap = 512) {
  if (!seen || key === null || key === undefined) return seen;
  if (seen.size >= cap) seen.clear();
  seen.add(key);
  return seen;
}

/**
 * 出场序列进度与打印进度是两个不同的概念：
 * 前者来自后端 broadcast（第 N 位 / 共 M 位），后者来自展示端内存队列（第几层 / 百分比）。
 * 控制台过去把两者混标成「现在正在打印」，这里提供明确的格式化入口。
 */
export function describeAppearanceProgress({ seq, total, round } = {}) {
  const parts = [];
  if (Number.isFinite(seq)) parts.push(`第 ${seq} 位`);
  if (Number.isFinite(total) && total > 0) parts.push(`共 ${total} 位`);
  if (Number.isFinite(round) && round > 0) parts.push(`第 ${round} 轮`);
  return parts.join(' · ') || '尚未开播';
}

export function describePrintProgress({ name, percent, phase } = {}) {
  if (phase === 'idle' || !name) return '待命';
  if (phase === 'reveal' || phase === 'transfer') return `当前：${name} · 出分转运`;
  return `当前：${name} · 打印中 ${Math.max(0, Math.min(100, Math.round(percent || 0)))}%`;
}
