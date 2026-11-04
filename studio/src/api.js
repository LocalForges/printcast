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

export const api = {
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
  // 出场顺序预览：GET /__api/schedule?pack=..&strategy=..&mode=..&count=..
  previewSchedule: ({ packs, strategy, mode, count }) => {
    const q = packs.map((p) => 'pack=' + encodeURIComponent(p)).join('&');
    const tail = []
      .concat(strategy ? ['strategy=' + strategy] : [])
      .concat(mode ? ['mode=' + mode] : [])
      .concat(count ? ['count=' + count] : [])
      .join('&');
    return req('GET', '/schedule' + (q ? '?' + q : '') + (q && tail ? '&' + tail : tail ? '?' + tail : ''));
  },
  // 出场广播控制：POST /__api/broadcast
  broadcast: (action, body = {}) => req('POST', '/broadcast', { json: { action, ...body } }),
  getBroadcast: () => req('GET', '/broadcast'),
  // 控制台设置（唯一可写配置来源；展示端只读）：GET/PUT /__api/settings
  getSettings: () => req('GET', '/settings'),
  saveSettings: (settings) => req('PUT', '/settings', { json: settings }),
};
