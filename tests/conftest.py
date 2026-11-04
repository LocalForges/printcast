"""让 tests/ 下的 Python 用例在未安装包时也能 import printcast。

正式安装后（`pip install -e .`）这段插入是冗余但无害的 —— sys.path 去重即可。
"""
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)
