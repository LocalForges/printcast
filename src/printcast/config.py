"""集中配置：路径、端口、平台探测、浏览器候选。

所有可调项优先读环境变量，其次用内置默认值。不引入 pydantic 等第三方依赖，
保持核心层零依赖 —— 这样纯浏览器调试（--server-only）可以在空白 venv 里直接跑。
"""
import os
import shutil
import sys
from pathlib import Path

# —— 路径 ——
# 本文件位于 <repo>/src/printcast/config.py，仓库根为其上两级。
ROOT = Path(__file__).resolve().parents[2]


def env_flag(name, default=False):
    """解析布尔型环境变量：1/true/yes/on 为真，其余为假。"""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


# —— 平台 ——
IS_WIN = sys.platform.startswith('win')
IS_MAC = sys.platform == 'darwin'

# pywebview 的窗口后端：Windows 只有 EdgeChromium，macOS 只有 Cocoa。
WEBVIEW_GUI = 'edgechromium' if IS_WIN else 'cocoa'

# Windows 下隐藏子进程控制台窗口；其它平台该常量不存在，传 0 即可。
CREATE_NO_WINDOW = getattr(__import__('subprocess'), 'CREATE_NO_WINDOW', 0)

# —— 端口 ——
# HTTP 服务首选端口与其回退序列（8080 常被代理、IDE 预览占用）。
HTTP_PORT = int(os.environ.get('PRINTCAST_PORT', '8080'))
HTTP_PORT_FALLBACKS = (8081, 8181, 8088, 8090, 8095, 8282, 8388)

# 采集层（Node）的 WebSocket 端口范围，桌面层用它探测数据桥是否已就绪。
BRIDGE_PORT_START = 8765
BRIDGE_PORT_COUNT = 10

# 直播窗口（WebView2 / WebKit）开启的远程调试端口，采集层靠它挂 CDP。
LIVE_DEBUG_PORT = int(os.environ.get('PRINTCAST_LIVE_DEBUG_PORT', '9224'))

# —— 浏览器 ——
# 按优先级排列：Windows 上 Edge/Chrome 皆可；macOS 上 Safari 不支持 --app 与远程调试端口，只能靠 Chromium 系。
BROWSER_CANDIDATES = (
    (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
     r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
     r'C:\Program Files\Google\Chrome\Application\chrome.exe',
     r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe')
    if IS_WIN else
    ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
     '/Applications/Chromium.app/Contents/MacOS/Chromium',
     '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
     '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
     os.path.expanduser('~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))
    if IS_MAC else
    ('google-chrome', 'chromium', 'chromium-browser', 'microsoft-edge')
)


def find_browser():
    """返回第一个可用的 Chromium 系浏览器路径，找不到返回 None。"""
    for path in BROWSER_CANDIDATES:
        if os.path.isabs(path):
            if os.path.exists(path):
                return path
        else:
            hit = shutil.which(path)
            if hit:
                return hit
    return None


# —— 数据层（内容包 / 导入 / 媒体资产）——
# 用函数动态计算而不是模块级常量，测试可以 monkeypatch DATA_DIR 后立刻生效。
DATA_DIR = Path(os.environ.get('PRINTCAST_DATA_DIR', str(ROOT / 'data'))).resolve()


def packs_dir():
    path = DATA_DIR / 'packs'
    path.mkdir(parents=True, exist_ok=True)
    return path


def media_dir():
    path = DATA_DIR / 'media'
    path.mkdir(parents=True, exist_ok=True)
    return path


def studio_dist_dir():
    """Vue + Vite 工作台的构建产物目录（不存在时工作台返回引导页）。"""
    return ROOT / 'web' / 'studio-dist'


MAX_JSON_BYTES = int(os.environ.get('PRINTCAST_MAX_JSON_BYTES', str(2 * 1024 * 1024)))
MAX_MEDIA_BYTES = int(os.environ.get('PRINTCAST_MAX_MEDIA_BYTES', str(10 * 1024 * 1024)))
ALLOWED_IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp'}

# —— 运行时产物（与 .gitignore 保持一致）——
BRIDGE_LOG = ROOT / 'desktop-bridge.log'
BRIDGE_ROOM_FILE = ROOT / '.bridge-room'
CAPTURE_COMPAT_FILE = ROOT / '.capture-compat'

# WebView 独立配置目录：分开存登录态，避免多窗口抢同一份 profile。
PROFILE_DIRS = {
    'printer': ROOT / '.printer-webview-profile',
    'live': ROOT / '.live-webview-profile',
    'scene': ROOT / '.scene-webview-profile',
    'bridge': ROOT / '.bridge-profile',
}
