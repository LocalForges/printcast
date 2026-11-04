// 展示端设置契约回归：settings-loader.js 是展示端唯一的配置入口。
// 用最小 DOM 桩在 Node 里跑真实脚本，锁死以下边界，防止「假参数化」回潮：
//   1. /__api/settings 返回 {ok, settings}，必须取出 settings 本体；
//   2. 展示端只 GET、绝不 PUT/POST；
//   3. 品牌 / 主题 / 徽标 / 公告 / 直播默认值全部由控制台驱动。
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import test from 'node:test';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const WEB = path.join(ROOT, 'web');
const SOURCE = fs.readFileSync(path.join(WEB, 'settings-loader.js'), 'utf8');

function el(tag, attrs = {}) {
  const node = {
    tagName: tag.toUpperCase(), attrs, style: { cssText: '' },
    childNodes: [], hidden: false, value: '', textContent: '', href: '',
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    appendChild(c) { this.childNodes.push(c); return c; },
    insertBefore(c, ref) { const i = ref ? this.childNodes.indexOf(ref) : -1;
      this.childNodes.splice(i < 0 ? this.childNodes.length : i, 0, c); return c; },
    querySelector(sel) {
      if (sel !== '[data-links]') return null;
      return this.childNodes.find((c) => c.attrs && c.attrs['data-links'] !== undefined) || null;
    },
  };
  let html = '';
  Object.defineProperty(node, 'innerHTML', {
    get() { return html; },
    set(v) { html = String(v); if (html === '') node.childNodes = []; },
  });
  return node;
}

function run(settings, nodes = {}) {
  const calls = [];
  const rootStyle = { props: {}, setProperty(k, v) { this.props[k] = v; } };
  const rootAttrs = {};
  const all = {
    '[data-bind], [data-bind-html]': nodes.bind || [],
    '[data-links]': nodes.links || [],
    '[data-demo-badge]': nodes.badge || [],
    '[data-announce]': nodes.announce || [],
    '[data-room-input]': nodes.room || [],
  };
  const document = {
    documentElement: { style: rootStyle, setAttribute(k, v) { rootAttrs[k] = v; }, attrs: rootAttrs },
    querySelectorAll(sel) { return all[sel] || []; },
    createElement(tag) { return el(tag); },
    createTextNode(text) { return { nodeType: 3, nodeValue: String(text) }; },
  };
  const sandbox = {
    document,
    console,
    Promise,
    fetch(url, opts) {
      calls.push({ url, opts });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, settings }) });
    },
  };
  sandbox.window = sandbox; // window.__PC 落回 sandbox 本身
  vm.runInNewContext(SOURCE, sandbox, { filename: 'settings-loader.js' });
  return { pc: sandbox.__PC, calls, rootStyle, rootAttrs, ready: sandbox.__PC.ready };
}

const BASE = {
  branding: {
    title: '控制台命名', subtitle: '副标题来自控制台', accent: '#ff654f',
    footer: '页脚 <b>来自控制台</b>',
    links: [{ label: '教程', href: '/site/guide.html' }],
  },
  display: {
    theme: 'light', overlayText: 'OVERRIDE', overlaySub: '来自控制台的副文案',
    showDemoBadge: false, showAnnounce: false, announceText: '',
  },
  live: { defaultRoom: '123456', platform: 'douyin' },
};

test('取出 settings 本体，且只发一次 GET（不写配置）', async () => {
  const { pc, calls, ready } = run(BASE);
  const s = await ready;
  assert.deepEqual(s, BASE, 'window.__PC.ready 必须解析为 settings 本体，而不是整个响应');
  assert.equal(pc.settings, s);
  assert.equal(calls.length, 1, '展示端只应请求一次');
  assert.equal(calls[0].url, '/__api/settings');
  assert.ok(!calls[0].opts || !calls[0].opts.method, '不得使用 PUT/POST 等写方法');
});

test('品牌 / 主题 / 链接全部按控制台值渲染', async () => {
  const bound = el('h1', { 'data-bind': 'branding.title' });
  const sub = el('span', { 'data-bind': 'display.overlaySub' });
  const htmlBound = el('span', { 'data-bind-html': 'branding.footer' });
  const linksHost = el('span', { 'data-links': '' });
  const { rootStyle, rootAttrs, ready } = run(BASE, { bind: [bound, sub, htmlBound], links: [linksHost] });
  await ready;
  assert.equal(bound.textContent, '控制台命名');
  assert.equal(sub.textContent, '来自控制台的副文案');
  assert.equal(htmlBound.innerHTML, '页脚 <b>来自控制台</b>', 'data-bind-html 单独存在时也必须生效');
  assert.equal(rootStyle.props['--accent'], '#ff654f');
  assert.equal(rootAttrs['data-theme'], 'light');
  assert.equal(linksHost.childNodes.length, 1);
  assert.equal(linksHost.childNodes[0].href, '/site/guide.html');
  assert.equal(linksHost.childNodes[0].textContent, '教程');
});

