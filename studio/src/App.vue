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
  overview: { title: '总览', desc: '实时状态、当前出场与一键干预' },
  broadcast: { title: '出场广播', desc: '启动剧本播放，讲到谁就打谁' },
  packs: { title: '内容包', desc: '管理已导入的角色内容包' },
  import: { title: '数据导入', desc: '下载模板、校验并导入 CSV / JSON' },
  media: { title: '图片资源', desc: '上传与清理头像贴图' },
  schedule: { title: '排期预演', desc: '按策略生成出场序列，不改动实时状态' },
  settings: { title: '控制台设置', desc: '唯一可写配置来源，展示端只读' },
  system: { title: '系统', desc: '数据桥、展示窗口与运行信息' },
};
const NAV = [
  { group: '运行', items: ['overview', 'broadcast'] },
  { group: '资产', items: ['packs', 'import', 'media'] },
  { group: '编排', items: ['schedule'] },
  { group: '配置', items: ['settings', 'system'] },
];
const activeView = ref('overview');
const viewMeta = computed(() => VIEWS[activeView.value] || VIEWS.overview);
function go(view) { activeView.value = view; }

// —— 基础数据 ——
const schema = ref(null);
const limits = ref({});
const packs = ref([]);
const media = ref([]);
const message = ref('');
const error = ref('');
function flash(msg, isError = false) {
  if (isError) { error.value = msg; message.value = ''; }
  else { message.value = msg; error.value = ''; }
  setTimeout(() => { message.value = ''; error.value = ''; }, 4000);
}

// —— 后端连接与总览状态 ——
const connection = reactive({ ok: null, host: '', detail: '正在检测本机服务…' });
const status = ref(null);
const statusError = ref('');
const nowSec = ref(Math.floor(Date.now() / 1000));
let statusTimer = null;

async function refreshStatus() {
  nowSec.value = Math.floor(Date.now() / 1000);
  connection.host = location.host || '(未知)';
  try {
    const data = await api.getStatus();
    status.value = data;
    statusError.value = '';
    connection.ok = true;
    connection.detail = '本机服务已连通 · 端口 ' + data.service.port;
  } catch (e) {
    status.value = null;
    statusError.value = e.message || '无法连接';
    connection.ok = false;
    connection.detail = 'HTTP ' + (e.status || '?') + ' · ' + statusError.value;
  }
}

