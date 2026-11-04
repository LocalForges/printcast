"""兼容性回归：旧的 sys.path 入口仍然可用，保证 bat 脚本与 guide.html 不失效。

这两个薄转发文件位于 src/desktop/，历史上被 PYTHONPATH 直接指到该目录。
"""
import importlib
import sys
import unittest
from pathlib import Path

DESKTOP = str(Path(__file__).resolve().parents[1] / 'src' / 'desktop')


class ShimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if DESKTOP not in sys.path:
            sys.path.insert(0, DESKTOP)

    def test_desktop_launcher_shim(self):
        mod = importlib.import_module('desktop_launcher')
        for name in ('main', 'ROOT', 'ensure_server', 'bridge_status'):
            self.assertTrue(hasattr(mod, name), name)
        self.assertTrue(mod.ROOT.is_dir())
        self.assertIn('ok', mod.bridge_status())

    def test_scene_relay_shim_is_same_class(self):
        from scene_relay import SceneRelay as Legacy
        from printcast.relay import SceneRelay
        self.assertIs(Legacy, SceneRelay)

    def test_shim_and_package_share_root(self):
        from desktop_launcher import ROOT as legacy_root
        from printcast.config import ROOT
        self.assertEqual(legacy_root, ROOT)


if __name__ == '__main__':
    unittest.main()
