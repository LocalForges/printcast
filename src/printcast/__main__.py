"""包入口：python -m printcast 等价于 printcast 命令。"""
import sys

from .cli import main

if __name__ == '__main__':
    sys.exit(main())
