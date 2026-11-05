"""本机进程与端口探测：不依赖第三方库，也不受系统代理干扰。

系统代理（Clash、Charles 等）会拦截对 127.0.0.1 的请求，因此这里一律用
裸 ProxyHandler（空字典）直连。
"""
import json
import socket
import time
import urllib.request

from .config import BRIDGE_PORT_COUNT, BRIDGE_PORT_START, ROOT

_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def local_get(url, timeout_s=1.5):
    """本机健康检查必须直连：系统代理会拦截 127.0.0.1 请求。"""
    return _LOCAL_OPENER.open(url, timeout=timeout_s)


def listening(port):
    with socket.socket() as sock:
        sock.settimeout(.3)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def bridge_status():
    """探测数据桥。identity 必须与本仓库根一致，避免误认其它目录起的桥。"""
    for port in range(BRIDGE_PORT_START, BRIDGE_PORT_START + BRIDGE_PORT_COUNT):
        try:
            with local_get(f'http://127.0.0.1:{port}/health', 1.5) as response:
                data = json.load(response)
            if (data.get('service') == 'avatar-printer'
                    and _norm(data.get('identity', '')) == _norm(str(ROOT))):
                return dict(ok=True, port=port, url=f'ws://127.0.0.1:{port}',
                            # 采集器自报的平台与统计；老版本桥没有这些字段，缺省为空。
                            platform=str(data.get('platform') or ''),
                            room=str(data.get('room') or ''),
                            stats=data.get('stats') if isinstance(data.get('stats'), dict) else {})
        except Exception:
            pass
    return dict(ok=False)


def wait_bridge(process, timeout_s=6.0):
    """等子进程把数据桥拉起来；进程提前退出或超时都抛 RuntimeError。

    6s 而非 3s：node 冷启动要加载采集器模块图（CDP/协议解码）并读头像缓存，
    慢机器上 3s 会把「其实已经起来」误判成超时。
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('数据桥启动失败，请查看 desktop-bridge.log')
        status = bridge_status()
        if status['ok']:
            return status
        time.sleep(.1)
    raise RuntimeError('数据桥启动超时，请查看 desktop-bridge.log')


def _norm(path):
    # Windows 路径大小写不敏感，macOS 默认也不敏感但保留大小写；统一 normcase 后交给平台判断。
    return __import__('os').path.normcase(str(path))
