<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { api } from './api.js';

// —— 工作台外观（独立于展示端 display.theme，属于控制台自己的偏好）——
const theme = ref('dark');
try { theme.value = localStorage.getItem('printcast.studio.theme') || 'dark'; } catch (e) {}
watch(theme, (v) => {
  document.documentElement.dataset.theme = v;
  try { localStorage.setItem('printcast.studio.theme', v); } catch (e) {}
}, { immediate: true });

const VIEWS = {
  overview: { title: '头像打印', desc: '实时打印状态、内容源切换与一键干预' },
  broadcast: { title: '剧本播放', desc: '作为「头像打印」的内容源：启动剧本播放，讲到谁就打谁' },
  packs: { title: '内容包', desc: '管理已导入的角色内容包' },
  import: { title: '数据导入', desc: '下载模板、校验并导入 CSV / JSON' },
  media: { title: '图片资源', desc: '上传与清理头像贴图' },
  schedule: { title: '排期预演', desc: '时间轴复现、固定 seed 与本地预演' },
  settings: { title: '控制台设置', desc: '唯一可写配置来源，右侧实时预览展示端' },
  system: { title: '系统', desc: '数据桥、展示窗口与运行信息' },
  audit: { title: '操作日志', desc: '本机写操作可回溯，按动作与关键词筛选' },
};
const NAV = [
  { group: '运行', items: ['overview', 'broadcast'] },
  { group: '资产', items: ['packs', 'import', 'media'] },
  { group: '编排', items: ['schedule'] },
  { group: '配置', items: ['settings', 'system', 'audit'] },
];
// 内容源切换：头像打印既可由「实时直播」驱动，也可由「剧本播放」驱动；
// 二者共用同一台 3D 打印机与画面，不再各做一套。
const contentSource = ref('script'); // 'script' = 剧本播放；'live' = 实时直播
const activeView = ref('overview');
const viewMeta = computed(() => VIEWS[activeView.value] || VIEWS.overview);
function go(view) { activeView.value = view; }

// —— P1：动作中文名（操作日志由服务端埋点，前端只负责展示）——
const AUDIT_LABELS = {
  'settings.update': '更新控制台设置', 'settings.reset': '恢复出厂设置',
  'pack.save': '保存内容包', 'pack.delete': '删除内容包', 'pack.import': '导入内容包',
  'media.upload': '上传图片', 'media.delete': '删除图片', 'audit.clear': '清空操作日志',
  'broadcast.start': '启动广播', 'broadcast.next': '推进下一个',
  'broadcast.trigger': '点名出场', 'broadcast.reset': '重置广播', 'broadcast.plan': '预演序列',
  'bridge.start': '启动数据桥', 'bridge.stop': '停止数据桥',
  'scene.open': '打开打印台窗口', 'live.open': '打开直播窗口',
};
function auditLabel(action) { return AUDIT_LABELS[action] || action; }
function fmtTime(at) {
  if (!at) return '—';
  const d = new Date(at);
  return isNaN(d.getTime()) ? at : d.toLocaleString('zh-CN', { hour12: false });
}
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function downloadJson(filename, value) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
// seed 一律以字符串交给后端，由后端 normalize_seed() 单点归一化。
// 早期前端把纯数字转 Number：一是 URL 与 JSON 两条入口类型不一致会让
// 「预演序列 ≠ 按此配置开播」，二是 JS 双精度在 >2^53 时会丢精度。
function normalizeSeed(value) {
  const s = String(value === undefined || value === null ? '' : value).trim();
  return s || undefined;
}
async function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      document.execCommand('copy'); ta.remove();
    }
    flash('已复制到剪贴板');
  } catch (e) { flash('复制失败，请手动复制下方参数：' + e.message, true); }
}

// —— 基础数据 ——
const schema = ref(null);
const limits = ref({});
const packs = ref([]);
const media = ref([]);
const message = ref('');
const error = ref('');
let flashTimer = null;
function flash(msg, isError = false) {
  if (isError) { error.value = msg; message.value = ''; }
  else { message.value = msg; error.value = ''; }
  if (flashTimer) clearTimeout(flashTimer);
  flashTimer = setTimeout(() => { message.value = ''; error.value = ''; }, 4000);
}

// —— 后端连接与总览状态 ——
const connection = reactive({ ok: null, host: '', detail: '正在检测本机服务…' });
const status = ref(null);
const statusError = ref('');
const nowSec = ref(Math.floor(Date.now() / 1000));
let statusTimer = null;

// 2s 定时轮询与写操作后的手动刷新会并发；用单调递增序号丢弃过期响应，
// 避免「先发的慢请求后返回」把新状态覆盖掉。
let statusSeq = 0;
async function refreshStatus() {
  const seq = ++statusSeq;
  nowSec.value = Math.floor(Date.now() / 1000);
  connection.host = location.host || '(未知)';
  try {
    const data = await api.getStatus();
    if (seq !== statusSeq) return;
    status.value = data;
    statusError.value = '';
    connection.ok = true;
    connection.detail = '本机服务已连通 · 端口 ' + data.service.port;
  } catch (e) {
    if (seq !== statusSeq) return;
    status.value = null;
    statusError.value = e.message || '无法连接';
    connection.ok = false;
    connection.detail = 'HTTP ' + (e.status || '?') + ' · ' + statusError.value;
  }
}

const bcState = computed(() => (status.value && status.value.broadcast) || { active: false });
const bcPlaying = computed(() => !!(bcState.value && bcState.value.playing));
const lights = computed(() => [
  { key: 'service', label: '本机服务', on: !!status.value, detail: status.value ? '端口 ' + status.value.service.port : '未连通' },
  { key: 'bridge', label: '数据桥', on: !!(status.value && status.value.bridge && status.value.bridge.ok),
    detail: status.value && status.value.bridge && status.value.bridge.ok ? status.value.bridge.url : '未启动' },
  { key: 'broadcast', label: '剧本播放', on: !!bcState.value.active,
    detail: bcState.value.active ? '进行中 · 已出场 ' + (bcState.value.seq || 0) : '待机' },
]);
const currentChar = computed(() => bcState.value.current || null);
const counts = computed(() => (status.value && status.value.counts) || { packs: packs.value.length, media: media.value.length });
const runtimeText = computed(() => {
  const started = bcState.value.startedAt;
  if (!started) return '';
  const s = Math.max(0, nowSec.value - Math.floor(started));
  const m = Math.floor(s / 60);
  return m >= 60 ? Math.floor(m / 60) + ' 小时 ' + (m % 60) + ' 分' : m + ' 分 ' + (s % 60) + ' 秒';
});

// —— 实时事件流：订阅 SceneRelay 长轮询，只读，不发布 ——
const events = ref([]);
let eventAbort = null;
let eventCursor = null;
let eventRunning = false;

function eventText(m) {
  if (!m) return '空消息';
  if (m.type === 'view-appearance') {
    const ap = m.appearance || {};
    return '出场 ' + (ap.name || ap.id || '未知角色') + ' · 已推入打印队列';
  }
  if (m.type === 'view-ping') return '场景心跳';
  return '信令 ' + (m.type || 'unknown');
}
function clockText() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false });
}
let eventGeneration = 0;
async function eventLoop(generation) {
  const client = 'studio-' + Math.random().toString(36).slice(2, 10);
  while (eventRunning && generation === eventGeneration) {
    try {
      const q = '/__scene-events?client=' + encodeURIComponent(client) +
        (eventCursor === null ? '' : '&after=' + eventCursor);
      const res = await fetch(q, { signal: eventAbort.signal });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      if (!eventRunning || generation !== eventGeneration) break;
      eventCursor = data.cursor;
      const list = data.messages || [];
      for (let i = list.length - 1; i >= 0; i--) {
        events.value.unshift({ time: clockText(), text: eventText(list[i]) });
      }
      if (events.value.length > 40) events.value.length = 40;
    } catch (e) {
      if (!eventRunning || generation !== eventGeneration) break;
      await new Promise((r) => setTimeout(r, 1500));
    }
  }
}
function startEventLoop() {
  if (eventRunning) return;  // 防重复挂载时启动多个共享同一 AbortController 的循环
  eventAbort = new AbortController();
  eventRunning = true;
  eventGeneration += 1;
  eventCursor = null;
  eventLoop(eventGeneration);
}
function stopEventLoop() {
  eventRunning = false;
  eventGeneration += 1;
  if (eventAbort) eventAbort.abort();
}

async function loadMeta() {
  try {
    const data = await api.getSchema();
    schema.value = data.schema;
    limits.value = data.schema.limits || {};
  } catch (e) { error.value = '读取字段定义失败：' + e.message; }
}
async function loadPacks() {
  try { packs.value = (await api.listPacks()).packs || []; }
  catch (e) { error.value = e.message; }
}
async function loadMedia() {
  try { media.value = (await api.listMedia()).media || []; }
  catch (e) { error.value = e.message; }
}

// —— 内容包 / 模板 / 导入 / 图片 ——
const fileInput = ref(null);
const csvText = ref('');
const csvFileName = ref('');
const packMeta = reactive({ id: '', title: '', mode: 'sequence' });
const commit = ref(true);
const importResult = ref(null);
const importing = ref(false);
const pendingConfirm = ref(null);

function ask(kind, id) { pendingConfirm.value = { kind, id }; }
async function confirmPending() {
  const c = pendingConfirm.value;
  pendingConfirm.value = null;
  if (!c) return;
  if (c.kind === 'pack') await removePack(c.id);
  else if (c.kind === 'media') await removeMedia(c.id);
  else if (c.kind === 'reset-settings') await applyResetSettings();
  else if (c.kind === 'reset-broadcast') await bcReset();
  else if (c.kind === 'clear-audit') await clearAudit();
}

// —— P1：内容包搜索 / 排序 / 抽屉编辑 / 复制 / 导入导出 ——
// 所有写操作都走既有的 /__api/packs 与 /__api/import，后端会逐字段校验；
// 抽屉只负责编辑表单，不另造一套数据模型。
const packQuery = ref('');
const packSort = ref('title');
const filteredPacks = computed(() => {
  const q = packQuery.value.trim().toLowerCase();
  const list = packs.value.filter((p) =>
    !q || (String(p.id) + ' ' + String(p.title)).toLowerCase().includes(q));
  const key = packSort.value;
  return [...list].sort((a, b) => {
    if (key === 'count') return (b.count || 0) - (a.count || 0);
    if (key === 'updated') return String(b.updated || '').localeCompare(String(a.updated || ''));
    return String(a[key] || '').localeCompare(String(b[key] || ''), 'zh-CN');
  });
});

const drawer = ref(null);            // { mode, original, draft, sourceId }
const drawerBusy = ref(false);
const drawerErrors = ref([]);
const drawerConfirmClose = ref(false);
const packImportInput = ref(null);
const packImportResult = ref(null);
const drawerDirty = computed(() => drawer.value
  ? JSON.stringify(drawer.value.draft) !== drawer.value.original : false);

// schema 的 tags 字段把「分号/逗号字符串」规范化成数组。若把数组原样 POST 回去，
// 会被 str(list) 变成脏标签（M0 踩过的坑）。保存/导出/导入前统一转回字符串。
function normalizePackForSave(pack) {
  const out = clone(pack);
  delete out.updated;
  (out.characters || []).forEach((c) => {
    if (Array.isArray(c.tags)) c.tags = c.tags.join(';');
  });
  return out;
}
function editTags(c) {
  if (Array.isArray(c.tags)) c.tags = c.tags.join(';');
  else if (c.tags == null) c.tags = '';
}
function charAvatar(c) {
  const a = c && c.avatar;
  return typeof a === 'string' && /^[a-f0-9]{12}\.(png|jpe?g|webp)$/.test(a)
    ? '/media/' + a : null;
}
function tagsText(c) {
  const t = c && c.tags;
  return Array.isArray(t) ? t.join(' / ') : (t || '—');
}