const bcState = computed(() => (status.value && status.value.broadcast) || { active: false });
const lights = computed(() => [
  { key: 'service', label: '本机服务', on: !!status.value, detail: status.value ? '端口 ' + status.value.service.port : '未连通' },
  { key: 'bridge', label: '数据桥', on: !!(status.value && status.value.bridge && status.value.bridge.ok),
    detail: status.value && status.value.bridge && status.value.bridge.ok ? status.value.bridge.url : '未启动' },
  { key: 'broadcast', label: '出场广播', on: !!bcState.value.active,
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
async function eventLoop() {
  const client = 'studio-' + Math.random().toString(36).slice(2, 10);
  while (eventRunning) {
    try {
      const q = '/__scene-events?client=' + encodeURIComponent(client) +
        (eventCursor === null ? '' : '&after=' + eventCursor);
      const res = await fetch(q, { signal: eventAbort.signal });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      eventCursor = data.cursor;
      const list = data.messages || [];
      for (let i = list.length - 1; i >= 0; i--) {
        events.value.unshift({ time: clockText(), text: eventText(list[i]) });
      }
      if (events.value.length > 40) events.value.length = 40;
    } catch (e) {
      if (!eventRunning) break;
      await new Promise((r) => setTimeout(r, 1500));
    }
  }
}
function startEventLoop() {
  eventAbort = new AbortController();
  eventRunning = true;
  eventLoop();
}
function stopEventLoop() {
  eventRunning = false;
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
      await Promise.all([loadPacks(), refreshStatus()]);
      csvText.value = ''; csvFileName.value = '';
    } else {
      flash('校验未通过：' + (data.errors || []).length + ' 处错误，未写入', true);
    }
  } catch (e) { flash('导入失败：' + e.message, true); }
  finally { importing.value = false; }
}
async function removePack(id) {
  try { await api.deletePack(id); flash('已删除 ' + id); await Promise.all([loadPacks(), refreshStatus()]); }
  catch (e) { flash('删除失败：' + e.message, true); }
}
async function upload() {
  const f = fileInput.value && fileInput.value.files && fileInput.value.files[0];
  if (!f) { flash('请选择图片', true); return; }
  try {
    const rec = await api.uploadMedia(f);
    flash('上传成功：' + rec.media.name);
    fileInput.value.value = '';
    await Promise.all([loadMedia(), refreshStatus()]);
  } catch (e) { flash('上传失败：' + e.message, true); }
}
async function removeMedia(id) {
  try { await api.deleteMedia(id); flash('已删除图片'); await Promise.all([loadMedia(), refreshStatus()]); }
  catch (e) { flash('删除失败：' + e.message, true); }
}

// —— 出场顺序预览 ——
const schedPacks = ref([]);
const schedStrategy = ref('concat');
const schedMode = ref('');
const schedCount = ref(20);
const schedResult = ref(null);
const schedLoading = ref(false);
async function previewSchedule() {
  if (!schedPacks.value.length) { flash('请至少选择一个内容包', true); return; }
  schedLoading.value = true;
  try {
    const data = await api.previewSchedule({
      packs: schedPacks.value, strategy: schedStrategy.value,
      mode: schedMode.value || undefined, count: schedCount.value || undefined,
    });
    schedResult.value = data;
    flash('已生成出场序列，共 ' + (data.appearances || []).length + ' 个');
  } catch (e) { flash('预览失败：' + e.message, true); }
  finally { schedLoading.value = false; }
}

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
    flash('控制台设置已保存，展示页刷新后生效');
    await bcLoad();
  } catch (e) { flash('保存失败：' + e.message, true); }
}
async function applyResetSettings() {
  try {
    const data = await api.resetSettings();
    settings.value = data.settings;
    settingsBaseline.value = JSON.stringify(data.settings);
    settingsDirty.value = false;
    flash('已恢复出厂设置');
  } catch (e) { flash('恢复默认失败：' + e.message, true); }
}
function colorValue(v) { return /^#[0-9a-fA-F]{6}$/.test(v || '') ? v : '#4f8cff'; }

// —— 出场广播控制 ——
const bcPacks = ref([]);
const bcStrategy = ref('concat');
const bcMode = ref('');
const bcLoop = ref(false);
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
    });
    await refreshStatus(); flash('出场广播已启动');
  } catch (e) { flash('启动失败：' + e.message, true); }
}
async function bcNext() {
  try { await api.broadcast('next'); await refreshStatus(); }
  catch (e) { flash(e.message, true); }
}
async function bcTrigger() {
  try { await api.broadcast('trigger', { charId: bcCharId.value || undefined }); await refreshStatus(); }
  catch (e) { flash(e.message, true); }
}
async function bcReset() {
  try { await api.broadcast('reset'); await refreshStatus(); flash('广播已重置'); }
  catch (e) { flash(e.message, true); }
}

// —— 本机窗口与数据桥（后端已实现，控制台此前从未接入）——
async function openPrinter() {
  try { await api.openScene('/web/index.html?scene=1', 'landscape'); flash('已拉起 3D 打印台窗口'); }
  catch (e) { flash('打开打印台失败：' + e.message, true); }
}
async function openLiveWindow() {
  const room = settings.value && settings.value.live && settings.value.live.defaultRoom;
  if (!room) { flash('请先在「控制台设置 → 直播」填写默认直播间号', true); go('settings'); return; }
  try { await api.openLive(room, false); flash('已拉起直播小窗'); }
  catch (e) { flash('打开直播小窗失败：' + e.message, true); }
}
async function toggleBridge() {
  const running = status.value && status.value.bridge && status.value.bridge.ok;
  const room = settings.value && settings.value.live && settings.value.live.defaultRoom;
  try {
    if (running) await api.stopBridge();
    else await api.startBridge(room || undefined);
    await refreshStatus();
    flash(running ? '数据桥已停止' : '数据桥已启动');
  } catch (e) { flash('数据桥操作失败：' + e.message, true); }
}

