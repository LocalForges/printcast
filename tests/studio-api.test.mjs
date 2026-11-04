// P1：工作台 API 客户端契约。用最小 fetch 桩跑真实的 studio/src/api.js，
// 锁死 schedule 复现参数、操作日志查询与写操作的请求形状。
import test from 'node:test';
import assert from 'node:assert/strict';
import { api } from '../studio/src/api.js';

function withFetch(handler) {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    const payload = handler ? handler(url, init) : { ok: true };
    return {
      ok: true, status: 200,
      text: async () => JSON.stringify(payload),
    };
  };
  return { calls, restore: () => { globalThis.fetch = original; } };
}

test('scheduleQuery 完整携带复现参数（含 loop 关闭）', () => {
  const q = api.scheduleQuery({
    packs: ['ming-emperors', 'sanguo'], strategy: 'interleave',
    mode: 'weighted', seed: '20261104', count: 12, loop: false,
  });
  assert.match(q, /^\/schedule\?/);
  for (const part of ['pack=ming-emperors', 'pack=sanguo', 'strategy=interleave',
    'mode=weighted', 'seed=20261104', 'count=12', 'loop=0']) {
    assert.ok(q.includes(part), q + ' 缺少 ' + part);
  }
});

test('scheduleQuery 省略留空参数，不产生 seed=undefined', () => {
  const q = api.scheduleQuery({ packs: ['a'], strategy: 'concat' });
  assert.equal(q, '/schedule?pack=a&strategy=concat');
  assert.ok(!q.includes('undefined'));
  assert.ok(!q.includes('loop='));
});

test('previewSchedule 走 GET 并把响应体解包', async () => {
  const { calls, restore } = withFetch((url) => ({
    ok: true, seed: 20261104, appearances: [{ name: '甲' }],
    requested: url,
  }));
  try {
    const data = await api.previewSchedule({
      packs: ['a'], strategy: 'concat', mode: 'weighted',
      seed: '20261104', count: 8,
    });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].init.method, 'GET');
    assert.equal(calls[0].url, '/__api/schedule?pack=a&strategy=concat&mode=weighted&seed=20261104&count=8');
    assert.equal(data.seed, 20261104);
    assert.equal(data.appearances[0].name, '甲');
  } finally { restore(); }
});

test('getAudit 编码筛选参数并回传 entries / stats', async () => {
  const { calls, restore } = withFetch(() => ({
    ok: true, entries: [{ action: 'pack.save' }], stats: { total: 1 },
  }));
  try {
    const data = await api.getAudit({ limit: 50, action: 'pack.save', q: '明 朝' });
    assert.equal(calls[0].url, '/__api/audit?limit=50&action=pack.save&q=%E6%98%8E%20%E6%9C%9D');
    assert.equal(data.stats.total, 1);
  } finally { restore(); }
});

test('clearAudit 走 DELETE，broadcast start 保留数字 seed', async () => {
  const { calls, restore } = withFetch(() => ({ ok: true }));
  try {
    await api.clearAudit();
    assert.equal(calls[0].init.method, 'DELETE');
    assert.equal(calls[0].url, '/__api/audit');
    await api.broadcast('start', { packs: ['a'], seed: 20261104, loop: true });
    const body = JSON.parse(calls[1].init.body);
    assert.equal(body.action, 'start');
    assert.equal(body.seed, 20261104);
    assert.equal(typeof body.seed, 'number', 'seed 必须是 number，否则与 schedule 的 int 解析不一致');
    assert.equal(body.loop, true);
  } finally { restore(); }
});

test('savePack / importData 的请求形状', async () => {
  const { calls, restore } = withFetch(() => ({ ok: true, pack: {} }));
  try {
    await api.savePack({ id: 'a', title: 'A', characters: [] });
    assert.equal(calls[0].init.method, 'POST');
    assert.equal(calls[0].url, '/__api/packs');
    assert.equal(JSON.parse(calls[0].init.body).id, 'a');
    await api.importData({ format: 'json', pack: {}, content: {} }, true);
    assert.equal(calls[1].url, '/__api/import?commit=1');
    assert.equal(calls[1].init.method, 'POST');
  } finally { restore(); }
});
