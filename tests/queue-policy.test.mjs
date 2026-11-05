// 队列策略是真 ES 模块：浏览器与 Node 共用同一份实现，不再靠切源码字符串验证。
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  QUEUE_LIMIT, shouldEnqueue, remember,
  describeAppearanceProgress, describePrintProgress,
} from '../web-src/core/queue-policy.js';

test('队列有硬上限，防止剧本 5 秒节拍叠加后无限堆积', () => {
  const seen = new Set();
  assert.equal(shouldEnqueue({ length: QUEUE_LIMIT - 1, seen, key: 'x' }).ok, true);
  const full = shouldEnqueue({ length: QUEUE_LIMIT, seen, key: 'y' });
  assert.equal(full.ok, false);
  assert.equal(full.reason, 'full');
  assert.equal(shouldEnqueue({ length: 40, seen, key: 'z', limit: 2 }).reason, 'full');
});

test('同一出场序号只入队一次，seen 集合有上界', () => {
  const seen = new Set();
  assert.equal(shouldEnqueue({ length: 0, seen, key: 'seq:7' }).ok, true);
  remember(seen, 'seq:7');
  assert.equal(shouldEnqueue({ length: 1, seen, key: 'seq:7' }).reason, 'duplicate');
  assert.equal(shouldEnqueue({ length: 1, seen, key: null }).ok, true, '无序号时不误判重复');
  for (let i = 0; i < 600; i++) remember(seen, 'seq:' + i, 32);
  assert.ok(seen.size <= 32, 'seen 必须设上界');
  assert.equal(shouldEnqueue({ length: -1, seen }).reason, 'invalid');
});

test('出场进度与打印进度是两个概念，文案不得混用', () => {
  assert.equal(describeAppearanceProgress({ seq: 3, total: 24, round: 2 }), '第 3 位 · 共 24 位 · 第 2 轮');
  assert.equal(describeAppearanceProgress(), '尚未开播');
  assert.equal(describePrintProgress({ name: '张三', percent: 42, phase: 'printing' }), '当前：张三 · 打印中 42%');
  assert.equal(describePrintProgress({ name: '张三', phase: 'transfer' }), '当前：张三 · 出分转运');
  assert.equal(describePrintProgress({ phase: 'idle' }), '待命');
});