function ruleLabel(k) {
  return ({
    comment: '评论打印', join: '进场打印', like: '点赞打印',
    follow: '关注打印', gift: '礼物打印', giftVoice: '礼物语音', joinVoice: '进场语音',
  })[k] || k;
}

onMounted(async () => {
  await Promise.all([loadMeta(), loadPacks(), loadMedia(), loadSettings(), refreshStatus()]);
  await bcLoad();
  startEventLoop();
  statusTimer = setInterval(refreshStatus, 2000);
});
onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer);
  stopEventLoop();
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
        <div v-if="pendingConfirm && (pendingConfirm.kind === 'reset-broadcast' || pendingConfirm.kind === 'reset-settings')" class="inline-confirm bar">
          {{ pendingConfirm.kind === 'reset-broadcast' ? '重置会清空当前广播进度，确定？' : '恢复默认会覆盖全部控制台设置，确定？' }}
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
                <div class="muted" v-else>在下方选好内容包后点「开始广播」，或到「出场广播」页配置参数。</div>
              </div>
            </div>
            <div class="hero-actions">
              <button class="btn primary" @click="bcStart">开始 / 重启广播</button>
              <button class="btn" :disabled="!bcState.active" @click="bcNext">下一个</button>
              <button class="btn ghost" :disabled="!bcState.active" @click="ask('reset-broadcast')">重置进度</button>
              <button class="btn ghost" @click="go('broadcast')">点名 / 高级控制 →</button>
            </div>
          </section>

          <div class="metrics">
            <div class="metric"><div class="metric-label">内容包</div><div class="metric-value mono">{{ counts.packs }}</div><div class="metric-sub">已导入</div></div>
            <div class="metric"><div class="metric-label">已出场</div><div class="metric-value mono">{{ bcState.seq || 0 }}</div><div class="metric-sub">本轮广播</div></div>
            <div class="metric"><div class="metric-label">图片资源</div><div class="metric-value mono">{{ counts.media }}</div><div class="metric-sub">已上传</div></div>
            <div class="metric"><div class="metric-label">服务运行</div><div class="metric-value mono">{{ status ? Math.floor(status.service.uptimeSeconds / 60) : 0 }}<span class="unit">分</span></div><div class="metric-sub">自启动</div></div>
          </div>

          <div class="two-col">
            <section class="card">
              <div class="card-head"><h2>实时事件</h2><span class="muted">订阅 /__scene-events · 自动刷新</span></div>
              <div class="event-list">
                <div v-if="!events.length" class="empty">暂无事件。启动广播后，出场、语音、打印入队会实时出现在这里。</div>
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
                <div class="chain-row"><span class="chain-key">出场广播</span><span :class="bcState.active ? 'tag ok' : 'tag mute'">{{ bcState.active ? '进行中' : '待机' }}</span></div>
                <div class="chain-row"><span class="chain-key">剧本打印</span><span class="tag mute">{{ settings && settings.broadcast && settings.broadcast.scriptedPrint ? '已启用' : '已关闭' }}</span></div>
              </div>
              <div class="row tight">
                <button class="btn small" @click="toggleBridge">{{ status && status.bridge && status.bridge.ok ? '停止数据桥' : '启动数据桥' }}</button>
                <a class="link" href="/web/broadcast.html" target="_blank">广播展示页 ↗</a>
                <a class="link" href="/web/index.html" target="_blank">3D 打印台 ↗</a>
              </div>
            </section>
          </div>
        </template>

        <!-- ============ 出场广播 ============ -->
        <template v-else-if="activeView === 'broadcast'">
          <section class="card">
            <div class="card-head"><h2>广播参数</h2><span class="muted">未开播时初值来自控制台设置</span></div>
            <div class="row"><span class="field-label">内容包</span>
              <label class="switch" v-for="p in packs" :key="p.id"><input type="checkbox" :value="p.id" v-model="bcPacks" /><span class="track"></span>{{ p.title }}</label>
            </div>
            <div class="row">
              <label>组合策略<select v-model="bcStrategy"><option value="concat">concat 顺次</option><option value="interleave">interleave 穿插</option><option value="merged">merged 合并</option></select></label>
              <label>出场模式<select v-model="bcMode"><option value="">默认</option><option value="sequence">sequence</option><option value="weighted">weighted</option><option value="trigger">trigger</option></select></label>
              <label class="switch"><input type="checkbox" v-model="bcLoop" /><span class="track"></span>循环</label>
            </div>
            <div class="row">
              <button class="btn primary" @click="bcStart">开始 / 重启广播</button>
              <button class="btn" :disabled="!bcState.active" @click="bcNext">下一个</button>
              <button class="btn ghost" :disabled="!bcState.active" @click="ask('reset-broadcast')">重置</button>
            </div>
            <div class="row">
              <input v-model="bcCharId" placeholder="点名角色 ID（可选）" class="grow" />
              <button class="btn" :disabled="!bcState.active" @click="bcTrigger">点名出场</button>
            </div>
            <div class="state-line">
              <span :class="bcState.active ? 'tag ok' : 'tag mute'">{{ bcState.active ? '进行中' : '待机' }}</span>
              <span class="muted" v-if="bcState.active">{{ (bcState.packIds || []).join(', ') }} · 模式 {{ bcState.mode }} · 已出场 {{ bcState.seq || 0 }}<template v-if="currentChar"> · 当前 {{ currentChar.name }}</template></span>
              <span class="muted" v-else>尚未开始或已重置。</span>
            </div>
          </section>
        </template>

        <!-- ============ 内容包 ============ -->
        <template v-else-if="activeView === 'packs'">
          <section class="card">
            <div class="card-head"><h2>已导入内容包</h2><button class="btn ghost small" @click="loadPacks(); refreshStatus()">刷新</button></div>
            <div v-if="!packs.length" class="empty">暂无内容包。到「数据导入」下载模板并导入，内置示例包仍存放在 <code>data/packs/</code>。</div>
            <table v-else>
              <thead><tr><th>ID</th><th>标题</th><th>模式</th><th>人物数</th><th></th></tr></thead>
              <tbody>
                <tr v-for="p in packs" :key="p.id">
                  <td class="mono">{{ p.id }}</td><td>{{ p.title }}</td><td>{{ p.mode }}</td><td class="mono">{{ p.count }}</td>
                  <td class="right">
                    <span v-if="pendingConfirm && pendingConfirm.kind === 'pack' && pendingConfirm.id === p.id" class="inline-confirm">
                      确定删除？<button class="btn danger small" @click="confirmPending">删除</button><button class="btn ghost small" @click="pendingConfirm = null">取消</button>
                    </span>
                    <button v-else class="btn danger small" @click="ask('pack', p.id)">删除</button>
                  </td>
                </tr>
              </tbody>
            </table>
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

        <!-- ============ 排期预演 ============ -->
        <template v-else-if="activeView === 'schedule'">
          <section class="card">
            <div class="card-head"><h2>生成出场序列</h2><span class="muted">预演不改动实时广播状态</span></div>
            <div class="row">
              <label>组合策略<select v-model="schedStrategy"><option value="concat">concat 顺次</option><option value="interleave">interleave 轮转穿插</option><option value="merged">merged 合并排序</option></select></label>
              <label>出场模式<select v-model="schedMode"><option value="">默认</option><option value="sequence">sequence</option><option value="weighted">weighted</option><option value="trigger">trigger</option></select></label>
              <label>数量<input type="number" v-model.number="schedCount" min="1" max="300" /></label>
            </div>
            <div class="row"><span class="field-label">内容包</span><label class="switch" v-for="p in packs" :key="p.id"><input type="checkbox" :value="p.id" v-model="schedPacks" /><span class="track"></span>{{ p.title }}</label></div>
            <div class="row"><button class="btn primary" :disabled="schedLoading" @click="previewSchedule">{{ schedLoading ? '生成中…' : '生成出场顺序' }}</button><a class="link" href="/web/broadcast.html" target="_blank">打开广播展示页 ↗</a></div>
            <ol v-if="schedResult" class="seq">
              <li v-for="(a, i) in schedResult.appearances" :key="i"><b>{{ a.name }}</b><span class="muted">（{{ a.packId }} · #{{ i + 1 }}<template v-if="a.loop"> · 第{{ a.loop + 1 }}轮</template>）</span><span v-if="a.speech" class="muted">— {{ a.speech }}</span></li>
            </ol>
            <p v-if="schedResult" class="muted">模式 {{ schedResult.mode }} · 策略 {{ schedResult.strategy }} · loop {{ schedResult.loop }}</p>
          </section>
        </template>

        <!-- ============ 控制台设置 ============ -->
        <template v-else-if="activeView === 'settings'">
          <div class="settings-bar" v-if="settings">
            <span :class="settingsDirty ? 'tag warn' : 'tag ok'">{{ settingsDirty ? '有未保存的修改' : '已与后端同步' }}</span>
            <button class="btn primary" :disabled="!settingsDirty" @click="saveSettings">保存设置</button>
            <button class="btn ghost" @click="ask('reset-settings')">恢复默认</button>
            <span class="muted">保存后打开：<a class="link" href="/web/index.html" target="_blank">打印台 ↗</a><a class="link" href="/web/broadcast.html" target="_blank">广播页 ↗</a><a class="link" href="/web/live-view.html" target="_blank">直播小窗 ↗</a></span>
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
              <button class="group-head" @click="openGroups.printer = !openGroups.printer"><span>打印机规则</span><span class="muted">{{ openGroups.printer ? '收起' : '展开' }}</span></button>
              <div v-if="openGroups.printer" class="group-body">
                <div class="checks">
                  <label class="switch" v-for="k in ['comment','join','like','follow','gift','giftVoice','joinVoice']" :key="k"><input type="checkbox" v-model="settings.printer.rules[k]" /><span class="track"></span>{{ ruleLabel(k) }}</label>
                </div>
                <div class="row">
                  <label class="switch"><input type="checkbox" v-model="settings.printer.autoDemo" /><span class="track"></span>自动演示填充</label>
                  <label class="switch"><input type="checkbox" v-model="settings.printer.idleFill" /><span class="track"></span>空闲测试头像</label>
                  <label>演示间隔 (ms)<input type="number" v-model.number="settings.printer.demoGapMs" min="0" /></label>
                  <label>空闲阈值 (秒)<input type="number" v-model.number="settings.printer.idleSeconds" min="0" /></label>
                </div>
              </div>
            </section>

            <section class="card group">
              <button class="group-head" @click="openGroups.broadcast = !openGroups.broadcast"><span>出场广播默认值</span><span class="muted">{{ openGroups.broadcast ? '收起' : '展开' }}</span></button>
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
        </template>

        <footer class="page-foot muted">printcast · 控制台写配置，展示端只读取并渲染 · 所有数据留在本机</footer>
      </main>
    </div>

    <div v-if="message" class="toast ok">{{ message }}</div>
    <div v-else-if="error" class="toast err">{{ error }}</div>
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

@media (max-width: 900px) {
  .sidebar { width: 148px; flex-basis: 148px; }
  .workspace { padding: 18px 16px 60px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .two-col { grid-template-columns: minmax(0, 1fr); }
  .lights { display: none; }
}
</style>
