"""桌面层：pywebview 窗口封装 + 子进程编排。

依赖分层：本模块是唯一 import webview 的地方，server/probe/relay 全部不碰它。
这样 --server-only 在没装 pywebview 的空白 venv 里也能跑。
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from .config import (
    BRIDGE_LOG, BRIDGE_ROOM_FILE, CAPTURE_COMPAT_FILE, CREATE_NO_WINDOW,
    LIVE_DEBUG_PORT, PROFILE_DIRS, ROOT,
)
from .probe import bridge_status, listening, wait_bridge
from .server import room_id


def _require_webview():
    try:
        import webview  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            '桌面窗口需要 pywebview：pip install "printcast[desktop]"\n'
            '若只想用浏览器调试，改用 --server-only。'
        ) from exc
    return __import__('webview')


def _launcher_args(*args):
    """统一构造「重新拉起自身」的命令行。装成包后走 -m，源码运行走原脚本。"""
    return [sys.executable, '-m', 'printcast', *args]


class DesktopApi:
    """暴露给 JS 的接口（window.pywebview.api.*）。"""

    def __init__(self, base_url=''):
        self.base_url = base_url.rstrip('/')
        self._live = None
        self._bridge = None
        self._room = None
        self._scene_windows = []
        self._scene_process = None
        self._lock = threading.RLock()
        self.restart_requested = False

    # —— 程序控制 ——
    def restart_program(self):
        with self._lock:
            if self.restart_requested:
                return '正在重启…'
            self.restart_requested = True

        def shutdown():
            webview = _require_webview()
            for win in list(webview.windows)[::-1]:
                win.destroy()

        threading.Timer(0.5, shutdown).start()
        return '正在完整重启程序…'

    # —— 兼容模式（老显卡 / 远程桌面下关闭 GPU 加速）——
    def get_capture_compatibility(self):
        return CAPTURE_COMPAT_FILE.exists()

    def set_capture_compatibility(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError('无效的兼容模式设置')
        if enabled:
            CAPTURE_COMPAT_FILE.write_text('software-rendering', encoding='utf-8')
        else:
            CAPTURE_COMPAT_FILE.unlink(missing_ok=True)
        return self.restart_program()

    # —— 文件 ——
    def save_rules_png(self, data_url):
        webview = _require_webview()
        if (not isinstance(data_url, str)
                or not data_url.startswith('data:image/png;base64,')
                or len(data_url) > 20_000_000):
            raise ValueError('无效的 PNG 图片')
        data = base64.b64decode(data_url.split(',', 1)[1], validate=True)
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('无效的 PNG 图片')
        result = webview.windows[0].create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename='直播打印规则.png',
            file_types=('PNG 图片 (*.png)',))
        if not result:
            return '已取消保存。'
        path = Path(result[0] if isinstance(result, (tuple, list)) else result)
        if path.suffix.lower() != '.png':
            path = path.with_suffix('.png')
        path.write_bytes(data)
        return '已保存 PNG：' + str(path)

    # —— 场景窗口 ——
    def open_scene_window(self, path=None, orient='landscape'):
        if orient not in {'landscape', 'landscape-1080p', 'portrait', 'portrait-1080p'}:
            orient = 'landscape'
        # 独立进程：否则基于进程的窗口捕获会选到控制面板而不是输出窗口。
        if self._scene_process and self._scene_process.poll() is None:
            return '直播小窗已在独立进程运行，请从任务栏切换到直播小窗。'
        self._scene_process = subprocess.Popen(
            _launcher_args('--scene-view', '--scene-orient', orient), cwd=ROOT)
        return '已打开独立进程直播小窗，请重新选择捕获窗口。'

    def resize_scene(self, w, h):
        try:
            w, h = max(200, min(int(w), 4096)), max(200, min(int(h), 4096))
        except (TypeError, ValueError):
            return 'bad size'
        for win in list(self._scene_windows):
            try:
                if not getattr(win, 'closed', False):
                    win.resize(w, h)
            except Exception:
                pass
        return 'ok'

    # —— 直播窗口与采集 ——
    def open_live_room(self, raw):
        with self._lock:
            room = room_id(raw)
            if self._live and self._live.poll() is None:
                if room == self._room:
                    return '直播窗口已打开，请切换登录 / Live window already open — switch to it and log in.'
                # 直接换房间：关旧开新；运行中的数据桥会自动跟随 .bridge-room 切换。
                try:
                    self._live.terminate()
                    self._live.wait(timeout=5)
                except Exception:
                    pass
                self._live = None
            if listening(LIVE_DEBUG_PORT):
                raise RuntimeError(f'端口 {LIVE_DEBUG_PORT} 被占用，请关闭旧直播窗口 / Port busy — close the old live window')
            self._room = room
            BRIDGE_ROOM_FILE.write_text(room, encoding='utf-8')
            env = os.environ.copy()
            env['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = (
                f'--remote-debugging-port={LIVE_DEBUG_PORT} --remote-debugging-address=127.0.0.1')
            self._live = subprocess.Popen(
                _launcher_args('--live-room', room), cwd=ROOT, env=env)
            return '直播窗口已打开，登录后点“开始抓取” / Live window opened — log in, then click Start Capture.'

    def start_capture(self, raw):
        with self._lock:
            room = room_id(raw)
            if not self._live or self._live.poll() is not None or room != self._room:
                raise RuntimeError("请先打开该房间的直播窗口并登录 / Open this room's live window and log in first")
            if self._bridge and self._bridge.poll() is None:
                return '数据桥已在运行 / Bridge already running.'
            if bridge_status()['ok']:
                return '数据桥已在运行，自动跟随换房 / Bridge running — follows room switches automatically.'
            with urllib.request.urlopen(f'http://127.0.0.1:{LIVE_DEBUG_PORT}/json/list', timeout=3) as response:
                pages = json.load(response)
            if not any(re.match(r'https://live\.douyin\.com/' + room + r'(?:[/?#]|$)', p.get('url', '')) for p in pages):
                raise RuntimeError('直播窗口尚未进入该直播间，请先完成登录或验证')
            node = shutil.which('node')
            if not node:
                raise RuntimeError('未找到 Node.js')
            env = os.environ.copy()
            env['PRINTER_CDP_PORT'] = str(LIVE_DEBUG_PORT)
            with open(BRIDGE_LOG, 'ab') as log:
                self._bridge = subprocess.Popen(
                    [node, str(ROOT / 'src' / 'collector' / 'live-collector.mjs'), room],
                    cwd=str(ROOT), env=env, stdout=log, stderr=log,
                    creationflags=CREATE_NO_WINDOW)
            status = wait_bridge(self._bridge)
            return f'数据桥已启动，端口 {status["port"]}，正在连接直播评论。'

    def stop_capture(self, raw=None):
        with self._lock:
            if self._bridge and self._bridge.poll() is None:
                self._bridge.terminate()
                try:
                    self._bridge.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._bridge.kill()
            self._bridge = None
            return '抓取已停止 / Capture stopped.'

    def close(self):
        for proc in (self._scene_process, self._live):
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    pass
        self.stop_capture()


def run_scene_view(base_url, orient='landscape'):
    """独立进程的直播小窗（纯画面，供 OBS 窗口捕获）。"""
    webview = _require_webview()
    from .config import WEBVIEW_GUI
    sizes = {'landscape': (1280, 720), 'landscape-1080p': (1920, 1080),
             'portrait': (720, 1280), 'portrait-1080p': (1080, 1920)}
    width, height = sizes.get(orient, (1280, 720))
    api = DesktopApi(base_url)
    win = webview.create_window('直播小窗 · Avatar Printer',
                                base_url + '/web/live-view.html', js_api=api,
                                width=width, height=height, background_color='#000000',
                                resizable=True)
    api._scene_windows.append(win)
    webview.start(gui=WEBVIEW_GUI, private_mode=False, storage_path=str(PROFILE_DIRS['scene']))


def run_live_room(room):
    """独立的直播间登录窗口（带独立 profile，可扫码登录）。"""
    webview = _require_webview()
    from .config import WEBVIEW_GUI
    webview.settings['REMOTE_DEBUGGING_PORT'] = LIVE_DEBUG_PORT
    room = room_id(room)
    webview.create_window('直播间登录 · ' + room, 'https://live.douyin.com/' + room,
                          width=1180, height=800)
    webview.start(gui=WEBVIEW_GUI, private_mode=False, storage_path=str(PROFILE_DIRS['live']))
