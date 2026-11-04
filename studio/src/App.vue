<script setup>
import { onMounted, ref, reactive } from 'vue';
import { api } from './api.js';

const schema = ref(null);
const limits = ref({});
const packs = ref([]);
const media = ref([]);
const message = ref('');
const error = ref('');

const fileInput = ref(null);
const csvText = ref('');
const csvFileName = ref('');
const packMeta = reactive({ id: '', title: '', mode: 'sequence' });
const commit = ref(true);
const importResult = ref(null);
const importing = ref(false);

// —— 出场顺序预览（任务 5）——
const schedPacks = ref([]);
const schedStrategy = ref('concat');
const schedMode = ref('');
const schedCount = ref(20);
const schedResult = ref(null);
const schedLoading = ref(false);

async function loadMeta() {
  try {
    const data = await api.getSchema();
    schema.value = data.schema;
    limits.value = data.schema.limits || {};
  } catch (e) {
    error.value = '读取字段定义失败：' + e.message;
  }
}

async function loadPacks() {
  try {
    const data = await api.listPacks();
    packs.value = data.packs || [];
  } catch (e) {
    error.value = e.message;
  }
}

async function loadMedia() {
  try {
    const data = await api.listMedia();
    media.value = data.media || [];
  } catch (e) {
    error.value = e.message;
  }
}

function flash(msg, isError = false) {
  if (isError) { error.value = msg; message.value = ''; }
  else { message.value = msg; error.value = ''; }
  setTimeout(() => { message.value = ''; error.value = ''; }, 4000);
}

async function downloadTemplate(fmt) {
  try {
    const blob = await api.getTemplate(fmt);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'printcast-template.' + fmt;
    a.click();
    URL.revokeObjectURL(url);
    flash('模板已下载：printcast-template.' + fmt);
  } catch (e) {
    flash('下载失败：' + e.message, true);
  }
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
  if (!packMeta.id || !packMeta.title) {
    flash('请先填写内容包 ID 与标题', true);
    return;
  }
  importing.value = true;
  importResult.value = null;
  try {
    const payload = {
      format: 'csv',
      pack: { id: packMeta.id, title: packMeta.title, mode: packMeta.mode },
      content: csvText.value,
    };
    const data = await api.importData(payload, commit.value);
    importResult.value = data;
    if (data.ok) {
      flash(commit.value ? '导入成功并已保存' : '校验通过，未保存（取消勾选保存后点导入）');
      await loadPacks();
      csvText.value = '';
      csvFileName.value = '';
    } else {
      flash('校验未通过：' + (data.errors || []).length + ' 处错误，未写入', true);
    }
  } catch (e) {
    flash('导入失败：' + e.message, true);
  } finally {
    importing.value = false;
  }
}

async function removePack(id) {
  if (!confirm('确定删除内容包 ' + id + '？')) return;
  try {
    await api.deletePack(id);
    flash('已删除 ' + id);
    await loadPacks();
  } catch (e) {
    flash('删除失败：' + e.message, true);
  }
}

async function upload() {
  const f = fileInput.value?.files?.[0];
  if (!f) { flash('请选择图片', true); return; }
  try {
    const rec = await api.uploadMedia(f);
    flash('上传成功：' + rec.media.name);
    fileInput.value.value = '';
    await loadMedia();
  } catch (e) {
    flash('上传失败：' + e.message, true);
  }
}

async function removeMedia(id) {
  try {
    await api.deleteMedia(id);
    flash('已删除图片');
    await loadMedia();
  } catch (e) {
    flash('删除失败：' + e.message, true);
  }
}

onMounted(async () => {
  // 先取控制台设置，再读广播状态：广播表单的默认值来自设置，顺序不能颠倒。
  await Promise.all([loadMeta(), loadPacks(), loadMedia(), loadSettings()]);
  await bcLoad();
});

// —— 控制台设置（本程序唯一可写配置来源；所有展示页只读）——
// 边界：这里写的设置经 /__api/settings PUT 落盘；前端展示页（index.html /
// broadcast.html / live-view.html / app.zh.mjs）只 GET，不写入任何配置。
const settings = ref(null);
const settingsMsg = ref('');

async function loadSettings() {
  try {
    const data = await api.getSettings();
    settings.value = data.settings;
  } catch (e) {
    error.value = '读取控制台设置失败：' + e.message;
  }
}

async function saveSettings() {
  if (!settings.value) return;
  try {
    const data = await api.saveSettings(settings.value);
    settings.value = data.settings;
    flash('控制台设置已保存，展示页刷新后生效');
    await bcLoad();
  } catch (e) {
    flash('保存失败：' + e.message, true);
  }
}

