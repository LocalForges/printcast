"""兼容入口（薄转发）—— 实际实现已迁至 src/printcast/relay.py。

保留本文件供旧的 sys.path 引用（tests、外部脚本）继续使用。
新代码请用：from printcast.relay import SceneRelay
"""
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1])
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from printcast.relay import SceneRelay  # noqa: E402,F401

__all__ = ['SceneRelay']
