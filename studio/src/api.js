// 所有请求都打到同源主服务的 /__api/。浏览器对同源 fetch 自动带
// Sec-Fetch-Site: same-origin，因此后端鉴权天然通过；dev 模式下则由
// vite.config.js 的 proxy 把 /__api 转发到 :8080。
async function req(method, path, { json, body, headers } = {}) {
  const init = { method, headers: {} };
  if (headers) Object.assign(init.headers, headers);
  if (json !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(json);
  } else if (body !== undefined) {
    init.body = body;
  }
  const res = await fetch('/__api' + path, init);
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const message = (data && data.error) || (data && data.message) || res.statusText;
    const err = new Error(message);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

// 本机控制端点在 /__ 前缀下（不属于 /__api/），但同样走同源 fetch，
// 因此后端 _guard() 对本机页面天然放行。
async function localGet(path) {
  const res = await fetch(path);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const err = new Error((data && data.error) || res.statusText);
    err.status = res.status;
    throw err;
  }
  return data;
}

// 出场序列预演：GET /__api/schedule?pack=..&strategy=..&mode=..&seed=..&loop=..&count=..
// seed 固定后同一组参数必然复现同一条序列，工作台据此生成可分享的复现链接。
function scheduleQuery({ packs, strategy, mode, count, seed, loop }) {
  const q = (packs || []).map((p) => 'pack=' + encodeURIComponent(p)).join('&');
  const tail = []
    .concat(strategy ? ['strategy=' + encodeURIComponent(strategy)] : [])
    .concat(mode ? ['mode=' + encodeURIComponent(mode)] : [])
    .concat(seed !== undefined && seed !== null && seed !== '' ? ['seed=' + encodeURIComponent(seed)] : [])
    .concat(loop === true || loop === false ? ['loop=' + (loop ? 1 : 0)] : [])
    .concat(count ? ['count=' + encodeURIComponent(count)] : [])
    .join('&');
  return '/schedule' + (q ? '?' + q : '') + (q && tail ? '&' + tail : tail ? '?' + tail : '');
}

export const api = {
  scheduleQuery,
  getSchema: () => req('GET', '/schema'),
  getTemplate: (fmt) =>
    fetch('/__api/template.' + fmt).then((r) => r.blob()),
  listPacks: () => req('GET', '/packs'),
  getPack: (id) => req('GET', '/packs/' + id),
  savePack: (pack) => req('POST', '/packs', { json: pack }),
  deletePack: (id) => req('DELETE', '/packs/' + id),
  importData: (payload, commit) =>
    req('POST', '/import' + (commit ? '?commit=1' : ''), { json: payload }),
  listMedia: () => req('GET', '/media'),
  uploadMedia: (file) =>
    req('POST', '/media', { body: file, headers: { 'Content-Type': file.type || 'application/octet-stream', 'X-File-Name': encodeURIComponent(file.name) } }),
  deleteMedia: (id) => req('DELETE', '/media/' + id),
  previewSchedule: (params) => req('GET', scheduleQuery(params)),
  // 本机操作日志（控制台专属，展示端不调用）：读 / 清空。
  getAudit: ({ limit = 100, action = '', q = '' } = {}) => {
    const parts = []
      .concat(limit ? ['limit=' + encodeURIComponent(limit)] : [])
      .concat(action ? ['action=' + encodeURIComponent(action)] : [])
      .concat(q ? ['q=' + encodeURIComponent(q)] : []);
    return req('GET', '/audit' + (parts.length ? '?' + parts.join('&') : ''));
  },
  clearAudit: () => req('DELETE', '/audit'),
  // 出场广播控制：POST /__api/broadcast
  broadcast: (action, body = {}) => req('POST', '/broadcast', { json: { action, ...body } }),
  getBroadcast: () => req('GET', '/broadcast'),
  // 控制台设置（唯一可写配置来源；展示端只读）：GET/PUT /__api/settings
  getSettings: () => req('GET', '/settings'),
  saveSettings: (settings) => req('PUT', '/settings', { json: settings }),
  resetSettings: () => req('DELETE', '/settings'),
  // 控制台总览：一次拿到本机服务 / 数据桥 / 广播 / 资产计数。
  getStatus: () => req('GET', '/status'),
  // 数据桥启停、拉起展示窗口：后端已实现，控制台此前从未调用。
  startBridge: (room) => localGet('/__start-bridge' + (room ? '?room=' + encodeURIComponent(room) : '')),
  stopBridge: () => localGet('/__stop-bridge'),
  openScene: (path, orient = 'landscape') =>
    localGet('/__open-scene?path=' + encodeURIComponent(path) + '&orient=' + encodeURIComponent(orient)),
  openLive: (room, portrait = false) =>
    localGet('/__open-live?room=' + encodeURIComponent(room) + (portrait ? '&portrait=1' : '')),
};