// —— 出场广播控制（也由控制台统一驱动）——
const bcPacks = ref([]);
const bcStrategy = ref('concat');
const bcMode = ref('');
const bcLoop = ref(false);
const bcState = ref(null);
const bcCharId = ref('');

async function bcLoad() {
  try {
    const data = await api.getBroadcast();
    bcState.value = data.broadcast || {};
    if (bcState.value.active) {
      bcPacks.value = bcState.value.packIds || [];
      bcStrategy.value = bcState.value.strategy || 'concat';
      bcMode.value = bcState.value.mode || '';
      bcLoop.value = !!bcState.value.loop;
    } else if (settings.value && settings.value.broadcast) {
      // 未开播时，控制台里的默认参数就是表单初值：设置真正驱动控制台行为。
      const d = settings.value.broadcast;
      bcPacks.value = d.defaultPacks || [];
      bcStrategy.value = d.strategy || 'concat';
      bcMode.value = d.mode || '';
      bcLoop.value = !!d.loop;
    }
  } catch (e) { /* 尚未开始广播属正常 */ }
}

async function bcStart() {
  if (!bcPacks.value.length) { flash('请至少选择一个内容包', true); return; }
  try {
    await api.broadcast('start', {
      packs: bcPacks.value, strategy: bcStrategy.value,
      mode: bcMode.value || undefined, loop: bcLoop.value,
    });
    await bcLoad();
    flash('出场广播已启动');
  } catch (e) { flash('启动失败：' + e.message, true); }
}

async function bcNext() {
  try { await api.broadcast('next'); await bcLoad(); }
  catch (e) { flash(e.message, true); }
}

async function bcTrigger() {
  try { await api.broadcast('trigger', { charId: bcCharId.value || undefined }); await bcLoad(); }
  catch (e) { flash(e.message, true); }
}

async function bcReset() {
  try { await api.broadcast('reset'); await bcLoad(); flash('广播已重置'); }
  catch (e) { flash(e.message, true); }
}

function ruleLabel(k) {
  return ({
    comment: '评论打印', join: '进场打印', like: '点赞打印',
    follow: '关注打印', gift: '礼物打印', giftVoice: '礼物语音', joinVoice: '进场语音',
  })[k] || k;
}

async function previewSchedule() {
  if (!schedPacks.value.length) { flash('请至少选择一个内容包', true); return; }
  schedLoading.value = true;
  try {
    const data = await api.previewSchedule({
      packs: schedPacks.value,
      strategy: schedStrategy.value,
      mode: schedMode.value || undefined,
      count: schedCount.value || undefined,
    });
    schedResult.value = data;
    flash('已生成出场序列，共 ' + (data.appearances || []).length + ' 个');
  } catch (e) {
    flash('预览失败：' + e.message, true);
  } finally {
    schedLoading.value = false;
  }
}
</script>

