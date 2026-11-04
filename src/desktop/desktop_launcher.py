"""兼容入口（薄转发）—— 实际实现已迁至 src/printcast/ 包。

保留本文件是为了不破坏既有调用方式：
  - macOS / Linux：python src/desktop/desktop_launcher.py --server-only
  - Windows：scripts/*.bat
  - site/guide.html：pythonw desktop_launcher.py --room 房间号 --capture
  - tests/test_native_output.py：from desktop_launcher import ensure_server, ROOT
  - scripts/run-bridge-forever.bat：from desktop_launcher import bridge_status

新代码请直接用：python -m printcast  /  from printcast.server import ensure_server
"""
import sys
from pathlib import Path

# desktop_launcher.py 位于 <repo>/src/desktop/，parents[1] 即 <repo>/src。
# 无论从哪个 cwd 启动、无论 PYTHONPATH 怎么设，都要保证 printcast 包可导入。
_SRC = str(Path(__file__).resolve().parents[1])
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from printcast.cli import main            # noqa: E402,F401
from printcast.config import ROOT        # noqa: E402,F401
from printcast.server import ensure_server  # noqa: E402,F401
from printcast.probe import bridge_status  # noqa: E402,F401

__all__ = ['main', 'ROOT', 'ensure_server', 'bridge_status']

if __name__ == '__main__':
    sys.exit(main())