async function openPack(id) {
  drawerBusy.value = true;
  drawerErrors.value = [];
  drawerConfirmClose.value = false;
  try {
    const data = await api.getPack(id);
    if (!data.pack) throw new Error('内容包不存在');
    const draft = clone(data.pack);
    if (!draft.characters) draft.characters = [];
    draft.characters.forEach(editTags);
    if (!draft.mode) draft.mode = 'sequence';
    draft.loop = !!draft.loop;
    if (!draft.description) draft.description = '';
    drawer.value = {
      mode: 'view', original: JSON.stringify(draft),
      draft, sourceId: id,
    };
  } catch (e) { flash('读取内容包失败：' + e.message, true); }
  finally { drawerBusy.value = false; }
}
function requestCloseDrawer() {
  if (drawerDirty.value) { drawerConfirmClose.value = true; return; }
  closeDrawer();
}
function closeDrawer() {
  drawer.value = null;
  drawerErrors.value = [];
  drawerConfirmClose.value = false;
}
function startEdit() {
  if (!drawer.value) return;
  drawer.value.mode = 'edit';
  drawer.value.original = JSON.stringify(drawer.value.draft);
  drawerErrors.value = [];
}
function cancelEdit() {
  if (!drawer.value) return;
  drawer.value.draft = JSON.parse(drawer.value.original);
  drawer.value.mode = 'view';
  drawerErrors.value = [];
}
function addCharacter() {
  const chars = drawer.value.draft.characters || (drawer.value.draft.characters = []);
  chars.push({ id: 'char-' + (chars.length + 1), name: '新角色',
    order: chars.length + 1, weight: 1, tags: '', speech: '', avatar: '' });
}
function removeCharacter(i) { drawer.value.draft.characters.splice(i, 1); }
function moveCharacter(i, delta) {
  const chars = drawer.value.draft.characters;
  const j = i + delta;
  if (j < 0 || j >= chars.length) return;
  const tmp = chars[i]; chars[i] = chars[j]; chars[j] = tmp;
  chars.forEach((c, k) => { c.order = k + 1; });
}
async function saveDrawer() {
  if (!drawer.value) return;
  drawerBusy.value = true;
  drawerErrors.value = [];
  try {
    const payload = normalizePackForSave(drawer.value.draft);
    await api.savePack(payload);
    flash('内容包已保存：' + payload.id);
    closeDrawer();
    await Promise.all([loadPacks(), refreshStatus(), loadAudit()]);
  } catch (e) {
    drawerErrors.value = (e.data && e.data.errors) || [{ message: e.message }];
    flash('保存失败：' + e.message, true);
  } finally { drawerBusy.value = false; }
}
async function duplicatePack(p) {
  try {
    const data = await api.getPack(p.id);
    if (!data.pack) throw new Error('内容包不存在');
    const copy = normalizePackForSave(data.pack);
    const existing = new Set(packs.value.map((x) => x.id));
    let id = (p.id + '-copy').slice(0, 64), n = 2;
    while (existing.has(id)) id = (p.id + '-copy-' + n++).slice(0, 64);
    copy.id = id;
    copy.title = (copy.title || p.title || p.id) + ' 副本';
    await api.savePack(copy);
    flash('已复制为 ' + id);
    await Promise.all([loadPacks(), refreshStatus(), loadAudit()]);
  } catch (e) { flash('复制失败：' + e.message, true); }
}
async function exportPack(p) {
  try {
    const data = await api.getPack(p.id);
    if (!data.pack) throw new Error('内容包不存在');
    downloadJson(p.id + '.json', normalizePackForSave(data.pack));
    flash('已导出 ' + p.id + '.json');
  } catch (e) { flash('导出失败：' + e.message, true); }
}
function onPackFile(e) {
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  packImportResult.value = null;
  const reader = new FileReader();
  reader.onload = async () => {
    let obj;
    try { obj = JSON.parse(reader.result); }
    catch (err) {
      packImportResult.value = { ok: false, error: 'JSON 解析失败：' + err.message };
      return;
    }
    if (!obj || typeof obj !== 'object' || !Array.isArray(obj.characters)) {
      packImportResult.value = { ok: false, error: '不是内容包 JSON（缺少 characters 数组）' };
      return;
    }
    const clean = normalizePackForSave(obj);
    try {
      const data = await api.importData({ format: 'json', pack: {}, content: clean }, true);
      packImportResult.value = {
        ok: !!data.ok, error: data.error, errors: data.errors || [],
        stats: data.stats, committed: data.committed, pack: data.pack,
      };
      if (data.ok) {
        flash('已导入内容包 ' + clean.id);
        await Promise.all([loadPacks(), refreshStatus(), loadAudit()]);
      } else flash('导入未通过校验，未写入任何数据', true);
    } catch (err) {
      packImportResult.value = {
        ok: false, error: err.message,
        errors: (err.data && err.data.errors) || [],
      };
      flash('导入失败：' + err.message, true);
    }
  };
  reader.readAsText(f, 'utf-8');
  e.target.value = '';
}

async function downloadTemplate(fmt) {
  try {
    const blob = await api.getTemplate(fmt);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'printcast-template.' + fmt; a.click();
    URL.revokeObjectURL(url);
    flash('模板已下载：printcast-template.' + fmt);
  } catch (e) { flash('下载失败：' + e.message, true); }
}
function onFile(e) {
  const f = e.target.files[0];
  if (!f) return;
  csvFileName.value = f.name;
  const reader = new FileReader();
  reader.onload = () => { csvText.value = reader.result; };
  reader.readAsText(f, 'utf-8');
}
async function runImport() {
  if (!packMeta.id || !packMeta.title) { flash('请先填写内容包 ID 与标题', true); return; }
  importing.value = true; importResult.value = null;
  try {
    const data = await api.importData({
      format: 'csv',
      pack: { id: packMeta.id, title: packMeta.title, mode: packMeta.mode },
      content: csvText.value,
    }, commit.value);
    importResult.value = data;
    if (data.ok) {
      flash(commit.value ? '导入成功并已保存' : '校验通过，未保存');
      await Promise.all([loadPacks(), refreshStatus(), loadAudit()]);
      csvText.value = ''; csvFileName.value = '';
    } else {
      flash('校验未通过：' + (data.errors || []).length + ' 处错误，未写入', true);
    }
  } catch (e) { flash('导入失败：' + e.message, true); }
  finally { importing.value = false; }
}
async function removePack(id) {
  try {
    await api.deletePack(id); flash('已删除 ' + id);
    if (drawer.value && drawer.value.sourceId === id) closeDrawer();
    await Promise.all([loadPacks(), refreshStatus(), loadAudit()]);
  } catch (e) { flash('删除失败：' + e.message, true); }
}
async function upload() {
  const f = fileInput.value && fileInput.value.files && fileInput.value.files[0];
  if (!f) { flash('请选择图片', true); return; }
  try {
    const rec = await api.uploadMedia(f);
    flash('上传成功：' + rec.media.name);
    fileInput.value.value = '';
    await Promise.all([loadMedia(), refreshStatus(), loadAudit()]);
  } catch (e) { flash('上传失败：' + e.message, true); }
}
async function removeMedia(id) {
  try {
    await api.deleteMedia(id); flash('已删除图片');
    await Promise.all([loadMedia(), refreshStatus(), loadAudit()]);
  } catch (e) { flash('删除失败：' + e.message, true); }
}

// —— P1：出场序列时间轴 / 固定 seed 复现 / 本地预演 ——
const schedPacks = ref([]);
const schedStrategy = ref('concat');
const schedMode = ref('');
const schedCount = ref(20);
const schedSeed = ref('');
const schedLoop = ref('');       // '' 跟随内容包设置；'1' / '0' 强制覆盖
const schedResult = ref(null);
const schedLoading = ref(false);
const tlSelected = ref(-1);
const tlPlaying = ref(false);
const tlIndex = ref(-1);
let tlTimer = null;

const schedParams = computed(() => ({
  packs: schedPacks.value,
  strategy: schedStrategy.value,
  mode: schedMode.value || undefined,
  count: schedCount.value || undefined,
  seed: schedSeed.value === '' ? undefined : schedSeed.value,
  loop: schedLoop.value === '' ? undefined : schedLoop.value === '1',
}));
const schedUrl = computed(() => location.origin + '/__api' + api.scheduleQuery(schedParams.value));
const schedAppearances = computed(() => (schedResult.value && schedResult.value.appearances) || []);

let schedSeq = 0;
async function previewSchedule() {
  if (!schedPacks.value.length) { flash('请至少选择一个内容包', true); return; }
  stopRehearsal();
  const seq = ++schedSeq;
  schedLoading.value = true;
  try {
    const data = await api.previewSchedule(schedParams.value);
    if (seq !== schedSeq) return;  // 连点两次时只接受最后一次
    schedResult.value = data;
    tlSelected.value = data.appearances && data.appearances.length ? 0 : -1;
    flash('已生成出场序列，共 ' + (data.appearances || []).length + ' 个');
  } catch (e) { if (seq === schedSeq) flash('预览失败：' + e.message, true); }
  finally { if (seq === schedSeq) schedLoading.value = false; }
}
function stopRehearsal() {
  tlPlaying.value = false;
  if (tlTimer) { clearInterval(tlTimer); tlTimer = null; }
}
function toggleRehearsal() {
  if (tlPlaying.value) { stopRehearsal(); return; }
  if (!schedAppearances.value.length) { flash('请先生成出场序列', true); return; }
  tlPlaying.value = true;
  tlIndex.value = 0;
  tlTimer = setInterval(() => {
    if (tlIndex.value >= schedAppearances.value.length - 1) { stopRehearsal(); return; }
    tlIndex.value += 1;
    tlSelected.value = tlIndex.value;
    const el = document.querySelector('.tl-card.is-current');
    if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  }, 1200);
}
async function startFromSchedule() {
  const p = schedParams.value;
  if (!p.packs.length) { flash('请至少选择一个内容包', true); return; }
  try {
    await api.broadcast('start', {
      packs: p.packs, strategy: p.strategy, mode: p.mode,
      seed: normalizeSeed(p.seed), loop: p.loop,
    });
    bcPacks.value = [...p.packs];
    bcStrategy.value = p.strategy;
    bcMode.value = p.mode || '';
    bcSeed.value = p.seed === undefined ? '' : String(p.seed);
    bcLoop.value = !!p.loop;
    await Promise.all([refreshStatus(), loadAudit()]);
    flash('已按预演参数开播，可在「剧本播放」继续推进');
  } catch (e) { flash('开播失败：' + e.message, true); }
}

// —— P1：设置页右侧嵌展示页实时预览 ——
// 边界：iframe 里跑的是**真实展示页**，它自己 GET /__api/settings。控制台不向
// iframe 注入任何草稿配置（postMessage 注入会破坏「console 写 / display 读」）。
// 因此只有已保存的设置才会出现在预览里；保存成功后自动刷新 iframe。
const previewTargets = [
  { label: '头像打印台', value: '/web/index.html' },
  { label: '3D 打印台', value: '/web/index.html' },
  { label: '直播小窗', value: '/web/live-view.html' },
];
const previewTarget = ref('/web/index.html');
const previewScale = ref(0.5);
const previewEnabled = ref(true);
const previewNonce = ref(0);
const previewUrl = computed(() => previewTarget.value +
  (previewTarget.value.includes('?') ? '&' : '?') + 'pv=' + previewNonce.value);
const previewFrameStyle = computed(() => ({ transform: 'scale(' + previewScale.value + ')' }));
const previewBoxStyle = computed(() => ({
  width: (1280 * previewScale.value) + 'px',
  height: (720 * previewScale.value) + 'px',
}));
function refreshPreview() { previewNonce.value += 1; }

