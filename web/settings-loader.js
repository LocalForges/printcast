/*
 * 展示端共享装载器（只读）。
 * 职责边界：展示端只读取 /__api/settings，把控制台里的品牌 / 展示 / 公告 / 直播默认值
 * 渲染到页面上；绝不写入任何配置——写入只发生在控制台（Studio）经 /__api/settings PUT。
 *
 * 这是展示端唯一的配置入口：渲染模块通过 window.__PC.ready 复用同一份设置，
 * 不再各自 fetch，避免出现「有的端用了设置、有的端没用」的假参数化。
 */
(function () {
  function getPath(obj, path) {
    return path.split('.').reduce(function (o, k) { return (o == null ? o : o[k]); }, obj);
  }

  function bind(s) {
    if (!s) return;
    document.querySelectorAll('[data-bind], [data-bind-html]').forEach(function (el) {
      var htmlKey = el.getAttribute('data-bind-html');
      var key = htmlKey || el.getAttribute('data-bind');
      if (!key) return;
      var val = getPath(s, key);
      if (val == null) return;
      if (!htmlKey && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) {
        if (el.type !== 'checkbox' && el.type !== 'radio') el.value = val;
      } else if (htmlKey) {
        el.innerHTML = val;
      } else if (el.querySelector && el.querySelector('[data-links]')) {
        // 容器里还嵌着链接宿主（如 <footer>）时，只替换文本节点。
        // 直接 el.textContent = val 会把 [data-links] 整块删掉，控制台配的链接就永远不渲染。
        var texts = [], n;
        for (n = 0; n < el.childNodes.length; n++) {
          if (el.childNodes[n].nodeType === 3) texts.push(el.childNodes[n]);
        }
        if (texts.length) {
          for (n = 0; n < texts.length; n++) texts[n].nodeValue = n === 0 ? String(val) : '';
        } else {
          el.insertBefore(document.createTextNode(String(val)), el.firstChild);
        }
      } else {
        el.textContent = val;
      }
    });
  }

  function links(s) {
    var arr = getPath(s, 'branding.links');
    document.querySelectorAll('[data-links]').forEach(function (host) {
      host.innerHTML = '';
      if (!Array.isArray(arr)) return;
      arr.forEach(function (l) {
        if (!l || !l.href) return;
        var a = document.createElement('a');
        a.href = l.href;
        a.textContent = l.label || l.href;
        a.style.cssText = 'color:inherit;margin-left:10px;text-decoration:none';
        host.appendChild(a);
      });
    });
    return Array.isArray(arr) ? arr : [];
  }

  function apply(s) {
    if (!s) return;
    var b = s.branding || {}, d = s.display || {}, live = s.live || {};
    if (b.accent) document.documentElement.style.setProperty('--accent', b.accent);
    document.documentElement.setAttribute('data-theme', d.theme || 'dark');
    bind(s);
    var ls = links(s);

    // 「演示模式」徽标：完全由控制台开关决定，页面不写死。
    document.querySelectorAll('[data-demo-badge]').forEach(function (el) {
      el.hidden = d.showDemoBadge === false;
    });

    // 公告条：取代旧版硬编码的第三方广告条。文案与链接全部来自控制台，默认关闭。
    document.querySelectorAll('[data-announce]').forEach(function (host) {
      host.innerHTML = '';
      if (d.showAnnounce !== true) { host.hidden = true; return; }
      host.hidden = false;
      if (d.announceText) {
        var span = document.createElement('span');
        span.textContent = d.announceText;
        host.appendChild(span);
      }
      ls.forEach(function (l) {
        var a = document.createElement('a');
        a.href = l.href; a.textContent = l.label || l.href;
        host.appendChild(a);
      });
      if (!host.childNodes.length) host.hidden = true;
    });

    // 直播间号默认值：控制台设定，展示端只回填输入框（不写回任何配置）。
    if (live.defaultRoom) {
      document.querySelectorAll('[data-room-input]').forEach(function (el) {
        if (!el.value) el.value = live.defaultRoom;
      });
    }
  }

  var pc = { settings: null, ready: null, apply: apply };
  window.__PC = pc;

  // 脚本挂在 <head>：本地服务可能比 HTML 解析更快返回，必须等 DOM 就绪再绑定。
  var domReady = new Promise(function (resolve) {
    if (typeof document === 'undefined') return resolve();
    if (document.readyState !== 'loading' || !document.addEventListener) return resolve();
    document.addEventListener('DOMContentLoaded', resolve, { once: true });
  });

  var opts = {};
  if (typeof AbortSignal !== 'undefined' && AbortSignal.timeout) {
    try { opts.signal = AbortSignal.timeout(4000); } catch (e) {}
  }
  var fetched = fetch('/__api/settings', opts)
    .then(function (r) { return r.ok ? r.json() : null; })
    // /__api/settings 返回 {ok, settings}，必须取出 settings 才是配置本体。
    .then(function (d) { return (d && d.settings) || null; })
    .catch(function () { return null; });

  pc.ready = Promise.all([fetched, domReady]).then(function (both) {
    var s = both[0];
    pc.settings = s;
    apply(s);
    return s;
  });
})();