test('页脚容器含 [data-links] 时，绑定文本不得删掉链接宿主', async () => {
  const footer = el('footer', { 'data-bind': 'branding.footer' });
  const textNode = { nodeType: 3, nodeValue: '旧页脚' };
  const linksHost = el('span', { 'data-links': '' });
  footer.childNodes = [textNode, linksHost];
  const { ready } = run(BASE, { bind: [footer], links: [linksHost] });
  await ready;
  assert.equal(textNode.nodeValue, '页脚 <b>来自控制台</b>');
  assert.ok(footer.childNodes.includes(linksHost), '链接宿主必须保留');
  assert.equal(linksHost.childNodes.length, 1, '控制台链接仍须渲染');
  assert.equal(linksHost.childNodes[0].href, '/site/guide.html');
});

test('展示页页脚把 data-bind 与 data-links 拆成兄弟节点', () => {
  for (const f of ['index.html', 'index-en.html']) {
    const s = fs.readFileSync(path.join(WEB, f), 'utf8');
    assert.ok(!/<footer[^>]*data-bind/.test(s),
      `${f} 的 footer 不应直接带 data-bind（整块 textContent 会删掉链接容器）`);
  }
});

test('showDemoBadge=false 隐藏徽标；showAnnounce=false 隐藏公告条', async () => {
  const badge = el('div', { 'data-demo-badge': '' });
  const announce = el('div', { 'data-announce': '' });
  badge.hidden = false; announce.hidden = false;
  const { ready } = run(BASE, { badge: [badge], announce: [announce] });
  await ready;
  assert.equal(badge.hidden, true);
  assert.equal(announce.hidden, true);
  assert.equal(announce.childNodes.length, 0, '关闭时不得残留任何内容');
});

test('公告条开启时，文案与链接全部来自控制台（页面无硬编码内容）', async () => {
  const announce = el('div', { 'data-announce': '' });
  const cfg = { ...BASE, display: { ...BASE.display, showAnnounce: true, announceText: '本次直播由控制台配置' } };
  const { ready } = run(cfg, { announce: [announce] });
  await ready;
  assert.equal(announce.hidden, false);
  assert.equal(announce.childNodes[0].textContent, '本次直播由控制台配置');
  assert.equal(announce.childNodes[1].href, '/site/guide.html');
  assert.equal(announce.childNodes[1].textContent, '教程');
});

test('live.defaultRoom 只回填空输入框，不覆盖用户已填内容', async () => {
  const empty = el('input', { 'data-room-input': '' });
  const filled = el('input', { 'data-room-input': '' });
  filled.value = '999999';
  const { ready } = run(BASE, { room: [empty, filled] });
  await ready;
  assert.equal(empty.value, '123456');
  assert.equal(filled.value, '999999');
});

test('静态页面不含硬编码第三方广告 / 微信号 / 水印', () => {
  for (const f of ['index.html', 'index-en.html', 'broadcast.html', 'live-view.html']) {
    const s = fs.readFileSync(path.join(WEB, f), 'utf8');
    for (const bad of ['志哥AI', 'xfak888888899999', '17398730078', 'wx-copy.js', 'ad-strip']) {
      assert.ok(!s.includes(bad), `${f} 仍残留 ${bad}`);
    }
  }
  for (const f of ['features.html', 'guide.html']) {
    const s = fs.readFileSync(path.join(ROOT, 'site', f), 'utf8');
    for (const bad of ['志哥AI', 'xfak888888899999', '17398730078', 'wx-copy.js', 'class="wm"']) {
      assert.ok(!s.includes(bad), `${f} 仍残留 ${bad}`);
    }
  }
});

test('展示端不含任何配置写入；控制命令只在控制台', () => {
  for (const f of ['index.html', 'index-en.html', 'broadcast.html', 'live-view.html']) {
    const s = fs.readFileSync(path.join(WEB, f), 'utf8');
    assert.ok(!/__api\/settings\s*['"]?\s*,\s*\{?\s*method\s*:\s*['"]PUT/i.test(s),
      `${f} 不得写 /__api/settings`);
  }
  const bc = fs.readFileSync(path.join(WEB, 'broadcast.html'), 'utf8');
  assert.ok(!bc.includes('action:'), 'broadcast.html 是只读展示页，不应包含广播控制命令');
  assert.ok(!/method\s*:\s*['"]POST/.test(bc), 'broadcast.html 不得 POST');
  // 两个渲染模块必须复用同一份设置（避免各自 fetch / 丢 settings 层）。
  for (const f of ['app.zh.mjs', 'app.en.mjs']) {
    const s = fs.readFileSync(path.join(WEB, f), 'utf8');
    assert.ok(s.includes('window.__PC.ready'), `${f} 未复用统一设置入口`);
    assert.ok(s.includes('printRules'), `${f} 未应用 printer 规则`);
  }
});