// —— 控制台设置：脏标记 / 恢复默认 / 分组 ——
// 边界：这里写的设置经 /__api/settings 落盘；展示页只 GET，不写任何配置。
const settings = ref(null);
const settingsBaseline = ref('');
const settingsDirty = ref(false);
const openGroups = reactive({ branding: true, display: false, printer: false, broadcast: false, live: false });

watch(settings, () => {
  if (settings.value) settingsDirty.value = JSON.stringify(settings.value) !== settingsBaseline.value;
}, { deep: true });

async function loadSettings() {
  try {
    const data = await api.getSettings();
    settings.value = data.settings;
    settingsBaseline.value = JSON.stringify(data.settings);
    settingsDirty.value = false;
  } catch (e) { error.value = '读取控制台设置失败：' + e.message; }
}
async function saveSettings() {
  if (!settings.value) return;
  try {
    const data = await api.saveSettings(settings.value);
    settings.value = data.settings;
    settingsBaseline.value = JSON.stringify(data.settings);
    settingsDirty.value = false;
    flash('控制台设置已保存，右侧预览已刷新');
    refreshPreview();
    await Promise.all([bcLoad(), loadAudit()]);
  } catch (e) { flash('保存失败：' + e.message, true); }
}
async function applyResetSettings() {
  try {
    const data = await api.resetSettings();
    settings.value = data.settings;
    settingsBaseline.value = JSON.stringify(data.settings);
    settingsDirty.value = false;
    refreshPreview();
    await loadAudit();
    flash('已恢复出厂设置，右侧预览已刷新');
  } catch (e) { flash('恢复默认失败：' + e.message, true); }
}
function colorValue(v) { return /^#[0-9a-fA-F]{6}$/.test(v || '') ? v : '#4f8cff'; }

// —— 出场广播控制 ——
const bcPacks = ref([]);
const bcStrategy = ref('concat');
const bcMode = ref('');
const bcLoop = ref(false);
const bcSeed = ref('');
const bcCharId = ref('');

async function bcLoad() {
  // 表单初值来自控制台设置：设置真正驱动控制台行为。
  if (settings.value && settings.value.broadcast && !bcState.value.active) {
    const d = settings.value.broadcast;
    bcPacks.value = d.defaultPacks || [];
    bcStrategy.value = d.strategy || 'concat';
    bcMode.value = d.mode || '';
    bcLoop.value = !!d.loop;
  }
}
async function bcStart() {
  if (!bcPacks.value.length) { flash('请至少选择一个内容包', true); return; }
  try {
    await api.broadcast('start', {
      packs: bcPacks.value, strategy: bcStrategy.value,
      mode: bcMode.value || undefined, loop: bcLoop.value,
      seed: normalizeSeed(bcSeed.value),
    });
    await Promise.all([refreshStatus(), loadAudit()]);
    flash('剧本播放已启动');
  } catch (e) { flash('启动失败：' + e.message, true); }
}
async function bcNext() {
  try { await api.broadcast('next'); await Promise.all([refreshStatus(), loadAudit()]); }
  catch (e) { flash(e.message, true); }
}
async function bcTrigger() {
  try {
    await api.broadcast('trigger', { charId: bcCharId.value || undefined });
    await Promise.all([refreshStatus(), loadAudit()]);
  } catch (e) { flash(e.message, true); }
}
async function bcReset() {
  try {
    await api.broadcast('reset');
    await Promise.all([refreshStatus(), loadAudit()]);
    flash('广播已重置');
  } catch (e) { flash(e.message, true); }
}
async function bcPlay() {
  try {
    await api.broadcast('play', { intervalMs: 5000, loop: bcLoop.value });
    await Promise.all([refreshStatus(), loadAudit()]);
    flash('已启动自动播放');
  } catch (e) { flash(e.message, true); }
}
async function bcPause() {
  try {
    await api.broadcast('pause');
    await Promise.all([refreshStatus(), loadAudit()]);
    flash('已暂停自动播放');
  } catch (e) { flash(e.message, true); }
}

// —— 本机窗口与数据桥（后端已实现，控制台此前从未接入）——
async function openPrinter() {
  try {
    await api.openScene('/web/index.html?scene=1', 'landscape');
    await loadAudit(); flash('已拉起 3D 打印台窗口');
  } catch (e) { flash('打开打印台失败：' + e.message, true); }
}
async function openLiveWindow() {
  const room = settings.value && settings.value.live && settings.value.live.defaultRoom;
  if (!room) { flash('请先在「控制台设置 → 直播」填写默认直播间号', true); go('settings'); return; }
  try { await api.openLive(room, false); await loadAudit(); flash('已拉起直播小窗'); }
  catch (e) { flash('打开直播小窗失败：' + e.message, true); }
}
async function toggleBridge() {
  const running = status.value && status.value.bridge && status.value.bridge.ok;
  const room = settings.value && settings.value.live && settings.value.live.defaultRoom;
  try {
    if (running) await api.stopBridge();
    else await api.startBridge(room || undefined);
    await Promise.all([refreshStatus(), loadAudit()]);
    flash(running ? '数据桥已停止' : '数据桥已启动');
  } catch (e) { flash('数据桥操作失败：' + e.message, true); }
}

function ruleLabel(k) {
  return ({
    comment: '评论打印', join: '进场打印', like: '点赞打印',
    follow: '关注打印', gift: '礼物打印', giftVoice: '礼物语音', joinVoice: '进场语音',
  })[k] || k;
}

// —— 数据层状态（SQLite）：控制台只读展示，展示端不关心 ——
const dbInfo = ref(null);
const dbError = ref('');
const DB_TABLE_LABELS = {
  packs: '内容包', characters: '人物', media: '图片元数据',
  settings: '设置文档', audit: '操作日志', runtime_state: '运行时状态',
};
async function loadDbInfo() {
  try {
    const data = await api.getDbInfo();
    dbInfo.value = data.db || null;
    dbError.value = '';
  } catch (e) {
    dbInfo.value = null;
    dbError.value = e.message;
  }
}
function dbTableRows(info) {
  if (!info) return [];
  return Object.entries(info.tables || {}).map(([key, count]) => ({
    key, count, label: DB_TABLE_LABELS[key] || key,
  }));
}

// —— P1：本机操作日志视图（读取服务端埋点，前端不上报）——
const auditEntries = ref([]);
const auditStats = ref({ total: 0, ok: 0, failed: 0, actions: [], limit: 500, lastAt: null });
const auditAction = ref('');
const auditQuery = ref('');
const auditOnlyFailed = ref(false);
const auditLoading = ref(false);

let auditSeq = 0;
async function loadAudit() {
  const seq = ++auditSeq;
  auditLoading.value = true;
  try {
    // 筛选交给后端 SQL：早期「先取 100 条再前端过滤」会把窗口外的失败记录截掉。
    const data = await api.getAudit({
      limit: 100,
      action: auditAction.value,
      q: auditQuery.value,
      onlyFailed: auditOnlyFailed.value,
    });
    if (seq !== auditSeq) return;
    auditEntries.value = data.entries || [];
    auditStats.value = data.stats || auditStats.value;
  } catch (e) { if (seq === auditSeq) error.value = '读取操作日志失败：' + e.message; }
  finally { if (seq === auditSeq) auditLoading.value = false; }
}
async function clearAudit() {
  try {
    await api.clearAudit();
    await loadAudit();
    flash('操作日志已清空（本次清空动作仍保留一条记录）');
  } catch (e) { flash('清空失败：' + e.message, true); }
}

function onKeydown(e) {
  if (e.key !== 'Escape') return;
  if (drawer.value) requestCloseDrawer();
  else if (pendingConfirm.value) pendingConfirm.value = null;
}

// 切到日志 / 内容包视图时刷新一次；其余视图靠各自的写操作主动刷新。
watch(activeView, (v) => {
  if (v === 'audit') loadAudit();
  if (v === 'packs') loadPacks();
  if (v === 'system') loadDbInfo();
});
watch([auditAction, auditOnlyFailed], () => loadAudit());

onMounted(async () => {
  await Promise.all([loadMeta(), loadPacks(), loadMedia(), loadSettings(),
                     refreshStatus(), loadDbInfo()]);
  await bcLoad();
  loadAudit();
  window.addEventListener('keydown', onKeydown);
  startEventLoop();
  statusTimer = setInterval(refreshStatus, 2000);
});
onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer);
  if (flashTimer) clearTimeout(flashTimer);
  stopEventLoop();
  stopRehearsal();
  window.removeEventListener('keydown', onKeydown);
});
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <div class="logo">P</div>
        <div>
          <div class="brand-name">printcast <span>控制台</span></div>
          <div class="brand-sub">本机运行 · 配置与状态的唯一来源</div>
        </div>
      </div>
      <div class="lights">
        <div v-for="l in lights" :key="l.key" class="light" :class="l.on ? 'on' : 'off'" :title="l.detail">
          <span class="light-dot"></span><span>{{ l.label }}</span>
        </div>
      </div>
      <div class="topbar-actions">
        <button class="btn ghost small" @click="openPrinter">打开打印台</button>
        <button class="btn ghost small" @click="openLiveWindow">直播小窗</button>
        <button class="btn ghost small" @click="theme = theme === 'dark' ? 'light' : 'dark'">{{ theme === 'dark' ? '浅色' : '深色' }}</button>
      </div>
    </header>

    <div class="layout">
      <aside class="sidebar">
        <div v-for="g in NAV" :key="g.group" class="nav-group">
          <div class="nav-title">{{ g.group }}</div>
          <button v-for="id in g.items" :key="id" class="nav-item" :class="{ active: activeView === id }" @click="go(id)">
            {{ VIEWS[id].title }}
          </button>
        </div>
        <div class="sidebar-foot">
          <div class="muted">服务 {{ connection.ok === true ? '已连通' : connection.ok === false ? '断开' : '检测中' }}</div>
          <div class="muted mono">{{ connection.host }}</div>
        </div>
      </aside>

      <main class="workspace">
        <div class="view-head">
          <div>
            <h1>{{ viewMeta.title }}</h1>
            <p class="muted">{{ viewMeta.desc }}</p>
          </div>
          <button class="btn ghost small" @click="refreshStatus">刷新状态</button>
        </div>

        <div v-if="connection.ok === false" class="banner err">
          后端连不上：{{ statusError || connection.detail }}。内置示例包仍在 <code>data/packs/</code>，并未被删除。
        </div>
        <div v-if="error" class="banner err">{{ error }}</div>
        <div v-if="pendingConfirm && ['reset-broadcast', 'reset-settings', 'clear-audit'].includes(pendingConfirm.kind)" class="inline-confirm bar">
          {{ pendingConfirm.kind === 'reset-broadcast' ? '重置会清空当前广播进度，确定？' : pendingConfirm.kind === 'clear-audit' ? '清空后历史记录不可恢复（本次清空动作会保留一条记录），确定？' : '恢复默认会覆盖全部控制台设置，确定？' }}
          <button class="btn danger small" @click="confirmPending">确定</button>
          <button class="btn ghost small" @click="pendingConfirm = null">取消</button>
        </div>

        <!-- ============ 总览 ============ -->
        <template v-if="activeView === 'overview'">
          <section class="card hero">
            <div class="hero-main">
              <div class="avatar">{{ currentChar ? (currentChar.name || '?').slice(0, 1) : '—' }}</div>
              <div class="hero-text">
                <div class="eyebrow">现在正在打印<span v-if="runtimeText"> · 已运行 {{ runtimeText }}</span></div>
                <div class="hero-title">{{ currentChar ? (currentChar.name || currentChar.id || '未知角色') : '尚未开播' }}</div>
                <div class="muted" v-if="bcState.active">
                  {{ (bcState.packIds || []).join(' / ') }} · 第 {{ bcState.seq || 0 }} 位 · 模式 {{ bcState.mode }}
                </div>
                <div class="muted" v-else>在上方选好内容包后点「开始剧本播放」，或到「剧本播放」页配置参数。</div>
              </div>
            </div>
            <div class="hero-actions">
              <button class="btn primary" @click="bcStart">开始 / 重启广播</button>
              <button class="btn" :disabled="!bcState.active" @click="bcNext">下一个</button>
              <button class="btn ghost" :disabled="!bcState.active" @click="ask('reset-broadcast')">重置进度</button>
              <button class="btn ghost" @click="go('broadcast')">剧本播放 / 高级控制 →</button>
            </div>
          </section>

          <section class="card">
            <div class="card-head"><h2>内容源</h2><span class="muted">同一台 3D 打印机，可切换驱动方式</span></div>
            <div class="seg">
              <button :class="contentSource==='script' ? 'seg-btn active' : 'seg-btn'" @click="contentSource='script'">剧本播放（内容包出场）</button>
              <button :class="contentSource==='live' ? 'seg-btn active' : 'seg-btn'" @click="contentSource='live'">实时直播（弹幕 / 礼物）</button>
            </div>
            <div class="row tight" style="margin-top:12px">
              <template v-if="contentSource==='script'">
                <button class="btn primary" @click="bcStart">开始 / 重启剧本播放</button>
                <button class="btn" :disabled="!bcState.active" @click="bcNext">下一个</button>
                <button class="btn" :disabled="!bcState.active" @click="bcPlaying ? bcPause() : bcPlay()">{{ bcPlaying ? '暂停播放' : '自动播放' }}</button>
                <button class="btn ghost" :disabled="!bcState.active" @click="ask('reset-broadcast')">重置进度</button>
              </template>
              <template v-else>
                <button class="btn primary" @click="toggleBridge">{{ status && status.bridge && status.bridge.ok ? '停止数据桥' : '启动数据桥' }}</button>
                <span class="muted">直播由数据桥从直播间抓取弹幕 / 礼物，实时驱动打印。</span>
                <a class="link" :href="'/web/index.html?room=' + ((settings&&settings.live&&settings.live.defaultRoom)||'')" target="_blank">打开直播抓取窗口 ↗</a>
              </template>
            </div>
          </section>

          <div class="metrics">
            <div class="metric"><div class="metric-label">内容包</div><div class="metric-value mono">{{ counts.packs }}</div><div class="metric-sub">已导入</div></div>
            <div class="metric"><div class="metric-label">已出场</div><div class="metric-value mono">{{ bcState.seq || 0 }}</div><div class="metric-sub">本轮剧本</div></div>
            <div class="metric"><div class="metric-label">图片资源</div><div class="metric-value mono">{{ counts.media }}</div><div class="metric-sub">已上传</div></div>
            <div class="metric"><div class="metric-label">服务运行</div><div class="metric-value mono">{{ status ? Math.floor(status.service.uptimeSeconds / 60) : 0 }}<span class="unit">分</span></div><div class="metric-sub">自启动</div></div>
          </div>

          <div class="two-col">
            <section class="card">
              <div class="card-head"><h2>实时事件</h2><span class="muted">订阅 /__scene-events · 自动刷新</span></div>
              <div class="event-list">
                <div v-if="!events.length" class="empty">暂无事件。启动剧本播放或直播后，出场、语音、打印入队会实时出现在这里。</div>
                <div v-for="(ev, i) in events" :key="i" class="event-row">
                  <span class="mono event-time">{{ ev.time }}</span><span>{{ ev.text }}</span>
                </div>
              </div>
            </section>
            <section class="card">
              <div class="card-head"><h2>运行链路</h2><span class="muted">只读诊断</span></div>
              <div class="chain">
                <div class="chain-row"><span class="chain-key">本机服务</span><span :class="status ? 'tag ok' : 'tag bad'">{{ status ? 'HTTP ' + status.service.port : '断开' }}</span></div>
                <div class="chain-row"><span class="chain-key">数据桥 / 采集</span><span :class="status && status.bridge && status.bridge.ok ? 'tag ok' : 'tag mute'">{{ status && status.bridge && status.bridge.ok ? status.bridge.url : '未启动' }}</span></div>
                <div class="chain-row"><span class="chain-key">剧本播放</span><span :class="bcState.active ? 'tag ok' : 'tag mute'">{{ bcState.active ? '进行中' : '待机' }}</span></div>
                <div class="chain-row"><span class="chain-key">剧本打印到 3D</span><span class="tag mute">{{ settings && settings.broadcast && settings.broadcast.scriptedPrint ? '已启用' : '已关闭' }}</span></div>
              </div>
              <div class="row tight">
                <button class="btn small" @click="toggleBridge">{{ status && status.bridge && status.bridge.ok ? '停止数据桥' : '启动数据桥' }}</button>
                <a class="link" href="/web/index.html" target="_blank">头像打印台 ↗</a>
              </div>
            </section>
          </div>

          <div class="two-col">
            <section class="card">
              <div class="card-head"><h2>打印规则</h2><span class="muted">从「控制台设置」搬来，直接在此调整</span></div>
              <div class="checks">
                <label class="switch" v-for="k in ['comment','join','like','follow','gift','giftVoice','joinVoice']" :key="k"><input type="checkbox" v-model="settings.printer.rules[k]" /><span class="track"></span>{{ ruleLabel(k) }}</label>
              </div>
              <div class="row">
                <label class="switch"><input type="checkbox" v-model="settings.printer.autoDemo" /><span class="track"></span>自动演示填充</label>
                <label class="switch"><input type="checkbox" v-model="settings.printer.idleFill" /><span class="track"></span>空闲测试头像</label>
                <label>演示间隔 (ms)<input type="number" v-model.number="settings.printer.demoGapMs" min="0" /></label>
                <label>空闲阈值 (秒)<input type="number" v-model.number="settings.printer.idleSeconds" min="0" /></label>
              </div>
              <button class="btn small" :disabled="!settingsDirty" @click="saveSettings">保存打印规则</button>
            </section>
            <section class="card">
              <div class="card-head"><h2>打印台实时画面</h2><span class="muted">只读预览 · 与展示端同一画面</span></div>
              <div class="preview-box" :style="previewBoxStyle">
                <iframe :key="previewUrl" :src="previewUrl" :style="previewFrameStyle" sandbox="allow-scripts allow-same-origin" referrerpolicy="no-referrer" title="头像打印台实时预览"></iframe>
              </div>
            </section>
          </div>
        </template>

        <!-- ============ 剧本播放 ============ -->
        <template v-else-if="activeView === 'broadcast'">
          <section class="card">
            <div class="card-head"><h2>剧本播放参数</h2><span class="muted">未开播时初值来自控制台设置</span></div>
            <div class="row"><span class="field-label">内容包</span>
              <label class="switch" v-for="p in packs" :key="p.id"><input type="checkbox" :value="p.id" v-model="bcPacks" /><span class="track"></span>{{ p.title }}</label>
            </div>
            <div class="row">
              <label>组合策略<select v-model="bcStrategy"><option value="concat">concat 顺次</option><option value="interleave">interleave 穿插</option><option value="merged">merged 合并</option></select></label>
              <label>出场模式<select v-model="bcMode"><option value="">默认</option><option value="sequence">sequence</option><option value="weighted">weighted</option><option value="trigger">trigger</option></select></label>
              <label class="switch"><input type="checkbox" v-model="bcLoop" /><span class="track"></span>循环</label>
              <label>固定 seed（可复现）<input v-model="bcSeed" placeholder="留空则随机，如 20261104" /></label>
            </div>
            <div class="row">
              <button class="btn primary" @click="bcStart">开始 / 重启广播</button>
              <button class="btn" :disabled="!bcState.active" @click="bcNext">下一个</button>
              <button class="btn" :disabled="!bcState.active" @click="bcPlaying ? bcPause() : bcPlay()">{{ bcPlaying ? '暂停播放' : '自动播放' }}</button>
              <button class="btn ghost" :disabled="!bcState.active" @click="ask('reset-broadcast')">重置</button>
            </div>
            <div class="row">
              <input v-model="bcCharId" placeholder="点名角色 ID（可选）" class="grow" />
              <button class="btn" :disabled="!bcState.active" @click="bcTrigger">点名出场</button>
            </div>
            <div class="state-line">
              <span :class="bcState.active ? 'tag ok' : 'tag mute'">{{ bcState.active ? '进行中' : '待机' }}</span>
              <span v-if="bcState.active" :class="bcState.playing ? 'tag ok' : 'tag mute'">{{ bcState.playing ? '自动播放中' : '已暂停（手动）' }}</span>
              <span class="muted" v-if="bcState.active">{{ (bcState.packIds || []).join(', ') }} · 模式 {{ bcState.mode }} · seed {{ bcState.seed === null || bcState.seed === undefined ? '未固定' : bcState.seed }} · 已出场 {{ bcState.seq || 0 }}<template v-if="currentChar"> · 当前 {{ currentChar.name }}</template></span>
              <span class="muted" v-else>尚未开始或已重置。</span>
            </div>
          </section>
        </template>

        <!-- ============ 内容包（P1：搜索 / 排序 / 抽屉 / 导入导出）============ -->
        <template v-else-if="activeView === 'packs'">
          <section class="card">
            <div class="card-head">
              <h2>已导入内容包 <span class="muted">· {{ filteredPacks.length }} / {{ packs.length }}</span></h2>
              <div class="row tight pack-tools">
                <input v-model="packQuery" placeholder="搜索 ID 或标题" class="grow" />
                <select v-model="packSort" class="sort-select">
                  <option value="title">按标题</option><option value="id">按 ID</option>
                  <option value="count">按人物数</option><option value="updated">按更新时间</option>
                </select>
                <input ref="packImportInput" type="file" accept=".json,application/json" class="hidden-file" @change="onPackFile" />
                <button class="btn small" @click="packImportInput.click()">导入 JSON</button>
                <button class="btn ghost small" @click="loadPacks(); refreshStatus()">刷新</button>
              </div>
            </div>
            <div v-if="packImportResult" class="import-report" :class="packImportResult.ok ? 'ok' : 'err'">
              <b>{{ packImportResult.ok ? '导入成功' : '导入失败' }}</b>
              <span class="muted"> · {{ packImportResult.error || (packImportResult.pack && packImportResult.pack.id) || '' }}
                <template v-if="packImportResult.stats"> · 共 {{ packImportResult.stats.total }} 人，接受 {{ packImportResult.stats.accepted }}，错误 {{ packImportResult.stats.errors }}</template>
              </span>
              <ul v-if="packImportResult.errors && packImportResult.errors.length">
                <li v-for="(e, i) in packImportResult.errors.slice(0, 12)" :key="i">行 {{ e.line }} · {{ e.field }}：{{ e.message }}</li>
              </ul>
            </div>
            <div v-if="!packs.length" class="empty">暂无内容包。到「数据导入」下载模板并导入，或直接点「导入 JSON」；内置示例包仍存放在 <code>data/packs/</code>。</div>
            <div v-else-if="!filteredPacks.length" class="empty">没有匹配「{{ packQuery }}」的内容包，换个关键词试试。</div>
            <table v-else>
              <thead><tr><th>ID</th><th>标题</th><th>模式</th><th>人物数</th><th>更新</th><th></th></tr></thead>
              <tbody>
                <tr v-for="p in filteredPacks" :key="p.id">
                  <td class="mono">{{ p.id }}</td>
                  <td><button class="link-btn" @click="openPack(p.id)">{{ p.title }}</button></td>
                  <td>{{ p.mode }}</td><td class="mono">{{ p.count }}</td>
                  <td class="mono muted">{{ (p.updated || '').slice(0, 10) || '—' }}</td>
                  <td class="right nowrap">
                    <button class="btn ghost small" @click="openPack(p.id)">查看 / 编辑</button>
                    <button class="btn ghost small" @click="duplicatePack(p)">复制</button>
                    <button class="btn ghost small" @click="exportPack(p)">导出</button>
                    <span v-if="pendingConfirm && pendingConfirm.kind === 'pack' && pendingConfirm.id === p.id" class="inline-confirm">
                      确定删除？<button class="btn danger small" @click="confirmPending">删除</button><button class="btn ghost small" @click="pendingConfirm = null">取消</button>
                    </span>
                    <button v-else class="btn danger small" @click="ask('pack', p.id)">删除</button>
                  </td>
                </tr>
              </tbody>
            </table>
            <p class="muted hint-line">点击标题打开右侧抽屉：查看人物头像、台词、权重与标签，可直接编辑保存（后端逐字段校验），也可复制成新包或导出 JSON 备份。</p>
          </section>
        </template>

        <!-- ============ 数据导入 ============ -->
        <template v-else-if="activeView === 'import'">
          <section class="card">
            <div class="card-head"><h2>模板下载</h2><span class="muted">字段由后端 schema 驱动</span></div>
            <div class="row"><button class="btn" @click="downloadTemplate('csv')">下载 CSV 模板</button><button class="btn" @click="downloadTemplate('json')">下载 JSON 模板</button></div>
          </section>
          <section class="card">
            <div class="card-head"><h2>导入数据</h2><span class="muted">先校验，后落盘</span></div>
            <div class="row">
              <label>内容包 ID<input v-model="packMeta.id" placeholder="如 ming-emperors" /></label>
              <label>标题<input v-model="packMeta.title" placeholder="如 明朝十六帝" /></label>
              <label>模式<select v-model="packMeta.mode"><option value="sequence">sequence 顺序</option><option value="weighted">weighted 权重</option><option value="trigger">trigger 触发</option></select></label>
            </div>
            <div class="row"><input type="file" accept=".csv" @change="onFile" class="grow" /><span class="muted">{{ csvFileName || '未选择文件' }}</span></div>
            <textarea v-model="csvText" rows="6" placeholder="或直接粘贴 CSV 文本（含表头 id,name,order,...）"></textarea>
            <div class="row">
              <label class="switch"><input type="checkbox" v-model="commit" /><span class="track"></span>校验通过后立即保存</label>
              <button class="btn primary" :disabled="importing" @click="runImport">{{ importing ? '导入中…' : '导入' }}</button>
            </div>
            <div v-if="importResult" class="result">
              <p :class="importResult.ok ? 'ok' : 'err'">{{ importResult.ok ? '通过' : '未通过' }} · 共 {{ importResult.stats && importResult.stats.total }} 行，接受 {{ importResult.stats && importResult.stats.accepted }}，错误 {{ importResult.stats && importResult.stats.errors }}</p>
              <ul v-if="importResult.errors && importResult.errors.length"><li v-for="(e, i) in importResult.errors.slice(0, 20)" :key="i">行 {{ e.line }} · {{ e.field }}：{{ e.message }}</li></ul>
            </div>
          </section>
        </template>

        <!-- ============ 图片资源 ============ -->
        <template v-else-if="activeView === 'media'">
          <section class="card">
            <div class="card-head"><h2>上传图片</h2><span class="muted">单张 ≤ {{ Math.round((limits.maxMediaBytes || 0) / 1048576) }}MB · PNG / JPEG / WebP</span></div>
            <div class="row"><input ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp" class="grow" /><button class="btn primary" @click="upload">上传</button></div>
            <div v-if="media.length" class="media-grid">
              <figure v-for="m in media" :key="m.id">
                <img :src="'/media/' + m.id" :alt="m.name" />
                <figcaption><span class="muted ellipsis">{{ m.name }}</span><button class="btn danger tiny" @click="ask('media', m.id)">×</button></figcaption>
              </figure>
            </div>
            <div v-else class="empty">暂无上传图片。</div>
            <div v-if="pendingConfirm && pendingConfirm.kind === 'media'" class="inline-confirm bar">
              确定删除图片 {{ pendingConfirm.id }}？<button class="btn danger small" @click="confirmPending">删除</button><button class="btn ghost small" @click="pendingConfirm = null">取消</button>
            </div>
          </section>
        </template>

        <!-- ============ 排期预演（P1：时间轴 / 固定 seed / 本地预演）============ -->
        <template v-else-if="activeView === 'schedule'">
          <section class="card">
            <div class="card-head"><h2>生成出场序列</h2><span class="muted">预演只在工作台内高亮，不触发真实广播与打印</span></div>
            <div class="row">
              <label>组合策略<select v-model="schedStrategy"><option value="concat">concat 顺次</option><option value="interleave">interleave 轮转穿插</option><option value="merged">merged 合并排序</option></select></label>
              <label>出场模式<select v-model="schedMode"><option value="">默认</option><option value="sequence">sequence</option><option value="weighted">weighted</option><option value="trigger">trigger</option></select></label>
              <label>数量（≤300）<input type="number" v-model.number="schedCount" min="1" max="300" /></label>
              <label>固定 seed<input v-model="schedSeed" placeholder="如 20261104，留空随机" /></label>
              <label>循环<select v-model="schedLoop"><option value="">跟随内容包</option><option value="1">开启</option><option value="0">关闭</option></select></label>
            </div>
            <div class="row"><span class="field-label">内容包</span><label class="switch" v-for="p in packs" :key="p.id"><input type="checkbox" :value="p.id" v-model="schedPacks" /><span class="track"></span>{{ p.title }}</label></div>
            <div class="row">
              <button class="btn primary" :disabled="schedLoading" @click="previewSchedule">{{ schedLoading ? '生成中…' : '生成出场序列' }}</button>
              <button class="btn" @click="toggleRehearsal" :disabled="!schedAppearances.length">{{ tlPlaying ? '停止预演' : '本地预演' }}</button>
              <button class="btn ghost" @click="copyText(schedUrl)">复制复现链接</button>
              <button class="btn ghost" @click="startFromSchedule">按此配置开播</button>
              <a class="link" href="/web/index.html" target="_blank">头像打印台 ↗</a>
            </div>
            <div class="repro">
              <span class="tag mute">固定 seed 复现</span>
              <code class="repro-url">{{ schedUrl }}</code>
              <span class="muted">同一组 pack + 策略 + 模式 + seed 必然得到同一条序列；「按此配置开播」会把 seed 原样交给广播控制器，state 里可核对。</span>
            </div>
          </section>

          <section class="card" v-if="schedResult">
            <div class="card-head">
              <h2>出场时间轴 <span class="muted">· {{ schedAppearances.length }} 位</span></h2>
              <span class="muted">模式 {{ schedResult.mode }} · 策略 {{ schedResult.strategy }} · seed {{ schedResult.seed === null || schedResult.seed === '' ? '未固定' : schedResult.seed }} · loop {{ schedResult.loop }}<template v-if="tlPlaying"> · 预演 {{ tlIndex + 1 }}/{{ schedAppearances.length }}</template></span>
            </div>
            <div class="timeline">
              <button v-for="(a, i) in schedAppearances" :key="i" class="tl-card"
                :class="{ 'is-selected': tlSelected === i, 'is-current': tlPlaying && tlIndex === i }"
                @click="tlSelected = i">
                <span class="tl-index mono">#{{ i + 1 }}<template v-if="a.loop"> · L{{ a.loop + 1 }}</template></span>
                <span class="tl-avatar">
                  <img v-if="charAvatar(a)" :src="charAvatar(a)" :alt="a.name" />
                  <template v-else>{{ (a.name || '?').slice(0, 1) }}</template>
                </span>
                <span class="tl-name">{{ a.name || a.id }}</span>
                <span class="tl-speech">{{ a.speech || '（无播报文案）' }}</span>
                <span class="tl-foot mono">{{ a.packId }}<template v-if="a.weight !== undefined"> · w{{ a.weight }}</template></span>
              </button>
              <div v-if="!schedAppearances.length" class="empty">这条序列没有可出场角色，检查内容包的 mode 与 weight。</div>
            </div>
            <div v-if="tlSelected >= 0 && schedAppearances[tlSelected]" class="tl-detail">
              <div class="tl-detail-head">
                <div class="tl-avatar big">
                  <img v-if="charAvatar(schedAppearances[tlSelected])" :src="charAvatar(schedAppearances[tlSelected])" alt="" />
                  <template v-else>{{ (schedAppearances[tlSelected].name || '?').slice(0, 1) }}</template>
                </div>
                <div>
                  <b>{{ schedAppearances[tlSelected].name }}</b>
                  <span class="muted"> · {{ schedAppearances[tlSelected].id }} · 第 {{ tlSelected + 1 }} 位</span>
                  <div class="muted">来自 {{ schedAppearances[tlSelected].packTitle || schedAppearances[tlSelected].packId }} · order {{ schedAppearances[tlSelected].order }} · weight {{ schedAppearances[tlSelected].weight }}</div>
                </div>
              </div>
              <div class="row tight">
                <span class="tag mute" v-for="(t, k) in (schedAppearances[tlSelected].tags || [])" :key="k">{{ t }}</span>
                <span class="muted" v-if="!(schedAppearances[tlSelected].tags || []).length">无标签</span>
              </div>
              <p class="muted" v-if="schedAppearances[tlSelected].speech">播报：{{ schedAppearances[tlSelected].speech }}</p>
            </div>
          </section>
          <div v-else class="empty">选好内容包与参数后点「生成出场序列」，这里会出现可点击、可逐位预演的时间轴卡片带。</div>
        </template>

        <!-- ============ 控制台设置（P1：右侧嵌展示页缩放预览）============ -->
        <template v-else-if="activeView === 'settings'">
          <div class="settings-layout">
          <div class="settings-main">
          <div class="settings-bar" v-if="settings">
            <span :class="settingsDirty ? 'tag warn' : 'tag ok'">{{ settingsDirty ? '有未保存的修改' : '已与后端同步' }}</span>
            <button class="btn primary" :disabled="!settingsDirty" @click="saveSettings">保存设置</button>
            <button class="btn ghost" @click="ask('reset-settings')">恢复默认</button>
            <span class="muted">保存后打开：<a class="link" href="/web/index.html" target="_blank">头像打印台 ↗</a><a class="link" href="/web/live-view.html" target="_blank">直播小窗 ↗</a></span>
          </div>
          <template v-if="settings">
            <section class="card group">
              <button class="group-head" @click="openGroups.branding = !openGroups.branding"><span>品牌与页脚</span><span class="muted">{{ openGroups.branding ? '收起' : '展开' }}</span></button>
              <div v-if="openGroups.branding" class="group-body">
                <div class="row">
                  <label>站点标题<input v-model="settings.branding.title" /></label>
                  <label>副标题<input v-model="settings.branding.subtitle" /></label>
                  <label>强调色<div class="color-row"><input type="color" :value="colorValue(settings.branding.accent)" @input="settings.branding.accent = $event.target.value" /><input v-model="settings.branding.accent" placeholder="#4f8cff" /></div></label>
                </div>
                <label>页脚说明<textarea v-model="settings.branding.footer" rows="2"></textarea></label>
                <div class="row"><span class="field-label">页脚链接</span>
                  <div v-for="(lnk, i) in settings.branding.links" :key="i" class="link-row">
                    <input v-model="lnk.label" placeholder="名称" /><input v-model="lnk.href" placeholder="/site/guide.html" /><button class="btn ghost small" @click="settings.branding.links.splice(i, 1)">移除</button>
                  </div>
                  <button class="btn ghost small" @click="settings.branding.links.push({ label: '', href: '/' })">＋ 添加链接</button>
                </div>
              </div>
            </section>

            <section class="card group">
              <button class="group-head" @click="openGroups.display = !openGroups.display"><span>展示外观</span><span class="muted">{{ openGroups.display ? '收起' : '展开' }}</span></button>
              <div v-if="openGroups.display" class="group-body">
                <div class="row"><label>覆盖层主文字<input v-model="settings.display.overlayText" /></label><label>覆盖层副文字<input v-model="settings.display.overlaySub" /></label></div>
                <div class="row"><label>展示端主题<select v-model="settings.display.theme"><option value="dark">深色</option><option value="light">浅色</option></select></label></div>
                <div class="row"><label>公告条文案<input v-model="settings.display.announceText" placeholder="由控制台设置，展示端不含硬编码内容" /></label></div>
                <div class="checks">
                  <label class="switch"><input type="checkbox" v-model="settings.display.showDemoBadge" /><span class="track"></span>演示模式徽标</label>
                  <label class="switch"><input type="checkbox" v-model="settings.display.showAnnounce" /><span class="track"></span>公告条</label>
                </div>
              </div>
            </section>

            <section class="card group">
              <button class="group-head" @click="openGroups.broadcast = !openGroups.broadcast"><span>剧本播放默认值</span><span class="muted">{{ openGroups.broadcast ? '收起' : '展开' }}</span></button>
              <div v-if="openGroups.broadcast" class="group-body">
                <div class="row"><span class="field-label">默认内容包</span><label class="switch" v-for="p in packs" :key="p.id"><input type="checkbox" :value="p.id" v-model="settings.broadcast.defaultPacks" /><span class="track"></span>{{ p.title }}</label></div>
                <div class="row">
                  <label>组合策略<select v-model="settings.broadcast.strategy"><option value="concat">concat</option><option value="interleave">interleave</option><option value="merged">merged</option></select></label>
                  <label>出场模式<select v-model="settings.broadcast.mode"><option value="">默认</option><option value="sequence">sequence</option><option value="weighted">weighted</option><option value="trigger">trigger</option></select></label>
                </div>
                <div class="checks">
                  <label class="switch"><input type="checkbox" v-model="settings.broadcast.loop" /><span class="track"></span>循环</label>
                  <label class="switch"><input type="checkbox" v-model="settings.broadcast.autoStart" /><span class="track"></span>启动即广播</label>
                  <label class="switch"><input type="checkbox" v-model="settings.broadcast.speech" /><span class="track"></span>语音播报</label>
                  <label class="switch"><input type="checkbox" v-model="settings.broadcast.scriptedPrint" /><span class="track"></span>打到 3D 打印机</label>
                </div>
              </div>
            </section>

            <section class="card group">
              <button class="group-head" @click="openGroups.live = !openGroups.live"><span>直播</span><span class="muted">{{ openGroups.live ? '收起' : '展开' }}</span></button>
              <div v-if="openGroups.live" class="group-body">
                <div class="row"><label>默认直播间号<input v-model="settings.live.defaultRoom" placeholder="留空则手动输入" /></label><label>平台<select v-model="settings.live.platform"><option value="douyin">抖音</option><option value="other">其它</option></select></label></div>
              </div>
            </section>
          </template>
          <div v-else class="empty">控制台设置读取失败，请检查上方连接状态。</div>
          </div>
          <aside class="preview-pane">
            <div class="card-head"><h2>展示端实时预览</h2><span class="muted">只读 GET · 不注入草稿</span></div>
            <div class="preview-controls">
              <select v-model="previewTarget">
                <option v-for="t in previewTargets" :key="t.value" :value="t.value">{{ t.label }}</option>
              </select>
              <select v-model.number="previewScale">
                <option :value="0.4">40%</option><option :value="0.5">50%</option><option :value="0.65">65%</option>
              </select>
              <button class="btn ghost small" @click="refreshPreview">刷新</button>
              <button class="btn ghost small" @click="previewEnabled = !previewEnabled">{{ previewEnabled ? '暂停' : '恢复' }}</button>
            </div>
            <div v-if="previewEnabled" class="preview-box" :style="previewBoxStyle">
              <iframe :key="previewUrl" :src="previewUrl" :style="previewFrameStyle"
                      sandbox="allow-scripts allow-same-origin allow-popups"
                      referrerpolicy="no-referrer" title="展示端实时预览"></iframe>
            </div>
            <div v-else class="empty">预览已暂停，不会加载展示页（省渲染资源）。</div>
            <p class="muted">iframe 里是真实展示页，它自己 GET 已保存的设置。未保存的修改请先点「保存设置」，保存后这里会自动刷新；控制台不会向 iframe 注入草稿配置。</p>
            <div class="row tight">
              <span :class="settingsDirty ? 'tag warn' : 'tag ok'">{{ settingsDirty ? '有未保存的修改' : '预览与后端已同步' }}</span>
              <a class="link" :href="previewTarget" target="_blank">新窗口打开 ↗</a>
            </div>
          </aside>
          </div>
        </template>

        <!-- ============ 系统 ============ -->
        <template v-else-if="activeView === 'system'">
          <section class="card">
            <div class="card-head"><h2>本机进程与窗口</h2><span class="muted">这些操作只在控制台提供，展示端不参与</span></div>
            <div class="chain">
              <div class="chain-row"><span class="chain-key">3D 打印台</span><span class="muted">/web/index.html</span><button class="btn small" @click="openPrinter">打开窗口</button></div>
              <div class="chain-row"><span class="chain-key">直播小窗</span><span class="muted">需先设置默认直播间号</span><button class="btn small" @click="openLiveWindow">打开窗口</button></div>
              <div class="chain-row"><span class="chain-key">数据桥</span><span :class="status && status.bridge && status.bridge.ok ? 'tag ok' : 'tag mute'">{{ status && status.bridge && status.bridge.ok ? status.bridge.url : '未启动' }}</span><button class="btn small" @click="toggleBridge">{{ status && status.bridge && status.bridge.ok ? '停止' : '启动' }}</button></div>
            </div>
          </section>
          <section class="card">
            <div class="card-head"><h2>运行信息</h2></div>
            <div class="chain">
              <div class="chain-row"><span class="chain-key">服务地址</span><span class="mono muted">{{ connection.host }}</span></div>
              <div class="chain-row"><span class="chain-key">连通状态</span><span :class="connection.ok === true ? 'tag ok' : 'tag bad'">{{ connection.detail }}</span></div>
              <div class="chain-row"><span class="chain-key">角色字段 / 包字段</span><span class="mono muted">{{ schema ? schema.characterFields.length : 0 }} / {{ schema ? schema.packFields.length : 0 }}</span></div>
              <div class="chain-row"><span class="chain-key">工作台主题</span><span class="muted">仅影响控制台自身，与展示端主题无关</span><button class="btn small" @click="theme = theme === 'dark' ? 'light' : 'dark'">切换</button></div>
            </div>
          </section>
          <section class="card">
            <div class="card-head"><h2>数据层（SQLite）</h2>
              <button class="btn ghost small" @click="loadDbInfo">刷新</button></div>
            <div v-if="dbError" class="empty">数据层状态读取失败：{{ dbError }}</div>
            <template v-else-if="dbInfo">
              <div class="chain">
                <div class="chain-row"><span class="chain-key">运行时数据源</span><span class="tag ok">{{ dbInfo.backend }} · schema v{{ dbInfo.schemaVersion }}</span><span class="mono muted">{{ dbInfo.dbPath }}</span></div>
                <div class="chain-row"><span class="chain-key">完整性</span><span :class="dbInfo.integrity === 'ok' ? 'tag ok' : 'tag bad'">{{ dbInfo.integrity }}</span><span class="muted">{{ dbInfo.sizeBytes }} 字节</span></div>
                <div class="chain-row" v-if="dbInfo.migratedFrom"><span class="chain-key">首次迁移</span><span class="muted">已从 JSON 导入 {{ dbInfo.migratedFrom.packs }} 包 / {{ dbInfo.migratedFrom.media }} 图片 / {{ dbInfo.migratedFrom.audit }} 条日志</span><span class="mono muted">{{ dbInfo.migratedAt }}</span></div>
              </div>
              <div class="audit-metrics">
                <div class="metric" v-for="r in dbTableRows(dbInfo)" :key="r.key">
                  <div class="metric-label">{{ r.label }}</div><div class="metric-value mono">{{ r.count }}</div>
                </div>
              </div>
              <p class="muted">SQLite 是运行时唯一数据源；<code>data/packs/*.json</code>、<code>settings.json</code>、<code>media/index.json</code> 是同步落盘的分发 / 备份镜像。手改 JSON 后用 <code>python -m printcast --db import</code> 导入，改库后用 <code>--db export</code> 导出，<code>--db verify</code> 自检。</p>
            </template>
            <div v-else class="empty">正在读取数据层状态…</div>
          </section>
        </template>

        <!-- ============ 操作日志（P1：服务端埋点、可回溯）============ -->
        <template v-else-if="activeView === 'audit'">
          <div class="audit-metrics">
            <div class="metric"><div class="metric-label">记录总数</div><div class="metric-value mono">{{ auditStats.total }}</div><div class="metric-sub">上限 {{ auditStats.limit }}</div></div>
            <div class="metric"><div class="metric-label">成功</div><div class="metric-value mono ok-text">{{ auditStats.ok }}</div><div class="metric-sub">HTTP 2xx / 3xx</div></div>
            <div class="metric"><div class="metric-label">失败</div><div class="metric-value mono err-text">{{ auditStats.failed }}</div><div class="metric-sub">4xx / 5xx</div></div>
            <div class="metric"><div class="metric-label">最近一条</div><div class="metric-value mono small-value">{{ auditStats.lastAt ? fmtTime(auditStats.lastAt).slice(-8) : '—' }}</div><div class="metric-sub">{{ auditStats.lastAt ? fmtTime(auditStats.lastAt).slice(0, 10) : '尚无记录' }}</div></div>
          </div>
          <section class="card">
            <div class="card-head"><h2>本机写操作</h2><span class="muted">{{ auditLoading ? '读取中…' : '服务端统一埋点 · 最近 100 条' }}</span></div>
            <div class="row tight audit-tools">
              <select v-model="auditAction" class="grow">
                <option value="">全部动作</option>
                <option v-for="a in auditStats.actions" :key="a" :value="a">{{ auditLabel(a) }}</option>
              </select>
              <input v-model="auditQuery" placeholder="关键词（动作 / 目标 / 说明）" class="grow" @keyup.enter="loadAudit" />
              <label class="switch"><input type="checkbox" v-model="auditOnlyFailed" /><span class="track"></span>仅看失败</label>
              <button class="btn small" @click="loadAudit">搜索 / 刷新</button>
              <button class="btn danger small" @click="ask('clear-audit')">清空日志</button>
            </div>
            <div v-if="!auditEntries.length" class="empty">暂无匹配的记录。到「内容包」「控制台设置」或「剧本播放」做一次写操作，这里就会出现对应条目。</div>
            <table v-else>
              <thead><tr><th>时间</th><th>动作</th><th>目标</th><th>结果</th><th>说明</th></tr></thead>
              <tbody>
                <tr v-for="e in auditEntries" :key="e.id">
                  <td class="mono nowrap">{{ fmtTime(e.at) }}</td>
                  <td>{{ auditLabel(e.action) }}<div class="mono muted tiny-text">{{ e.action }}</div></td>
                  <td class="mono ellipsis">{{ e.target || '—' }}</td>
                  <td><span :class="e.ok ? 'tag ok' : 'tag bad'">{{ e.ok ? '成功' : '失败' }} · {{ e.status }}</span></td>
                  <td class="muted">{{ e.detail || '—' }}</td>
                </tr>
              </tbody>
            </table>
            <p class="muted hint-line">覆盖设置 / 内容包 / 图片 / 广播 / 数据桥 / 窗口等全部本机写操作，由服务端记录（不靠浏览器上报），失败动作同样留痕；展示端高频信令不记录。数据只写在本机 <code>data/audit.jsonl</code>，超过上限自动淘汰最旧记录。清空后会保留一条「清空操作日志」记录，可回溯性不中断。</p>
          </section>
        </template>

        <footer class="page-foot muted">printcast · 控制台写配置，展示端只读取并渲染 · 所有数据留在本机</footer>
      </main>
    </div>

    <div v-if="message" class="toast ok">{{ message }}</div>
    <div v-else-if="error" class="toast err">{{ error }}</div>

    <!-- P1：内容包抽屉（点标题打开，ESC / 点遮罩关闭）-->
    <div v-if="drawer" class="drawer-layer" @click.self="requestCloseDrawer">
      <aside class="drawer">
        <div class="drawer-head">
          <div>
            <div class="eyebrow">内容包 · {{ drawer.mode === 'edit' ? '编辑中' : '只读查看' }}</div>
            <h2>{{ drawer.draft.title || drawer.sourceId }}</h2>
            <div class="muted mono">{{ drawer.draft.id }} · {{ (drawer.draft.characters || []).length }} 位人物</div>
          </div>
          <div class="drawer-head-actions">
            <button v-if="drawer.mode === 'view'" class="btn primary small" @click="startEdit">编辑</button>
            <template v-else>
              <button class="btn ghost small" @click="cancelEdit">取消</button>
              <button class="btn primary small" :disabled="drawerBusy" @click="saveDrawer">{{ drawerBusy ? '保存中…' : '保存' }}</button>
            </template>
            <button class="btn ghost small" @click="requestCloseDrawer">关闭</button>
          </div>
        </div>
        <div v-if="drawerConfirmClose" class="inline-confirm bar">
          有未保存的修改，确定放弃？
          <button class="btn danger small" @click="closeDrawer">放弃修改</button>
          <button class="btn ghost small" @click="drawerConfirmClose = false">继续编辑</button>
        </div>
        <div v-if="drawerErrors.length" class="drawer-errors">
          <b>后端校验未通过，未写入任何数据：</b>
          <ul><li v-for="(e, i) in drawerErrors.slice(0, 20)" :key="i">行 {{ e.line }} · {{ e.field }}：{{ e.message }}</li></ul>
        </div>
        <div class="drawer-body">
          <div v-if="drawer.mode === 'edit'" class="row">
            <label>内容包 ID<input v-model="drawer.draft.id" /></label>
            <label>标题<input v-model="drawer.draft.title" /></label>
            <label>出场模式<select v-model="drawer.draft.mode"><option value="sequence">sequence</option><option value="weighted">weighted</option><option value="trigger">trigger</option></select></label>
            <label class="switch"><input type="checkbox" v-model="drawer.draft.loop" /><span class="track"></span>循环</label>
          </div>
          <div v-if="drawer.mode === 'edit'" class="row"><label>说明<input v-model="drawer.draft.description" placeholder="可选" /></label></div>
          <p v-if="drawer.mode === 'edit' && drawer.draft.id !== drawer.sourceId" class="muted hint-line">ID 已改变：保存会另存为新包，原包 <code>{{ drawer.sourceId }}</code> 仍保留。</p>

          <div class="drawer-section-head">
            <h3>人物表</h3>
            <div v-if="drawer.mode === 'edit'" class="row tight">
              <button class="btn small" @click="addCharacter">＋ 添加人物</button>
              <button class="btn ghost small" @click="duplicatePack({ id: drawer.sourceId, title: drawer.draft.title })">复制成新包</button>
              <button class="btn ghost small" @click="exportPack({ id: drawer.sourceId })">导出 JSON</button>
            </div>
            <div v-else class="row tight">
              <button class="btn ghost small" @click="duplicatePack({ id: drawer.sourceId, title: drawer.draft.title })">复制成新包</button>
              <button class="btn ghost small" @click="exportPack({ id: drawer.sourceId })">导出 JSON</button>
            </div>
          </div>
          <table class="char-table">
            <thead><tr><th>头像</th><th>ID / 名称</th><th>顺序 / 权重</th><th>标签</th><th>台词</th><th v-if="drawer.mode === 'edit'"></th></tr></thead>
            <tbody>
              <tr v-for="(c, i) in drawer.draft.characters" :key="i">
                <td>
                  <span class="tl-avatar small">
                    <img v-if="charAvatar(c)" :src="charAvatar(c)" :alt="c.name" />
                    <template v-else>{{ (c.name || '?').slice(0, 1) }}</template>
                  </span>
                  <select v-if="drawer.mode === 'edit'" v-model="c.avatar" class="mini-select">
                    <option value="">默认头像</option>
                    <option v-for="m in media" :key="m.id" :value="m.id">{{ m.name }}</option>
                  </select>
                </td>
                <td>
                  <template v-if="drawer.mode === 'edit'"><input v-model="c.id" /><input v-model="c.name" /></template>
                  <template v-else><b>{{ c.name }}</b><div class="mono muted tiny-text">{{ c.id }}</div></template>
                </td>
                <td>
                  <template v-if="drawer.mode === 'edit'"><input type="number" v-model.number="c.order" /><input type="number" v-model.number="c.weight" step="0.1" /></template>
                  <span v-else class="mono">#{{ c.order }} · w{{ c.weight }}</span>
                </td>
                <td>
                  <input v-if="drawer.mode === 'edit'" v-model="c.tags" placeholder="分号分隔" />
                  <span v-else class="muted">{{ tagsText(c) }}</span>
                </td>
                <td>
                  <textarea v-if="drawer.mode === 'edit'" v-model="c.speech" rows="2"></textarea>
                  <span v-else class="muted speech-cell">{{ c.speech || '—' }}</span>
                </td>
                <td v-if="drawer.mode === 'edit'" class="nowrap">
                  <button class="btn ghost tiny" :disabled="i === 0" @click="moveCharacter(i, -1)">↑</button>
                  <button class="btn ghost tiny" :disabled="i === drawer.draft.characters.length - 1" @click="moveCharacter(i, 1)">↓</button>
                  <button class="btn danger tiny" @click="removeCharacter(i)">×</button>
                </td>
              </tr>
              <tr v-if="!drawer.draft.characters.length"><td colspan="6" class="empty">这个包还没有人物，点「＋ 添加人物」开始。</td></tr>
            </tbody>
          </table>
          <p class="muted hint-line">保存走 <code>POST /__api/packs</code>，后端按 schema 逐字段校验；标签用分号分隔，头像从「图片资源」里选。修改会写入本机 <code>data/packs/&lt;id&gt;.json</code>，并记一条操作日志。</p>
        </div>
      </aside>
    </div>
  </div>
</template>

<style>
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0b1018; --surface: #141d29; --surface-2: #1b2636; --border: #2a374a;
  --text: #e8eef8; --muted: #8fa2bb; --accent: #6ea8ff; --accent-soft: #1c2f4d;
  --ok: #43d39a; --ok-soft: #10281e; --warn: #e6b968; --warn-soft: #2a2113;
  --danger: #f37d74; --danger-soft: #2c191a;
}
:root[data-theme="light"] {
  color-scheme: light;
  --bg: #f2f5fa; --surface: #ffffff; --surface-2: #f5f8fc; --border: #dfe6ef;
  --text: #182337; --muted: #66788f; --accent: #2f6fd0; --accent-soft: #e7f0ff;
  --ok: #0f8a58; --ok-soft: #e6f6ed; --warn: #9a6b0b; --warn-soft: #fbf1da;
  --danger: #c33a35; --danger-soft: #fdeceb;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.6 system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.muted { color: var(--muted); font-size: 13px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.app-shell { min-height: 100vh; }

.topbar { position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: 20px;
  padding: 10px 20px; background: var(--surface); border-bottom: 1px solid var(--border); }
.brand { display: flex; align-items: center; gap: 11px; }
.logo { width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center;
  background: var(--accent); color: #fff; font-size: 15px; font-weight: 600; }
.brand-name { font-size: 15px; font-weight: 600; line-height: 1.2; }
.brand-name span { font-weight: 400; color: var(--muted); }
.brand-sub { font-size: 11.5px; color: var(--muted); }
.lights { display: flex; gap: 14px; align-items: center; margin-left: 12px; }
.light { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--muted); }
.light-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.light.on .light-dot { background: var(--ok); }
.light.on { color: var(--text); }
.topbar-actions { margin-left: auto; display: flex; gap: 7px; }

.layout { display: flex; align-items: flex-start; }
.sidebar { position: sticky; top: 55px; width: 190px; flex: 0 0 190px; height: calc(100vh - 55px);
  padding: 18px 12px; border-right: 1px solid var(--border); background: var(--surface);
  display: flex; flex-direction: column; gap: 16px; overflow-y: auto; }
.nav-title { font-size: 11px; letter-spacing: .09em; color: var(--muted); padding: 0 10px 5px; }
.nav-item { display: block; width: 100%; text-align: left; padding: 7px 11px; margin: 2px 0;
  border: 0; border-radius: 8px; background: transparent; color: var(--muted);
  font: inherit; font-size: 13px; cursor: pointer; }
.nav-item:hover { background: var(--surface-2); color: var(--text); }
.nav-item.active { background: var(--accent-soft); color: var(--accent); }
.sidebar-foot { margin-top: auto; padding: 10px; border-top: 1px solid var(--border); font-size: 12px; }

.workspace { flex: 1; min-width: 0; max-width: 1240px; padding: 22px 26px 70px; }
.view-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.view-head h1 { margin: 0; font-size: 20px; font-weight: 600; letter-spacing: -.01em; }
.view-head p { margin: 2px 0 0; }
.page-foot { margin-top: 28px; font-size: 12px; }

.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 18px 20px; margin-bottom: 14px; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.card-head h2 { margin: 0; font-size: 14px; font-weight: 600; }

.seg { display: inline-flex; padding: 3px; gap: 3px; background: var(--surface-2);
  border: 1px solid var(--border); border-radius: 10px; }
.seg-btn { border: 0; background: transparent; color: var(--muted); font: inherit;
  font-size: 13px; padding: 7px 14px; border-radius: 7px; cursor: pointer; }
.seg-btn:hover { color: var(--text); }
.seg-btn.active { background: var(--accent); color: #fff; }
.banner { padding: 10px 14px; border-radius: 9px; margin-bottom: 12px; font-size: 13px; border: 1px solid transparent; }
.banner.err { background: var(--danger-soft); color: var(--danger); border-color: var(--danger); }
.empty { padding: 18px; border: 1px dashed var(--border); border-radius: 9px; color: var(--muted); font-size: 13px; }

.hero { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; padding: 20px 22px; }
.hero-main { display: flex; align-items: center; gap: 16px; min-width: 260px; flex: 1; }
.avatar { width: 54px; height: 54px; flex: 0 0 54px; border-radius: 50%; display: grid; place-items: center;
  background: var(--accent-soft); color: var(--accent); font-size: 20px; }
.eyebrow { font-size: 12px; color: var(--muted); }
.hero-title { font-size: 20px; font-weight: 600; line-height: 1.35; }
.hero-actions { display: flex; gap: 7px; flex-wrap: wrap; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.metric { background: var(--surface-2); border-radius: 10px; padding: 13px 15px; }
.metric-label { font-size: 12.5px; color: var(--muted); }
.metric-value { font-size: 25px; line-height: 1.25; margin-top: 3px; }
.metric-value .unit { font-size: 12px; color: var(--muted); margin-left: 3px; }
.metric-sub { font-size: 11.5px; color: var(--muted); }
.two-col { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 14px; }
.event-list { max-height: 190px; overflow-y: auto; font-size: 12.5px; }
.event-row { display: flex; gap: 12px; padding: 5px 0; border-bottom: 1px solid var(--border); }
.event-time { color: var(--muted); flex: 0 0 68px; }
.chain { display: flex; flex-direction: column; gap: 2px; }
.chain-row { display: flex; align-items: center; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--border); font-size: 13px; flex-wrap: wrap; }
.chain-key { flex: 0 0 120px; color: var(--muted); }
.chain-row .btn { margin-left: auto; }
.tag { display: inline-block; padding: 2px 9px; border-radius: 99px; font-size: 11.5px; }
.tag.ok { background: var(--ok-soft); color: var(--ok); }
.tag.bad { background: var(--danger-soft); color: var(--danger); }
.tag.warn { background: var(--warn-soft); color: var(--warn); }
.tag.mute { background: var(--surface-2); color: var(--muted); }

.btn { font: inherit; font-size: 13px; padding: 7px 13px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--border); background: var(--surface-2); color: var(--text); white-space: nowrap; }
.btn:hover:not(:disabled) { border-color: var(--accent); }
.btn:disabled { opacity: .45; cursor: default; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn.ghost { background: transparent; }
.btn.danger { background: transparent; color: var(--danger); border-color: var(--danger); }
.btn.small { padding: 4px 10px; font-size: 12px; }
.btn.tiny { padding: 1px 7px; font-size: 12px; }

.row { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; margin: 10px 0; }
.row.tight { margin-top: 14px; }
.field-label { font-size: 12.5px; color: var(--muted); align-self: center; }
label { display: flex; flex-direction: column; gap: 5px; font-size: 12.5px; color: var(--muted); flex: 1 1 190px; min-width: 0; }
input, select, textarea { width: 100%; font: inherit; font-size: 13px; padding: 8px 10px;
  color: var(--text); background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; outline: none; }
input:focus, select:focus, textarea:focus { border-color: var(--accent); }
input[type="file"] { padding: 7px; }
textarea { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; resize: vertical; }
.grow { flex: 1 1 200px; }
.color-row { display: flex; gap: 8px; align-items: center; }
.color-row input[type="color"] { width: 40px; height: 36px; padding: 2px; flex: 0 0 40px; }
.color-row input[type="text"], .color-row input:not([type]) { flex: 1; }
.link-row { display: flex; gap: 7px; align-items: center; flex: 0 0 100%; }
.link-row input { flex: 1; }
.checks { display: flex; flex-wrap: wrap; gap: 9px 20px; margin: 10px 0; }
.switch { display: inline-flex; flex-direction: row; align-items: center; gap: 8px; flex: 0 0 auto;
  color: var(--text); font-size: 12.5px; cursor: pointer; }
.switch input { position: absolute; opacity: 0; width: 0; height: 0; }
.track { position: relative; width: 32px; height: 18px; flex: 0 0 32px; border-radius: 99px;
  background: var(--border); transition: background .15s; }
.track::after { content: ''; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px;
  border-radius: 50%; background: #fff; transition: transform .15s; }
.switch input:checked + .track { background: var(--accent); }
.switch input:checked + .track::after { transform: translateX(14px); }
.switch input:focus-visible + .track { outline: 2px solid var(--accent); outline-offset: 2px; }

.settings-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 11px 14px;
  border: 1px solid var(--border); border-radius: 10px; background: var(--surface); margin-bottom: 14px; }
.settings-bar .muted { margin-left: auto; display: inline-flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.group { padding: 0; overflow: hidden; }
.group-head { width: 100%; display: flex; justify-content: space-between; align-items: center;
  padding: 13px 18px; border: 0; background: transparent; color: var(--text); font: inherit;
  font-size: 13.5px; cursor: pointer; text-align: left; }
.group-head:hover { background: var(--surface-2); }
.group-body { padding: 4px 18px 18px; border-top: 1px solid var(--border); }
.inline-confirm { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--danger); }
.inline-confirm.bar { display: flex; padding: 10px 14px; margin-bottom: 12px; border-radius: 9px; background: var(--danger-soft); }
.state-line { display: flex; align-items: center; gap: 10px; margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border); }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--border); }
th { font-size: 11.5px; letter-spacing: .05em; color: var(--muted); background: var(--surface-2); }
tbody tr:hover { background: var(--surface-2); }
td.right { text-align: right; }
.media-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(108px, 1fr)); gap: 12px; margin-top: 14px; }
figure { margin: 0; font-size: 11px; }
figure img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; border: 1px solid var(--border); }
figcaption { display: flex; justify-content: space-between; align-items: center; gap: 4px; margin-top: 4px; }
.ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.seq { margin: 14px 0 4px; padding-left: 22px; max-height: 340px; overflow: auto; font-size: 13px; }
.seq li { margin: 4px 0; }
.result { margin-top: 12px; font-size: 13px; }
.result ul { margin: 6px 0; padding-left: 18px; color: var(--danger); }
.result .ok { color: var(--ok); } .result .err { color: var(--danger); }
a.link { color: var(--accent); font-size: 12.5px; text-decoration: none; }
a.link:hover { text-decoration: underline; }
.toast { position: fixed; right: 20px; bottom: 20px; z-index: 40; max-width: 380px;
  padding: 11px 16px; border-radius: 10px; font-size: 13px; border: 1px solid; }
.toast.ok { background: var(--ok-soft); color: var(--ok); border-color: var(--ok); }
.toast.err { background: var(--danger-soft); color: var(--danger); border-color: var(--danger); }

/* —— P1：内容包抽屉 / 时间轴 / 预览 / 日志 —— */
.hidden-file { display: none; }
.nowrap { white-space: nowrap; }
.tiny-text { font-size: 11px; }
.hint-line { margin: 12px 0 0; font-size: 12px; line-height: 1.7; }
.ok-text { color: var(--ok); } .err-text { color: var(--danger); }
.small-value { font-size: 19px; }
.link-btn { padding: 0; border: 0; background: none; color: var(--accent); font: inherit;
  font-size: 13px; cursor: pointer; text-align: left; }
