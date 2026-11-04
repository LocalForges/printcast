// 结构回归：web/index*.html 只负责 DOM 与样式引用，逻辑必须住在 ES 模块里。
// 这条测试防止有人为了图方便又把 100KB 内联 script 贴回 HTML。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import test from 'node:test';

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../web');

const pairs = [
  ['index.html', 'app.zh.mjs'],
  ['index-en.html', 'app.en.mjs'],
];

test('HTML 只留骨架：无内联 style / 无内联 module script', () => {
  for (const [html] of pairs) {
    const s = fs.readFileSync(path.join(WEB, html), 'utf8');
    assert.ok(!/<style[^>]*>/.test(s), `${html} 仍有内联 style`);
    assert.ok(!/<script type="module">/.test(s), `${html} 仍有内联 module script`);
    assert.ok(s.length < 10_000, `${html} 体积 ${s.length}，疑似逻辑被塞回 HTML`);
  }
});

test('HTML 的样式与模块引用都能解析到本地文件', () => {
  for (const [html, mod] of pairs) {
    const s = fs.readFileSync(path.join(WEB, html), 'utf8');
    const refs = [...s.matchAll(/(?:src|href)="([^"]+)"/g)].map(m => m[1]);
    for (const ref of refs) {
      if (/^(https?:|data:|#)/.test(ref)) continue;
      const target = path.resolve(WEB, ref.split('?')[0]);
      assert.ok(fs.existsSync(target), `${html} 引用了不存在的 ${ref}`);
    }
    assert.ok(s.includes(`./${mod}`), `${html} 未引用 ${mod}`);
  }
});

test('共用 CSS 与两份语言模块都存在且非空', () => {
  const css = fs.readFileSync(path.join(WEB, 'app.css'), 'utf8');
  assert.ok(css.length > 3000, 'app.css 疑似内容缺失');
  for (const [, mod] of pairs) {
    const s = fs.readFileSync(path.join(WEB, mod), 'utf8');
    assert.ok(s.length > 80_000, `${mod} 体积 ${s.length}，疑似逻辑丢失`);
    assert.ok(s.includes('function solveArm('), `${mod} 缺少机械臂 IK`);
    assert.ok(s.includes('function preemptForGift('), `${mod} 缺少礼物插队`);
  }
});

test('ES 模块的相对 import 全部指向真实文件', () => {
  for (const [, mod] of pairs) {
    const s = fs.readFileSync(path.join(WEB, mod), 'utf8');
    const imports = [...s.matchAll(/(?:from|import)\s*['"]([^'"]+)['"]/g)].map(m => m[1]);
    const bare = new Set();
    for (const spec of imports) {
      if (!spec.startsWith('.')) { bare.add(spec); continue; }
      const target = path.resolve(WEB, spec.split('?')[0]);
      assert.ok(fs.existsSync(target), `${mod} 的 import ${spec} 找不到文件`);
    }
    // importmap 必须仍在 HTML 里声明裸模块名（three）
    const html = fs.readFileSync(path.join(WEB, mod === 'app.zh.mjs' ? 'index.html' : 'index-en.html'), 'utf8');
    for (const name of bare) {
      assert.ok(html.includes(`"${name}"`), `HTML 的 importmap 缺少 ${name} 声明`);
    }
  }
});
