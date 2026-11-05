// 展示端结构回归：唯一中文入口 + 工程化源码 + 入库产物。
// 防止有人把 100KB 内联脚本贴回 HTML，或绕过构建直接改产物。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import test from 'node:test';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const WEB = path.join(ROOT, 'web');
const SRC = path.join(ROOT, 'web-src');
const html = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8');

test('唯一展示入口：纯中文、无内联 style / module script', () => {
  assert.ok(html.includes('<html lang="zh-CN">'), '只保留纯净中文版');
  assert.ok(!/<style[^>]*>/.test(html), 'index.html 仍有内联 style');
  assert.ok(!/<script type="module">/.test(html), 'index.html 仍有内联 module script');
  assert.ok(html.length < 10_000, `index.html 体积 ${html.length}，疑似逻辑被塞回 HTML`);
  for (const gone of ['index-en.html', 'app.en.mjs', 'broadcast.html', 'live.html', 'site/']) {
    assert.ok(!html.includes(gone), `index.html 仍引用已下线的 ${gone}`);
  }
});

test('HTML 的样式与模块引用都能解析到入库产物', () => {
  const refs = [...html.matchAll(/(?:src|href)="([^"]+)"/g)].map((m) => m[1]);
  for (const ref of refs) {
    if (/^(https?:|data:|#)/.test(ref)) continue;
    assert.ok(fs.existsSync(path.resolve(WEB, ref.split('?')[0])), `引用了不存在的 ${ref}`);
  }
  assert.ok(html.includes('./app/app.js'), '入口未引用构建产物 app.js');
  assert.ok(html.includes('./app/app.css'), '入口未引用构建产物 app.css');
  assert.ok(fs.existsSync(path.join(WEB, 'settings-loader.js')), '统一设置入口丢失');
});

test('工程化源码按职责分片，且分层样式齐备', () => {
  const parts = fs.readdirSync(path.join(SRC, 'parts')).filter((f) => f.endsWith('.js')).sort();
  assert.deepEqual(parts, ['10-runtime.js', '20-scene.js', '30-printer.js', '40-panels.js']);
  for (const f of parts) {
    assert.ok(fs.statSync(path.join(SRC, 'parts', f)).size > 1000, `${f} 疑似空分片`);
  }
  for (const f of ['index.css', 'tokens.css', 'base.css', 'hud.css', 'theme-light.css']) {
    assert.ok(fs.existsSync(path.join(SRC, 'styles', f)), `缺少样式分层 ${f}`);
  }
  assert.ok(fs.existsSync(path.join(SRC, 'core', 'queue-policy.js')), '缺少队列策略真模块');
  assert.ok(fs.existsSync(path.join(SRC, 'imports.txt')), '缺少构建用 import 清单');
  assert.ok(fs.existsSync(path.join(ROOT, 'vite.config.js')), '缺少展示端构建配置');
  assert.ok(fs.existsSync(path.join(ROOT, 'scripts', 'build-display.sh')), '缺少构建脚本');
});

test('入库产物自包含且含浅色主题与 HUD 样式', () => {
  const js = fs.readFileSync(path.join(WEB, 'app', 'app.js'), 'utf8');
  const css = fs.readFileSync(path.join(WEB, 'app', 'app.css'), 'utf8');
  assert.ok(js.length > 100_000, `app.js 体积 ${js.length}，疑似构建不完整`);
  assert.ok(!/^import\s+.*\s+from\s+['"]/m.test(js), '产物仍残留裸 import，离线会 404');
  assert.ok(js.includes('window.__PC'), '产物未复用统一设置入口');
  assert.ok(css.includes('--pc-surface'), '产物缺少设计令牌');
  assert.ok(css.includes('html[data-theme="light"] .metric'), '浅色主题未覆盖数据读数');
  assert.ok(css.includes('#hud'), '产物缺少 HUD 样式');
  assert.ok(css.includes('@media(max-width:480px)'), '产物缺少小屏断点');
});