.link-btn:hover { text-decoration: underline; }
.card-head .pack-tools { margin: 0; gap: 8px; align-items: center; }
.sort-select { width: auto; flex: 0 0 128px; min-width: 128px; }
.import-report { padding: 10px 14px; border-radius: 9px; margin-bottom: 12px; font-size: 13px; border: 1px solid; }
.import-report.ok { background: var(--ok-soft); color: var(--ok); border-color: var(--ok); }
.import-report.err { background: var(--danger-soft); color: var(--danger); border-color: var(--danger); }
.import-report ul { margin: 6px 0 0; padding-left: 18px; }

.repro { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 12px;
  padding: 10px 12px; border-radius: 9px; background: var(--surface-2); font-size: 12px; }
.repro-url { flex: 1 1 100%; word-break: break-all; font-size: 11.5px; color: var(--muted); }
.timeline { display: flex; gap: 10px; overflow-x: auto; padding: 4px 2px 14px; }
.tl-card { flex: 0 0 168px; min-height: 158px; display: flex; flex-direction: column; gap: 5px;
  padding: 10px 11px; border: 1px solid var(--border); border-radius: 10px;
  background: var(--surface-2); color: var(--text); font: inherit; text-align: left; cursor: pointer; }
.tl-card:hover { border-color: var(--accent); }
.tl-card.is-selected { border-color: var(--accent); background: var(--accent-soft); }
.tl-card.is-current { border-color: var(--ok); box-shadow: 0 0 0 2px var(--ok); }
.tl-index { font-size: 11px; color: var(--muted); }
.tl-avatar { width: 40px; height: 40px; flex: 0 0 40px; border-radius: 50%; overflow: hidden;
  display: grid; place-items: center; background: var(--bg); color: var(--accent); font-size: 16px; }
