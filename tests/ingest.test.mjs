// 采集契约与通用推流口（/ingest）的测试：
// 1) 归一化函数把任意来源收成契约 v1，非法输入一律拒绝而不是抛异常；
// 2) 平台注册表可扩展，未知 id 回落默认平台；
// 3) /ingest 的传输层职责（方法 / 令牌 / 体积 / JSON）与业务回执。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeEvent, extractEvents, LIMITS } from '../src/collector/platforms/contract.mjs';
import { listPlatforms, resolvePlatform } from '../src/collector/platforms/index.mjs';
import { startWSServer } from '../src/server/bridge-server.mjs';

test('契约：评论归一化带上版本与平台', () => {
  const ev = normalizeEvent({ type: 'comment', name: ' 小明 ', text: '打印我  ' }, { platform: 'generic', source: 'ingest' });
  assert.equal(ev.v, 1);
  assert.equal(ev.platform, 'generic');
  assert.equal(ev.source, 'ingest');
  assert.equal(ev.type, 'comment');
  assert.equal(ev.name, '小明');
  assert.equal(ev.text, '打印我');
  assert.equal(ev.avatar, '');
});

test('契约：礼物补全 gift/raw/count 且数量收口', () => {
  const ev = normalizeEvent({ type: 'gift', name: '蛋小黑', raw: '大啤酒', count: 5000 }, { platform: 'douyin' });
  assert.equal(ev.gift, 'beer');
  assert.equal(ev.raw, '大啤酒');
  assert.equal(ev.count, LIMITS.countMax);
  const one = normalizeEvent({ type: 'gift', name: '蛋小黑', gift: 'lollipop', count: 0 });
  assert.equal(one.count, 1);
  assert.equal(one.gift, 'lollipop');
});

test('契约：非 http 头像一律丢弃（防止把任意路径塞进展示端）', () => {
  assert.equal(normalizeEvent({ type: 'join', name: '小明', avatar: '/media/x.png' }).avatar, '');
  assert.equal(normalizeEvent({ type: 'join', name: '小明', avatar: 'data:image/png;base64,AAA' }).avatar, '');
  assert.equal(normalizeEvent({ type: 'join', name: '小明', avatar: 'https://cdn.example.com/a.jpg' }).avatar,
    'https://cdn.example.com/a.jpg');
});

test('契约：非法事件返回 null', () => {
  assert.equal(normalizeEvent(null), null);
  assert.equal(normalizeEvent({ type: 'nope', name: '小明' }), null);
  assert.equal(normalizeEvent({ type: 'comment', name: '' , text: 'x'}), null);
  assert.equal(normalizeEvent({ type: 'comment', name: '小明', text: '   ' }), null);
  assert.equal(normalizeEvent({ type: 'like', name: '   ' }), null);
});

test('契约：控制字符剔除与超长截断', () => {
  const ev = normalizeEvent({ type: 'comment', name: '小\u0000明', text: 'x'.repeat(500) });
  assert.equal(ev.name, '小明');
  assert.equal(ev.text.length, LIMITS.textMax);
  assert.equal(normalizeEvent({ type: 'comment', name: 'a'.repeat(80), text: 'x' }).name.length, LIMITS.nameMax);
});

test('契约：请求体支持单条与 events 数组', () => {
  assert.equal(extractEvents({ type: 'join', name: 'a' }).length, 1);
  assert.equal(extractEvents({ events: [{}, {}] }).length, 2);
  assert.equal(extractEvents([{}, {}, {}]).length, 3);
  assert.equal(extractEvents(null).length, 0);
});

test('平台注册表：内置 douyin / generic，未知回落默认', () => {
  const ids = listPlatforms().map(p => p.id);
  assert.deepEqual(ids.sort(), ['douyin', 'generic']);
  assert.equal(resolvePlatform('generic').id, 'generic');
  assert.equal(resolvePlatform('DOUYIN').id, 'douyin');
  assert.equal(resolvePlatform('other').id, 'douyin');
  assert.equal(resolvePlatform('').id, 'douyin');
});

