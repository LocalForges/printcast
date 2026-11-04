"""printcast —— 直播间弹幕驱动的 3D 打印直播台。

四层结构：collector（Node）→ bridge（WebSocket）→ render（浏览器）→ desktop（本进程）。
本包只负责 Python 这一侧：静态文件服务、桌面窗口封装、本机控制端点、WebRTC 信令中继。
"""

__version__ = '0.3.0'
__all__ = ['__version__']