.tl-avatar img { width: 100%; height: 100%; object-fit: cover; }
.tl-avatar.big { width: 54px; height: 54px; flex-basis: 54px; font-size: 20px; }
.tl-avatar.small { width: 32px; height: 32px; flex-basis: 32px; font-size: 13px; }
.tl-name { font-weight: 600; font-size: 13px; }
.tl-speech { font-size: 11.5px; color: var(--muted); line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.tl-foot { margin-top: auto; font-size: 10.5px; color: var(--muted); }
.tl-detail { margin-top: 6px; padding: 12px 14px; border-radius: 10px; background: var(--surface-2); }
.tl-detail-head { display: flex; align-items: center; gap: 12px; font-size: 14px; }
.tl-detail p { margin: 6px 0 0; font-size: 12.5px; }

.settings-layout { display: grid; grid-template-columns: minmax(0, 1fr) 400px; gap: 14px; align-items: start; }
.settings-main { min-width: 0; }
.preview-pane { position: sticky; top: 70px; padding: 14px 16px; border: 1px solid var(--border);
  border-radius: 12px; background: var(--surface); }
.preview-controls { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.preview-controls select { flex: 1 1 0; width: auto; min-width: 0; padding: 6px 8px; font-size: 12px; }
.preview-controls .btn { flex: 0 0 auto; }
.preview-box { position: relative; overflow: hidden; border: 1px solid var(--border);
  border-radius: 10px; background: var(--surface-2); }
.preview-box iframe { position: absolute; top: 0; left: 0; width: 1280px; height: 720px;
  border: 0; transform-origin: top left; background: var(--bg); }
.preview-pane p { font-size: 12px; line-height: 1.65; margin: 12px 0 0; }

.audit-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.audit-tools { align-items: center; }
.audit-tools .switch { flex: 0 0 auto; }
.audit-tools input.grow { flex: 1 1 220px; }
.audit-tools select.grow { flex: 1 1 190px; }

.drawer-layer { position: fixed; inset: 0; z-index: 30; display: flex; justify-content: flex-end;
  background: rgba(6, 10, 18, .55); }
.drawer { width: min(880px, 96vw); height: 100%; display: flex; flex-direction: column;
  background: var(--surface); border-left: 1px solid var(--border); box-shadow: -12px 0 40px rgba(0, 0, 0, .25); }
.drawer-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
  padding: 18px 22px; border-bottom: 1px solid var(--border); }
.drawer-head h2 { margin: 4px 0 2px; font-size: 18px; font-weight: 600; }
.drawer-head-actions { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.drawer-body { flex: 1; overflow-y: auto; padding: 16px 22px 40px; }
.drawer-errors { padding: 10px 20px; font-size: 12.5px; background: var(--danger-soft); color: var(--danger); }
.drawer-errors ul { margin: 6px 0 0; padding-left: 18px; }
.drawer-section-head { display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px; margin: 16px 0 8px; }
.drawer-section-head h3 { margin: 0; font-size: 14px; font-weight: 600; }
.drawer-section-head .row { margin: 0; gap: 6px; }
.char-table { table-layout: fixed; }
.char-table th, .char-table td { padding: 7px 6px; vertical-align: top; font-size: 12px; }
.char-table th:nth-child(1) { width: 64px; } .char-table th:nth-child(2) { width: 21%; }
.char-table th:nth-child(3) { width: 15%; } .char-table th:nth-child(4) { width: 17%; }
.char-table input, .char-table textarea, .char-table select { font-size: 12px; padding: 5px 7px; }
.char-table td input + input { margin-top: 4px; }
.mini-select { margin-top: 5px; }
.speech-cell { display: block; line-height: 1.5; }

@media (max-width: 900px) {
  .sidebar { width: 148px; flex-basis: 148px; }
  .workspace { padding: 18px 16px 60px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .two-col { grid-template-columns: minmax(0, 1fr); }
  .lights { display: none; }
  .settings-layout { grid-template-columns: minmax(0, 1fr); }
  .preview-pane { position: static; }
  .audit-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .drawer { width: 100vw; }
}
</style>
