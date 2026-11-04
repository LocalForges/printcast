"""出场广播的端到端测试：经真实本地 HTTP 服务驱动 BroadcastController。

覆盖 /__api/broadcast 的 start / next / trigger / reset，以及经 SceneRelay
把 view-appearance 推给订阅标签页（/__scene-events 轮询）。
"""
import json
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from printcast import config, samples, storage
from printcast.server import LocalHTTPServer, make_handler

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class BroadcastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        config.DATA_DIR = cls.tmp
        res = samples.seed_builtin_packs()
        assert res['written'], '内置包 seed 失败：%s' % res

        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            cls.port = probe.getsockname()[1]
        cls.server = LocalHTTPServer(('127.0.0.1', cls.port), make_handler(cls.port))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    # —— 请求工具 ——

    def url(self, path):
        return f'http://127.0.0.1:{self.port}{path}'

    def get(self, path):
        req = urllib.request.Request(self.url(path))
        req.add_header('Sec-Fetch-Site', 'same-origin')
        req.add_header('Host', f'127.0.0.1:{self.port}')
        return _OPENER.open(req, timeout=3)

    def post(self, path, body=None):
        data = json.dumps(body or {}).encode('utf-8')
        req = urllib.request.Request(self.url(path), data=data,
                                     headers={'Content-Type': 'application/json',
                                              'Sec-Fetch-Site': 'same-origin',
                                              'Host': f'127.0.0.1:{self.port}'})
        return _OPENER.open(req, timeout=3)

    def jget(self, path):
        with self.get(path) as r:
            return json.load(r)

    def jpost(self, path, body=None):
        with self.post(path, body) as r:
            return r.status, json.load(r)

    # —— 测试 ——

    def test_start_sequence_and_next(self):
        _, data = self.jpost('/__api/broadcast',
                             {'action': 'start', 'packs': ['ming-emperors'],
                              'mode': 'sequence'})
        self.assertTrue(data['broadcast']['active'])
        self.assertEqual(data['broadcast']['mode'], 'sequence')

        _, d1 = self.jpost('/__api/broadcast', {'action': 'next'})
        self.assertEqual(d1['broadcast']['current']['name'], '朱元璋')
        _, d2 = self.jpost('/__api/broadcast', {'action': 'next'})
        self.assertEqual(d2['broadcast']['current']['name'], '朱允炆')

    def test_trigger_mode_named_and_auto(self):
        _, _ = self.jpost('/__api/broadcast',
                          {'action': 'start', 'packs': ['xiyouji'], 'mode': 'trigger'})
        _, d1 = self.jpost('/__api/broadcast', {'action': 'trigger', 'charId': 'wukong'})
        self.assertEqual(d1['broadcast']['current']['name'], '孙悟空')
        _, d2 = self.jpost('/__api/broadcast', {'action': 'trigger'})
        self.assertEqual(d2['broadcast']['current']['name'], '唐僧')

    def test_view_appearance_broadcast_to_subscribers(self):
        # 先记下当前游标，触发后再只轮询新增消息，避免被前面用例的历史消息干扰。
        with self.get('/__scene-events?client=probe&after=0') as r:
            cursor = json.load(r)['cursor']
        self.jpost('/__api/broadcast',
                   {'action': 'start', 'packs': ['xiyouji'], 'mode': 'trigger'})
        self.jpost('/__api/broadcast', {'action': 'trigger', 'charId': 'bajie'})
        with self.get(f'/__scene-events?client=viewer&after={cursor}') as r:
            data = json.load(r)
        types = [m['type'] for m in data['messages']]
        self.assertIn('view-appearance', types)
        ap = next(m for m in data['messages'] if m['type'] == 'view-appearance')
        self.assertEqual(ap['appearance']['name'], '猪八戒')

    def test_reset_clears_state(self):
        self.jpost('/__api/broadcast',
                   {'action': 'start', 'packs': ['honglou'], 'mode': 'sequence'})
        self.jpost('/__api/broadcast', {'action': 'next'})
        _, d = self.jpost('/__api/broadcast', {'action': 'reset'})
        self.assertEqual(d['broadcast']['current'], None)
        self.assertEqual(d['broadcast']['progress']['appeared'], 0)

    def test_start_missing_pack_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.jpost('/__api/broadcast',
                       {'action': 'start', 'packs': ['nope']})
        self.assertEqual(ctx.exception.code, 400)

    def test_schedule_via_server(self):
        data = self.jget('/__api/schedule?pack=ming-emperors&count=3')
        self.assertTrue(data['ok'])
        self.assertEqual([a['name'] for a in data['appearances']],
                         ['朱元璋', '朱允炆', '朱棣'])

    def test_broadcast_get_returns_state(self):
        self.jpost('/__api/broadcast',
                   {'action': 'start', 'packs': ['sanguo'], 'mode': 'sequence'})
        data = self.jget('/__api/broadcast')
        self.assertTrue(data['broadcast']['active'])
        self.assertEqual(data['broadcast']['packIds'], ['sanguo'])


if __name__ == '__main__':
    unittest.main()
