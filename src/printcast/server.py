"""本地静态服务 + 本机控制端点 + 内容包 API。

三件事：
1. 把仓库根当文档根，提供 /web /site /assets 静态文件；
   另外把 /studio 映射到 Vue+Vite 构建产物，把 /media 映射到上传的图片。
2. 暴露 /__ 前缀的本机控制端点，让页面能拉起独立窗口、启停数据桥、
   参与 WebRTC 信令（场景镜像）。
3. 把 /__api/ 前缀交给 api.dispatch：内容包 CRUD、数据模板下载、CSV/JSON 导入、
   图片上传。这部分是真正的业务逻辑，由 printcast/api.py 等模块承担。

鉴权策略：所有 /__ 与 /__api 端点要求 Host 为回环地址
（127.0.0.1 / localhost / ::1）+ 当前端口，且 Sec-Fetch-Site 若存在只能是
same-origin/none；防止别的网站借本地服务读数据或拉进程。
服务只监听 127.0.0.1，不对局域网开放。
"""
import errno
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import (
    BRIDGE_LOG, BRIDGE_ROOM_FILE, CAPTURE_COMPAT_FILE, CREATE_NO_WINDOW,
    HTTP_PORT, HTTP_PORT_FALLBACKS, IS_MAC, LIVE_DEBUG_PORT, PROFILE_DIRS, ROOT,
    find_browser,
)
from . import api, config, settings as settings_module, storage
from .broadcast import BroadcastController, BroadcastError
from .probe import bridge_status, listening, local_get, wait_bridge
from .relay import SceneRelay

# 场景窗口朝向 → 像素尺寸。
SCENE_SIZES = {
    'landscape': (1280, 720),
    'landscape-1080p': (1920, 1080),
    'portrait': (720, 1280),
    'portrait-1080p': (1080, 1920),
}

ROOM_RE = re.compile(r'\d{5,25}')
SCENE_PATH_RE = re.compile(r'/[A-Za-z0-9_\-]+/[A-Za-z0-9_\-]+\.html\?scene=1')


def room_id(raw):
    match = re.fullmatch(r'(?:https?://live\.douyin\.com/)?(\d{5,25})(?:[/?#].*)?', str(raw).strip())
    if not match:
        raise ValueError('请输入有效的直播间号或直播链接')
    return match[1]


def clean_room(raw):
    """从任意字符串里抽出 5–25 位数字的房间号，抽不出返回空串。"""
    digits = ''.join(ch for ch in str(raw or '') if ch.isdigit())[-25:]
    return digits if ROOM_RE.fullmatch(digits) else ''


def open_app_window(url, size=(1280, 720), extra=None):
    """用 Chromium 系浏览器的 --app 模式开一个无地址栏窗口。"""
    exe = find_browser()
    if not exe:
        return False
    if IS_MAC:
        # macOS 从终端拉起 Chrome 不会激活到前台，用 open -na 才能真正弹窗。
        args = ['open', '-na', exe, '--args', '--app=' + url, '--window-size=%d,%d' % size]
    else:
        args = [exe, '--app=' + url, '--window-size=%d,%d' % size]
    if extra:
        args += extra
    subprocess.Popen(args)
    return True


class _BridgeKeeper:
    """持有数据桥子进程的引用，供多个端点共享。

    Handler 是每请求新建的，进程句柄必须放在外部对象上，否则 /__stop-bridge 停不掉。
    """

    def __init__(self):
        self.process = None

    def start(self, room, cdp_port=None):
        if bridge_status()['ok']:
            return dict(ok=True, already=True)
        node = shutil.which('node')
        if not node:
            return dict(ok=False, error='node not found')
        env = os.environ.copy()
        if cdp_port:
            env['PRINTER_CDP_PORT'] = str(cdp_port)
        BRIDGE_ROOM_FILE.write_text(room, encoding='utf-8')
        with open(BRIDGE_LOG, 'ab') as log:
            self.process = subprocess.Popen(
                [node, str(ROOT / 'src' / 'collector' / 'live-collector.mjs'), room],
                cwd=str(ROOT), env=env, stdout=log, stderr=log,
                creationflags=CREATE_NO_WINDOW)
        try:
            return wait_bridge(self.process)
        except RuntimeError as exc:
            return dict(ok=False, error=str(exc))

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None