<template>
  <div class="studio">
    <header>
      <h1>printcast 数据工作台</h1>
      <p class="muted">内容包 / 数据导入 / 图片上传 —— 全部在本机运行，不上传云端</p>
    </header>

    <div v-if="message" class="banner ok">{{ message }}</div>
    <div v-if="error" class="banner err">{{ error }}</div>

    <section class="card">
      <h2>1 · 内容包列表</h2>
      <p v-if="!packs.length" class="muted">暂无内容包。导入数据后会自动生成。</p>
      <table v-else>
        <thead><tr><th>ID</th><th>标题</th><th>模式</th><th>人物数</th><th></th></tr></thead>
        <tbody>
          <tr v-for="p in packs" :key="p.id">
            <td>{{ p.id }}</td><td>{{ p.title }}</td><td>{{ p.mode }}</td>
            <td>{{ p.count }}</td>
            <td><button class="danger" @click="removePack(p.id)">删除</button></td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card">
      <h2>2 · 模板下载</h2>
      <p class="muted">按模板填写后导入，字段与系统一致。</p>
      <button @click="downloadTemplate('csv')">下载 CSV 模板</button>
      <button @click="downloadTemplate('json')">下载 JSON 模板</button>
    </section>

    <section class="card">
      <h2>3 · 数据导入</h2>
      <div class="row">
        <label>内容包 ID<input v-model="packMeta.id" placeholder="如 ming-emperors" /></label>
        <label>标题<input v-model="packMeta.title" placeholder="如 明朝十六帝" /></label>
        <label>模式
          <select v-model="packMeta.mode">
            <option value="sequence">sequence 顺序</option>
            <option value="weighted">weighted 权重</option>
            <option value="trigger">trigger 触发</option>
          </select>
        </label>
      </div>
      <div class="row">
        <input type="file" accept=".csv" @change="onFile" />
        <span class="muted">{{ csvFileName || '未选择文件' }}</span>
      </div>
      <textarea v-model="csvText" rows="6" placeholder="或直接粘贴 CSV 文本（含表头 id,name,order,...）"></textarea>
      <div class="row">
        <label class="check"><input type="checkbox" v-model="commit" /> 校验通过后立即保存到内容包</label>
        <button :disabled="importing" @click="runImport">{{ importing ? '导入中…' : '导入' }}</button>
      </div>
      <div v-if="importResult" class="result">
        <p :class="importResult.ok ? 'ok' : 'err'">
          {{ importResult.ok ? '✓ 通过' : '✗ 未通过' }}
          · 共 {{ importResult.stats?.total }} 行，接受 {{ importResult.stats?.accepted }}，错误 {{ importResult.stats?.errors }}
        </p>
        <ul v-if="importResult.errors?.length">
          <li v-for="(e, i) in importResult.errors.slice(0, 20)" :key="i">
            行 {{ e.line }} · {{ e.field }}：{{ e.message }}
          </li>
        </ul>
      </div>
    </section>

    <section class="card">
      <h2>4 · 图片上传</h2>
      <div class="row">
        <input ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp" />
        <button @click="upload">上传</button>
        <span class="muted">支持 PNG/JPEG/WebP，单张 ≤ {{ Math.round((limits.maxMediaBytes||0)/1048576) }}MB</span>
      </div>
      <div v-if="media.length" class="media-grid">
        <figure v-for="m in media" :key="m.id">
          <img :src="'/media/' + m.id" :alt="m.name" />
          <figcaption>{{ m.name }}<button class="danger small" @click="removeMedia(m.id)">×</button></figcaption>
        </figure>
      </div>
      <p v-else class="muted">暂无上传图片。</p>
    </section>

    <section class="card">
      <h2>5 · 出场顺序预览</h2>
      <p class="muted">按出场模式与组合策略生成「明朝皇帝 / 故事人物」的出场序列，可一键打开广播页实时推送。</p>
      <div class="row">
        <label>组合策略
          <select v-model="schedStrategy">
            <option value="concat">concat · 顺次</option>
            <option value="interleave">interleave · 轮转穿插</option>
            <option value="merged">merged · 合并排序</option>
          </select>
        </label>
        <label>出场模式（留空=用包的默认）
          <select v-model="schedMode">
            <option value="">默认</option>
            <option value="sequence">sequence 顺序</option>
            <option value="weighted">weighted 权重</option>
            <option value="trigger">trigger 触发</option>
          </select>
        </label>
        <label>数量
          <input type="number" v-model.number="schedCount" min="1" max="300" />
        </label>
      </div>
      <div class="row wrap">
        <span class="muted">内容包：</span>
        <label class="check" v-for="p in packs" :key="p.id">
          <input type="checkbox" :value="p.id" v-model="schedPacks" /> {{ p.title }}
        </label>
      </div>
      <div class="row">
        <button :disabled="schedLoading" @click="previewSchedule">{{ schedLoading ? '生成中…' : '生成出场顺序' }}</button>
        <a class="link" href="/web/broadcast.html" target="_blank">打开出场广播页 ↗</a>
      </div>
      <ol v-if="schedResult" class="seq">
        <li v-for="(a, i) in schedResult.appearances" :key="i">
          <b>{{ a.name }}</b>
          <span class="muted">（{{ a.packId }} · #{{ i + 1 }}<template v-if="a.loop"> · 第{{ a.loop + 1 }}轮</template>）</span>
          <span v-if="a.speech" class="muted">— {{ a.speech }}</span>
        </li>
      </ol>
      <p v-if="schedResult" class="muted">模式 {{ schedResult.mode }} · 策略 {{ schedResult.strategy }} · loop {{ schedResult.loop }}</p>
    </section>

    <section class="card" v-if="settings">
      <h2>6 · 控制台设置 <span class="muted">（唯一可写配置来源）</span></h2>
      <p class="muted">所有展示页（打印台 / 出场广播页 / 直播小窗）只读取这里的配置，不在前端写配置。修改后点「保存设置」，展示页刷新即生效。</p>

      <h3 class="sub">品牌与展示</h3>
      <div class="row">
        <label>站点标题<input v-model="settings.branding.title" placeholder="头像打印机" /></label>
        <label>副标题<input v-model="settings.branding.subtitle" placeholder="直播间弹幕驱动的 3D 打印直播台" /></label>
        <label>强调色<input v-model="settings.branding.accent" placeholder="#4f8cff" /></label>
      </div>
      <label>页脚说明
        <textarea v-model="settings.branding.footer" rows="2" placeholder="本地运行，数据不上传云端"></textarea>
      </label>
      <div class="row">
        <label>覆盖层主文字<input v-model="settings.display.overlayText" placeholder="PRINTCAST 01" /></label>
        <label>覆盖层副文字<input v-model="settings.display.overlaySub" placeholder="正在制作专属头像" /></label>
      </div>
      <div class="row">
        <label>主题
          <select v-model="settings.display.theme">
            <option value="dark">深色</option>
            <option value="light">浅色</option>
          </select>
        </label>
        <label class="check"><input type="checkbox" v-model="settings.display.showDemoBadge" /> 显示「演示模式」徽标</label>
        <label class="check"><input type="checkbox" v-model="settings.display.showAnnounce" /> 显示公告条</label>
      </div>
      <label>公告条文案（留空则只显示下方链接）
        <input v-model="settings.display.announceText" placeholder="由控制台设置，展示端不含硬编码内容" />
      </label>
      <div class="row wrap">
        <span class="muted">页脚链接：</span>
        <label class="check" v-for="(lnk, i) in settings.branding.links" :key="i">
          <input v-model="lnk.label" placeholder="名称" size="8" />
          <input v-model="lnk.href" placeholder="/site/guide.html" size="16" />
          <button class="secondary" @click="settings.branding.links.splice(i, 1)">移除</button>
        </label>
        <button class="secondary" @click="settings.branding.links.push({label:'',href:'/'})">＋ 添加链接</button>
      </div>

      <h3 class="sub">打印机规则</h3>
      <div class="checks">
        <label class="check" v-for="k in ['comment','join','like','follow','gift','giftVoice','joinVoice']" :key="k">
          <input type="checkbox" v-model="settings.printer.rules[k]" /> {{ ruleLabel(k) }}
        </label>
      </div>
      <div class="row">
        <label class="check"><input type="checkbox" v-model="settings.printer.autoDemo" /> 自动演示填充</label>
        <label class="check"><input type="checkbox" v-model="settings.printer.idleFill" /> 空闲自动测试头像</label>
        <label>演示间隔(ms)<input type="number" v-model.number="settings.printer.demoGapMs" min="0" /></label>
      </div>

      <h3 class="sub">出场广播</h3>
      <div class="row wrap">
        <span class="muted">默认内容包：</span>
        <label class="check" v-for="p in packs" :key="p.id">
          <input type="checkbox" :value="p.id" v-model="settings.broadcast.defaultPacks" /> {{ p.title }}
        </label>
      </div>
      <div class="row">
        <label>组合策略
          <select v-model="settings.broadcast.strategy">
            <option value="concat">concat 顺次</option>
            <option value="interleave">interleave 穿插</option>
            <option value="merged">merged 合并</option>
          </select>
        </label>
        <label>出场模式
          <select v-model="settings.broadcast.mode">
            <option value="">默认</option>
            <option value="sequence">sequence</option>
            <option value="weighted">weighted</option>
            <option value="trigger">trigger</option>
          </select>
        </label>
        <label class="check"><input type="checkbox" v-model="settings.broadcast.loop" /> 循环</label>
        <label class="check"><input type="checkbox" v-model="settings.broadcast.autoStart" /> 启动即广播</label>
        <label class="check"><input type="checkbox" v-model="settings.broadcast.speech" /> 语音播报</label>
        <label class="check"><input type="checkbox" v-model="settings.broadcast.scriptedPrint" /> 打到 3D 打印机（讲到谁打谁）</label>
      </div>

      <h3 class="sub">直播</h3>
      <div class="row">
        <label>默认直播间号<input v-model="settings.live.defaultRoom" placeholder="留空则手动输入" /></label>
        <label>平台
          <select v-model="settings.live.platform">
            <option value="douyin">抖音</option>
            <option value="other">其它</option>
          </select>
        </label>
      </div>

      <div class="row">
        <button @click="saveSettings">保存设置</button>
        <span class="muted">{{ settingsMsg }}</span>
      </div>
    </section>

    <section class="card" v-if="settings">
      <h2>7 · 出场广播控制</h2>
      <p class="muted">在此统一启动「讲到谁就打谁」的剧本播放；展示端的广播页与 3D 打印台实时同步。</p>
      <div class="row wrap">
        <span class="muted">内容包：</span>
        <label class="check" v-for="p in packs" :key="p.id">
          <input type="checkbox" :value="p.id" v-model="bcPacks" /> {{ p.title }}
        </label>
      </div>
      <div class="row">
        <label>组合策略
          <select v-model="bcStrategy">
            <option value="concat">concat</option><option value="interleave">interleave</option><option value="merged">merged</option>
          </select>
        </label>
        <label>出场模式
          <select v-model="bcMode">
            <option value="">默认</option><option value="sequence">sequence</option><option value="weighted">weighted</option><option value="trigger">trigger</option>
          </select>
        </label>
        <label class="check"><input type="checkbox" v-model="bcLoop" /> 循环</label>
      </div>
      <div class="row">
        <button class="primary" @click="bcStart">开始广播</button>
        <button @click="bcNext">下一个 ▶</button>
        <button class="secondary" @click="bcReset">重置</button>
      </div>
      <div class="row">
        <input v-model="bcCharId" placeholder="点名角色 ID（可选）" style="flex:1;min-width:160px" />
        <button @click="bcTrigger">点名出场</button>
      </div>
      <p class="muted" v-if="bcState && bcState.active">
        进行中：{{ (bcState.packIds||[]).join(', ') }} · 模式 {{ bcState.mode }} · 已出场 {{ bcState.progress ? bcState.progress.appeared : 0 }}
        <template v-if="bcState.current"> · 当前：{{ bcState.current.name }}</template>
      </p>
      <p class="muted" v-else>尚未开始（或已重置）。</p>
    </section>

    <footer class="muted">
      字段定义由后端驱动：{{ schema ? schema.characterFields.length : 0 }} 个角色字段 /
      {{ schema ? schema.packFields.length : 0 }} 个包字段
    </footer>
  </div>
