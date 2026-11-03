// 注入到直播间页面的采集脚本（Runtime.evaluate 执行）。
// 不依赖抖音混淆后的类名，全部按文本特征定位：弹幕行形态、头像 URL 特征、在线观众入口。

export const COLLECT = String.raw`(() => {
  const out = { likes: null, lines: [], avatars: {}, owner: '', href: location.href };
  const om = document.title.match(/^(.+?)的抖音直播间/);
  if (om) out.owner = om[1];
  for (const e of document.querySelectorAll('span,div,b,p')) {
    if (e.children.length) continue;
    const t = (e.textContent || '').replace(/\s+/g, ' ').trim();
    if (t && t.length < 20 && t.indexOf('本场点赞') >= 0) { const m = t.match(/([\d.]+)(万)?\s*本场点赞/); if (m) out.likes = Math.round(parseFloat(m[1]) * (m[2] ? 10000 : 1)); break; }
  }
  const single = t => /^.{1,24}[：:][^：:]{0,80}$/.test(t) || /^.{1,24}(送出|送了)\s*[^：:]{1,20}(\s*[xX×]\s*\d{1,3})?$/.test(t) || /^.{1,20}来了$/.test(t);
  const tick = (window.__scanTick = (window.__scanTick || 0) + 1);
  if (tick % 4 === 1 || !window.__chatRoot || !window.__chatRoot.isConnected) {
    let best = null, bestN = 0;
    for (const c of document.querySelectorAll('div')) {
      let n = 0;
      for (const k of c.children) { const t = (k.innerText || '').replace(/\s+/g, ' ').trim(); if (t && t.length <= 90 && single(t)) n++; }
      if (n > bestN) { bestN = n; best = c; }
    }
    window.__chatRoot = best;
  }
  const chatRoot = window.__chatRoot;
  const scope = chatRoot || document;
  const leaves = [...scope.querySelectorAll('span,div')].filter(e => !e.children.length);
  const seeds = leaves.filter(e => { const t = (e.textContent || '').replace(/\s+/g, ' ').trim(); return t && t.length <= 90 && (/[：:]/.test(t) || /(送出|送了)/.test(t) || /来了$/.test(t)); });
  const bestSet = new Set();
  for (const e of seeds) {
    let best = e;
    let n = e.parentElement;
    while (n && n !== document.body && (!chatRoot || chatRoot.contains(n))) {
      const t = (n.innerText || '').replace(/\s+/g, ' ').trim();
      if (t && t.length <= 90 && single(t)) { best = n; n = n.parentElement; } else break;
    }
    bestSet.add(best);
  }
  const chosen = [...bestSet].filter(a => ![...bestSet].some(b => b !== a && b.contains(a)));
  out.lines = chosen.map(n => (n.innerText || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
  if (tick % 2 === 0 || !window.__avMap) {
    const av = {};
    for (const img of document.querySelectorAll('img')) {
      const src = img.currentSrc || img.src || '';
      if (src.indexOf('douyinpic.com') < 0) continue;
      if (!/(aweme-avatar|tos-cn-avt|sc=avatar)/i.test(src)) continue;
      if (/grade_level|badge|medal|icon|\.svg|ranklist/i.test(src)) continue;
      let n = img.parentElement, name = '';
      for (let i = 0; i < 5 && n && !name; i++) {
        const t = (n.innerText || '').replace(/\s+/g, ' ').trim();
        if (/\d+\s*钻|充值|礼物周榜|小时榜|人气榜/.test(t) || t.length > 40) { n = n.parentElement; continue; }
        const m = t.match(/^([^：:\s]{1,24})/);
        if (m && m[1]) {
        const c = m[1].replace(/关注\d*粉丝\d*.*$/, '').replace(/\d{1,2}\/\d{1,2}.*$/, '').replace(/暂不支持.*$/, '').replace(/来了$/, '').replace(/\d+天前.*/, '').replace(/分享\[视频\]/, '').replace(/在线$/, '').trim();
        if (c.length >= 1 && c.length <= 20 && /[\u4e00-\u9fa5A-Za-z]/.test(c) && !/^用户\d{6,}$/.test(c) && !/^(送出了?|送了|来了|关注|粉丝|评论|分享)$/.test(c) && !/分享\[|前天|小时榜|人气榜|本场点赞|在线观众|贡献/.test(c)) name = c;
        }
        n = n.parentElement;
      }
      if (name && !av[name]) av[name] = src;
    }
    window.__avMap = av;
  }
  Object.assign(out.avatars, window.__avMap || {});
  if (tick % 40 === 7) {
    const hdr = [...document.querySelectorAll('div,span')].find(e => /在线观众/.test(e.textContent || '') && (e.textContent || '').length < 30);
    if (hdr) { for (const ty of ['mousedown', 'mouseup', 'click']) { try { hdr.dispatchEvent(new MouseEvent(ty, { bubbles: true, cancelable: true })) } catch (e) { } } }
  }
  if (tick % 8 === 0) {
    for (const d of document.querySelectorAll('div')) {
      if (chatRoot && (chatRoot.contains(d) || d.contains(chatRoot))) continue;
      if (d.scrollHeight > d.clientHeight + 60 && d.clientHeight > 80 && d.querySelectorAll('img').length >= 2) {
        if (!d.__scanDir) d.__scanDir = 1;
        d.scrollTop += d.__scanDir * 300;
        if (d.scrollTop + d.clientHeight >= d.scrollHeight - 4) d.__scanDir = -1;
        else if (d.scrollTop <= 0) d.__scanDir = 1;
      }
    }
  }
  return out;
})()`;