def auto_start_broadcast(broadcast):
    """控制台设置里 b`autoStart` 为真时，服务启动即按默认参数开播。

    这属于「后端（控制台）功能」：配置由 /__api/settings 提供，展示端不参与。
    内容包缺失或参数非法时静默跳过，绝不让设置问题拖垮 HTTP 服务启动。
    """
    try:
        cfg = settings_module.load_settings().get('broadcast') or {}
        if not cfg.get('autoStart') or not cfg.get('defaultPacks'):
            return None
        return broadcast.start(
            pack_ids=cfg['defaultPacks'],
            strategy=cfg.get('strategy') or 'concat',
            mode=cfg.get('mode') or None,
            loop=cfg.get('loop'))
    except Exception:  # 设置问题绝不能拖垮 HTTP 服务启动
        return None


# 全新 clone 后 web/studio-dist/ 不存在（构建产物不入库）。给一张可读的引导页，
# 而不是让 /studio/ 落到裸 404 —— 后者曾被误报成「工作台连接受阻」。
_STUDIO_NOT_BUILT_HTML = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>printcast 工作台 · 尚未构建</title>
<style>
:root{color-scheme:light}*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
 font:14px/1.7 system-ui,-apple-system,"PingFang SC",sans-serif;background:#f5f7fb;color:#1b2436}
.card{width:min(620px,calc(100vw - 40px));background:#fff;border:1px solid #e3e8f0;
 border-radius:16px;padding:32px 36px;box-shadow:0 8px 30px rgba(20,40,80,.06)}