</template>

<style>
:root { color-scheme: light dark; }
body { margin: 0; font-family: system-ui, -apple-system, "PingFang SC", sans-serif; background: #f5f6f8; }
.studio { max-width: 880px; margin: 0 auto; padding: 24px 16px 64px; }
header h1 { margin: 0 0 4px; font-size: 22px; }
.muted { color: #6b7280; font-size: 13px; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px 18px; margin: 14px 0; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.card h2 { margin: 0 0 12px; font-size: 16px; }
.row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 8px 0; }
label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
label.check { flex-direction: row; align-items: center; gap: 6px; }
input, select, textarea { font: inherit; padding: 6px 8px; border: 1px solid #d1d5db; border-radius: 8px; }
textarea { width: 100%; box-sizing: border-box; font-family: ui-monospace, monospace; font-size: 12px; }
button { font: inherit; padding: 7px 14px; border: 1px solid #2563eb; background: #2563eb; color: #fff; border-radius: 8px; cursor: pointer; }
button:disabled { opacity: .6; cursor: default; }
button.danger { background: #fff; color: #dc2626; border-color: #fca5a5; }
button.small { padding: 2px 7px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #f0f0f0; }
.banner { padding: 9px 12px; border-radius: 8px; margin: 10px 0; font-size: 13px; }
.banner.ok { background: #ecfdf5; color: #047857; }
.banner.err { background: #fef2f2; color: #b91c1c; }
.result { margin-top: 10px; font-size: 13px; }
.result ul { margin: 6px 0; padding-left: 18px; color: #b91c1c; }
.result .ok { color: #047857; } .result .err { color: #b91c1c; }
.media-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 10px; margin-top: 10px; }
figure { margin: 0; text-align: center; font-size: 11px; }
figure img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; border: 1px solid #e5e7eb; }
figcaption { display: flex; justify-content: space-between; align-items: center; gap: 4px; margin-top: 3px; }
.row.wrap { align-items: flex-start; }
.seq { margin: 12px 0 4px; padding-left: 22px; max-height: 320px; overflow: auto; font-size: 14px; }
.seq li { margin: 4px 0; }
a.link { color: #2563eb; font-size: 13px; text-decoration: none; align-self: center; }
a.link:hover { text-decoration: underline; }
.sub { margin: 18px 0 10px; font-size: 14px; color: #374151; border-left: 3px solid #2563eb; padding-left: 8px; }
.checks { display: flex; flex-wrap: wrap; gap: 10px 18px; margin: 8px 0; }
</style>