test('平台元信息：只有 douyin 需要浏览器与房间号', () => {
  assert.equal(resolvePlatform('douyin').needsBrowser, true);
  assert.equal(resolvePlatform('douyin').needsRoom, true);
  assert.equal(resolvePlatform('generic').needsBrowser, false);
  assert.equal(resolvePlatform('generic').supportsIngest, true);
  assert.equal(resolvePlatform('douyin').roomUrl('123456'), 'https://live.douyin.com/123456');
  assert.equal(resolvePlatform('generic').roomUrl('123456'), null);
  assert.equal(resolvePlatform('douyin').parseRoom('https://live.douyin.com/98765?x=1'), '98765');
});

function withServer(handler, fn) {
  return new Promise((resolve, reject) => {
    const hub = startWSServer(0, {
      onStatus: async port => {
        try { await fn(port, hub) } catch (e) { reject(e) } finally { hub.close(); resolve() }
      },
      onError: reject,
      onIngest: handler,
    });
  });
}

test('/ingest：合法事件回执 accepted，非法进 rejected', async () => {
  const seen = [];
  await withServer(payload => {
    const list = extractEvents(payload);
    let accepted = 0; const rejected = [];
    for (const raw of list) {
      const ev = normalizeEvent(raw, { platform: 'generic', source: 'ingest' });
      if (ev) { seen.push(ev); accepted++ } else rejected.push(raw.type || 'unknown');
    }
    return { accepted, rejected };
  }, async port => {
    const res = await fetch(`http://127.0.0.1:${port}/ingest`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ events: [
        { type: 'comment', name: '小明', text: '打印我' },
        { type: 'gift', name: '小红', gift: 'beer', count: 2 },
        { type: 'nope', name: '非法' },
      ] }),
    });
    const data = await res.json();
    assert.equal(res.status, 200);
    assert.equal(data.accepted, 2);
    assert.deepEqual(data.rejected, ['nope']);
    assert.equal(seen.length, 2);
    assert.equal(seen[1].gift, 'beer');
  });
});

test('/ingest：GET 405、坏 JSON 400、超体积 413', async () => {
  await withServer(() => ({ accepted: 0, rejected: [] }), async port => {
    const get = await fetch(`http://127.0.0.1:${port}/ingest`);
    assert.equal(get.status, 405);

    const bad = await fetch(`http://127.0.0.1:${port}/ingest`, { method: 'POST', body: '{oops' });
    assert.equal(bad.status, 400);

    const huge = await fetch(`http://127.0.0.1:${port}/ingest`, {
      method: 'POST',
      body: JSON.stringify({ events: [{ type: 'comment', name: 'x'.repeat(LIMITS.bodyBytes), text: 'y' }] }),
    });
    assert.equal(huge.status, 413);
  });
});

test('/ingest：配置令牌后必须带 x-ingest-token', async () => {
  process.env.PRINTCAST_INGEST_TOKEN = 's3cret';
  try {
    await withServer(() => ({ accepted: 1, rejected: [] }), async port => {
      const denied = await fetch(`http://127.0.0.1:${port}/ingest`, {
        method: 'POST', body: JSON.stringify({ type: 'join', name: 'a' }),
      });
      assert.equal(denied.status, 401);
      const ok = await fetch(`http://127.0.0.1:${port}/ingest`, {
        method: 'POST',
        headers: { 'x-ingest-token': 's3cret' },
        body: JSON.stringify({ type: 'join', name: 'a' }),
      });
      assert.equal(ok.status, 200);
      assert.equal((await ok.json()).accepted, 1);
    });
  } finally {
    delete process.env.PRINTCAST_INGEST_TOKEN;
  }
});

test('/health：onHealth 附加字段与既有探测字段共存', async () => {
  await withServer(() => ({ accepted: 0, rejected: [] }), async port => {
    const res = await fetch(`http://127.0.0.1:${port}/health`);
    const data = await res.json();
    assert.equal(data.service, 'avatar-printer');
    assert.equal(typeof data.port, 'number');
  });
});