.brand{display:flex;align-items:center;gap:10px;font-size:13px;color:#4f8cff;letter-spacing:.08em}
h1{margin:18px 0 8px;font-size:22px;font-weight:600}
p{margin:8px 0;color:#5a6678}code{font-family:ui-monospace,Menlo,monospace}
pre{margin:18px 0;padding:14px 16px;background:#0f172a;color:#e6edf7;border-radius:10px;
 font-size:13px;overflow:auto}
.status{margin-top:20px;padding:12px 14px;border-radius:10px;font-size:13px;background:#eef4ff;color:#2b5bb5}
.status.err{background:#fef2f2;color:#b91c1c}.status.ok{background:#ecfdf5;color:#047857}
a{color:#4f8cff}small{color:#8792a4}
@media(prefers-color-scheme:dark){:root{color-scheme:dark}body{background:#0e131c;color:#e6edf7}
 .card{background:#161d29;border-color:#283344;box-shadow:none}h1{color:#fff}p,small{color:#9aa8bd}
 .status{background:#17243c;color:#a9c6ff}.status.ok{background:#102a22;color:#8ee0bd}}
</style></head><body><div class="card">
<div class="brand">&#9639; PRINTCAST / STUDIO</div>
<h1>工作台尚未构建</h1>
<p><code>/studio/</code> 由 Vue + Vite 构建产物提供，产物不随 git 提交。全新克隆后需先构建一次。</p>
<pre>cd 项目根目录
bash scripts/build-studio.sh</pre>
<p>构建会产出 <code>web/studio-dist/</code>（约 90 KB），完成后刷新本页即可。</p>
<div class="status" id="api">正在检测后端连接…</div>
<p><small>后端状态：<span id="apiDetail">—</span> · 展示主页不受影响，可先打开
<a href="/web/index.html">/web/index.html</a>。</small></p>
</div><script>
fetch('/__api/settings').then(function(r){return r.json()}).then(function(d){
 var el=document.getElementById('api');el.className='status ok';
 el.textContent='后端已连通 · 控制台设置可读';document.getElementById('apiDetail').textContent='HTTP 200';
}).catch(function(e){var el=document.getElementById('api');el.className='status err';
 el.textContent='后端请求失败：'+e.message+'（请用 127.0.0.1 或 localhost 访问，并确认端口）';
 document.getElementById('apiDetail').textContent='请求失败';});
</script></body></html>'''


def make_handler(active_port):
    """构造 Handler 类。active_port 决定 Host 校验口径，因此需要闭包传入。"""
    relay = SceneRelay()
    bridge = _BridgeKeeper()
    broadcast = BroadcastController(relay)
    auto_start_broadcast(broadcast)
    started_at = time.time()
    # bridge_status() 会逐个端口探测（每次最多 1.5s）。控制台 2s 轮询一次，
    # 若每次都全量扫描会堆积线程，因此给探测结果加 3s TTL 缓存。
    bridge_cache = {'at': 0.0, 'value': {'ok': False}}
    bridge_lock = threading.Lock()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            # 文档根固定为仓库根：/web/ 页面、/site/ 宣传页、/assets/ 资源都从根解析。
            super().__init__(*a, directory=str(ROOT), **kw)

        def end_headers(self):
            # Ctrl+R 必须立刻读到改过的页面与脚本。
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            super().end_headers()

        # —— 公共工具 ——
        def _guard(self):
            """只允许本机页面调用（防其它网站借用本地服务拉进程）。

            双重校验：Host 必须是本机回环地址 + 当前端口；Sec-Fetch-Site 若存在
            必须是 same-origin/none。后者缺失时仍放行——Safari 等浏览器不发该头，
            而 Host 白名单已能挡住外部站点（跨站 fetch 会带 cross-site）。
            历史上只认 127.0.0.1 且强制要求该头，用 localhost 或非 Chromium
            浏览器打开工作台会整片 403，表现为「连接受阻 / 内容包消失」。
            """
            host = str(self.headers.get('Host', '')).strip()
            if host.startswith('['):                       # [::1]:8080
                host_only = host[1:].split(']', 1)[0]
                port_part = host.split(']', 1)[-1].lstrip(':')
            else:
                host_only, _, port_part = host.partition(':')
            if host_only.lower() not in ('127.0.0.1', 'localhost', '::1'):
                return False
            if port_part and port_part != str(active_port):
                return False
            return self.headers.get('Sec-Fetch-Site', '') in ('', 'same-origin', 'none')

        def _json(self, code, body):
            data = body.encode('utf-8') if isinstance(body, str) else json.dumps(body).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            # do_GET 的路由循环靠「返回值非 None」判断是否已处理。若这里返回 None，
            # 响应发出后仍会掉进 super().do_GET() 的静态回退，再叠一个 404，
            # 浏览器连接被污染并刷出 OSError 41。必须返回哨兵值。
            return True

        def _html(self, code, body):
            data = body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return True

        def send_error(self, code, message=None, explain=None):
            # 浏览器在收到完整响应后会立刻关连接；此时再写 404 会抛
            # OSError: [Errno 41]，把服务日志刷满。写失败就静默忽略。
            try:
                super().send_error(code, message, explain)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def _deny(self, body='{"error":"forbidden"}'):
            return self._json(403, body)

        def _query(self):
            return parse_qs(urlparse(self.path).query)

        def translate_path(self, path):
            """把工作台构建产物与上传媒体映射到真实目录，其余仍按仓库根解析。"""
            clean = path.split('?', 1)[0].split('#', 1)[0]
            if clean == '/studio' or clean.startswith('/studio/'):
                rel = clean[len('/studio'):].lstrip('/') or 'index.html'
                if '..' in rel.split('/') or rel.startswith('/'):
                    return str(ROOT / '__forbidden__')
                return str(config.studio_dist_dir() / rel)
            if clean.startswith('/media/'):
                hit = storage.media_path(clean[len('/media/'):])
                return str(hit) if hit else str(ROOT / '__missing_media__')
            return super().translate_path(path)

        # —— 内容包 API（GET/POST/PUT/DELETE 共用一条 I/O 通道）——
        def _api_call(self):
            if not self._guard():
                return self._deny()
            parsed = urlparse(self.path)
            is_upload = (parsed.path.rstrip('/') == '/__api/media'
                         and self.command == 'POST')
            limit = config.MAX_MEDIA_BYTES if is_upload else config.MAX_JSON_BYTES
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except (TypeError, ValueError):
                length = 0
            if length < 0 or length > limit:
                return self._json(413, {'ok': False,
                                        'error': '请求体超过 %d 字节上限' % limit})
            body = self.rfile.read(length) if length else b''
            headers = {k.lower(): v for k, v in self.headers.items()}
            response = api.dispatch(self.command, parsed.path,
                                    parse_qs(parsed.query), headers, body)
            if response is None:
                return self._json(404, {'ok': False, 'error': '未知的 API 路径'})
            self.send_response(response.status)
            self.send_header('Content-Type', response.content_type)
            self.send_header('Content-Length', str(len(response.body)))
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(response.body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _is_api(self):
            return self.path.split('?', 1)[0].startswith('/__api/')

        # —— 出场广播（有状态，复用闭包里的 relay / broadcast）——
        def _broadcast_call(self):
            if not self._guard():
                return self._deny()
            parsed = urlparse(self.path)
            prefix = '/__api/broadcast'
            sub = parsed.path[len(prefix):].strip('/')
            q = self._query()
            if self.command == 'GET':
                if sub == 'plan':
                    if broadcast.scheduler is None:
                        return self._json(400, {'ok': False, 'error': '尚未开始广播'})
                    count = int(q['count'][0]) if 'count' in q else None
                    return self._json(200, {'ok': True, **broadcast.plan(count)})
                return self._json(200, {'ok': True, 'broadcast': broadcast.state()})

            # POST：action 来自 URL 子路径或 JSON 体的 action 字段。
            try:
                length = int(self.headers.get('Content-Length', '0'))
                body = json.loads(self.rfile.read(length)) if length else {}
            except (ValueError, KeyError, TypeError):
                body = {}
            if not isinstance(body, dict):
                body = {}
            action = (body.get('action') or sub or 'next')
            try:
                if action == 'start':
                    result = broadcast.start(
                        pack_ids=body.get('packs') or body.get('packIds') or [],
                        strategy=body.get('strategy', 'concat'),
                        mode=body.get('mode'),
                        seed=body.get('seed'),
                        loop=body.get('loop'))
                elif action == 'next':
                    result = broadcast.next()
                elif action == 'trigger':
                    result = broadcast.trigger(body.get('charId') or body.get('char_id'))
                elif action == 'reset':
                    result = broadcast.reset()
                elif action == 'plan':
                    result = broadcast.plan(body.get('count'))
                else:
                    return self._json(400, {'ok': False,
                                            'error': '未知的广播动作：%s' % action})
            except BroadcastError as exc:
                return self._json(400, {'ok': False, 'error': str(exc)})
            return self._json(200, {'ok': True, 'broadcast': result})

        # —— 控制台总览：把散落在后端的运行时状态聚合成一次 GET ——
        # 打印队列长度、帧率等属于展示端内存，后端不臆造；控制台只读真实存在的
        # 状态，避免「展示端反向汇报」破坏 console 写 / display 读 的边界。
        def _console_status(self):
            if self.path.split('?', 1)[0] != '/__api/status':
                return None
            if not self._guard():
                return self._deny()
            with bridge_lock:
                now = time.monotonic()
                if now - bridge_cache['at'] > 3.0:
                    try:
                        bridge_cache['value'] = bridge_status()
                    except Exception:
                        bridge_cache['value'] = {'ok': False}
                    bridge_cache['at'] = now
                bridge_state = dict(bridge_cache['value'])
            try:
                counts = {'packs': len(storage.list_packs()),
                          'media': len(storage.list_media())}
            except OSError:
                counts = {'packs': 0, 'media': 0}
            return self._json(200, {
                'ok': True,
                'service': {'port': active_port,
                            'uptimeSeconds': round(time.time() - started_at)},
                'bridge': bridge_state,
                'broadcast': broadcast.state(),
                'counts': counts,
            })

        # —— POST ——
        def do_POST(self):
            if self.path.split('?', 1)[0].startswith('/__api/broadcast'):
                return self._broadcast_call()
            if self._is_api():
                return self._api_call()
            if self.path != '/__scene-message' or not self._guard():
                return self._deny()
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 65536:
                    raise ValueError('bad length')
                body = json.loads(self.rfile.read(length))
                relay.publish(body['client'], body['message'])
                return self._json(200, {'ok': True})
            except (ValueError, KeyError, TypeError):
                return self._json(400, {'error': 'invalid message'})

        def do_PUT(self):
            return self._api_call() if self._is_api() else self._deny()

        def do_DELETE(self):
            return self._api_call() if self._is_api() else self._deny()

        # —— GET ——
        def do_GET(self):
            # 只读存活探针，无需 same-origin 校验：供 ensure_server 判断端口是否
            # 已被本程序的另一实例占用（历史上靠 HTML 里的营销字符串，永远不命中）。
            if self.path == '/__health':
                return self._json(200, {'service': 'printcast', 'root': str(ROOT)})
            # 出场广播与控制台总览（有状态，需接入 relay / broadcast / bridge
            # 闭包）优先于通用 API 分发，否则会被 dispatch 当成未知路径返回 404。
            if self.path.split('?', 1)[0].startswith('/__api/broadcast'):
                return self._broadcast_call()
            status_response = self._console_status()
            if status_response is not None:
                return status_response
            # 内容包 API 的 GET 端点（schema / 模板 / 列表）走同一通道。
            if self._is_api():
                return self._api_call()
            for route in (self._studio_fallback, self._bridge_status,
                          self._scene_events, self._open_live,
                          self._start_bridge, self._stop_bridge, self._open_scene):
                handled = route()
                if handled is not None:
                    return handled
            # 忽略旧版本（no-store 生效前）留下的条件请求头。
            for header in ('If-Modified-Since', 'If-None-Match'):
                if header in self.headers:
                    del self.headers[header]
            return super().do_GET()

        # —— 各端点：返回 None 表示"这不是我的路由" ——
        def _studio_fallback(self):
            if urlparse(self.path).path.rstrip('/') != '/studio':
                return None
            if (config.studio_dist_dir() / 'index.html').is_file():
                return None
            return self._html(200, _STUDIO_NOT_BUILT_HTML)

        def _bridge_status(self):
            if self.path != '/__bridge-status':
                return None
            if not self._guard():
                return self._json(403, {'ok': False})
            return self._json(200, bridge_status())

        def _scene_events(self):
            if not self.path.startswith('/__scene-events?'):
                return None
            if not self._guard():
                return self._deny()
            try:
                q = self._query()
                client = q['client'][0]
                after = int(q['after'][0]) if 'after' in q else None
                return self._json(200, relay.poll(client, after))
            except (ValueError, KeyError):
                return self._json(400, {'error': 'invalid cursor'})

        def _open_live(self):
            if not self.path.startswith('/__open-live'):
                return None
            if not self._guard():
                return self._json(403, {'ok': False, 'error': 'forbidden'})
            q = self._query()
            room = clean_room((q.get('room') or [''])[0])
            if not room:
                return self._json(400, {'ok': False, 'error': 'bad room'})
            size = (720, 1280) if (q.get('portrait') or ['0'])[0] == '1' else (1280, 720)
            extra = None
            if (q.get('debug') or ['0'])[0] == '1':
                extra = [f'--remote-debugging-port={LIVE_DEBUG_PORT}',
                         '--user-data-dir=' + str(PROFILE_DIRS['bridge']),
                         '--lang=zh-CN', '--no-first-run', '--no-default-browser-check',
                         '--disable-backgrounding-occluded-windows',
                         '--disable-renderer-backgrounding',
                         '--disable-background-timer-throttling',
                         '--disable-features=IntensiveWakeUpThrottling,CalculateNativeWinOcclusion']
            if not open_app_window('https://live.douyin.com/' + room, size, extra):
                return self._json(500, {'ok': False, 'error': 'no browser found'})
            return self._json(200, {'ok': True})

        def _start_bridge(self):
            if not self.path.startswith('/__start-bridge'):
                return None
            if not self._guard():
                return self._json(403, {'ok': False, 'error': 'forbidden'})
            q = self._query()
            room = clean_room((q.get('room') or [''])[0])
            if not room:
                try:
                    room = clean_room(BRIDGE_ROOM_FILE.read_text(encoding='utf-8'))
                except OSError:
                    room = ''
            if not room:
                return self._json(400, {'ok': False, 'error': 'no room'})
            result = bridge.start(room, LIVE_DEBUG_PORT if listening(LIVE_DEBUG_PORT) else None)
            return self._json(200 if result.get('ok') else 500, result)

        def _stop_bridge(self):
            if not self.path.startswith('/__stop-bridge'):
                return None
            if not self._guard():
                return self._json(403, {'ok': False, 'error': 'forbidden'})
            bridge.stop()
            return self._json(200, {'ok': True})

        def _open_scene(self):
            if not self.path.startswith('/__open-scene'):
                return None
            if not self._guard():
                return self._json(403, {'ok': False, 'error': 'forbidden'})
            q = self._query()
            spath = (q.get('path') or [''])[0]
            orient = (q.get('orient') or ['landscape'])[0]
            w, h = SCENE_SIZES.get(orient, (1280, 720))
            if not SCENE_PATH_RE.fullmatch(spath):
                return self._json(400, {'ok': False, 'error': 'bad path'})
            size = f'{w},{h}'
            scene_url = f'http://127.0.0.1:{active_port}{spath}'
            if IS_MAC:
                exe = find_browser()
                if not exe:
                    return self._json(500, {'ok': False, 'error': 'no browser found'})
                subprocess.Popen(['open', '-na', exe, '--args', '--app=' + scene_url, '--window-size=' + size])
            else:
                if not open_app_window(scene_url, (w, h)):
                    return self._json(500, {'ok': False, 'error': 'no browser found'})
            return self._json(200, {'ok': True})

        def log_message(self, *args):
            pass

    return Handler


class LocalHTTPServer(ThreadingHTTPServer):
    """浏览器刷新/关闭标签页会中途断开连接，这类断连不该往终端刷 traceback。"""

    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        if isinstance(exc, OSError) and exc.errno in (errno.EPIPE, errno.ECONNRESET):
            return
        super().handle_error(request, client_address)


def ensure_server(preferred_port=None):
    """启动（或复用）本地 HTTP 服务，返回 (base_url, server_or_None)。

    preferred_port 由 CLI 的 --port 传入；缺省时用 config.HTTP_PORT（环境变量
    PRINTCAST_PORT 在进程启动时读取）。显式传参而非改模块属性，是为了避开
    `from ... import HTTP_PORT` 的值绑定陷阱。

    如果目标端口已被本程序的另一实例占用，就复用它并返回 None —— 调用方不应再 shutdown。
    """
    preferred = int(preferred_port or HTTP_PORT)
    ports = (preferred,) + tuple(p for p in HTTP_PORT_FALLBACKS if p != preferred)
    for port in ports:
        if not listening(port):
            continue
        try:
            with local_get(f'http://127.0.0.1:{port}/__health', 3) as response:
                data = json.load(response)
            if data.get('service') == 'printcast':
                return f'http://127.0.0.1:{port}/', None
        except Exception:
            pass

    for port in ports:
        if listening(port):
            continue
        try:
            server = LocalHTTPServer(('127.0.0.1', port), make_handler(port))
        except OSError:
            continue
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f'http://127.0.0.1:{port}/', server

    raise RuntimeError('没有可用端口，请用 PRINTCAST_PORT 指定，或关掉占用 8080-8388 的程序')
