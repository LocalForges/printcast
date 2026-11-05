"""自动播放（定时器推进）的端到端测试：经真实本地 HTTP 服务验证 play / pause。

验证点：
- start 只初始化，不自动推进（seq=0, playing=false）；
- play 后定时器按 intervalMs 持续 next()，seq 增长、playing=true；
- pause 后停止推进，seq 保持不变；
- 非 loop 序列走完后自动停播（playing=false, seq=total）；
- intervalMs 低于下限返回 400。
"""
import json
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from printcast import config, samples
from printcast.server import LocalHTTPServer, make_handler

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class BroadcastPlayTests(unittest.TestCase):
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

    def url(self, path):
        return f'http://127.0.0.1:{self.port}{path}'

    def post(self, path, body=None):
        data = json.dumps(body or {}).encode('utf-8')
        req = urllib.request.Request(self.url(path), data=data,
                                     headers={'Content-Type': 'application/json',
                                              'Sec-Fetch-Site': 'same-origin',
                                              'Host': f'127.0.0.1:{self.port}'})
        return _OPENER.open(req, timeout=3)

    def jpost(self, path, body=None):
        with self.post(path, body) as r:
            return r.status, json.load(r)

    def jget(self, path):
        req = urllib.request.Request(self.url(path),
                                     headers={'Sec-Fetch-Site': 'same-origin',
                                              'Host': f'127.0.0.1:{self.port}'})
        with _OPENER.open(req, timeout=3) as r:
            return json.load(r)

    def test_start_does_not_auto_advance(self):
        _, data = self.jpost('/__api/broadcast',
                             {'action': 'start', 'packs': ['ming-emperors'],
                              'mode': 'sequence'})
        self.assertTrue(data['broadcast']['active'])
        self.assertFalse(data['broadcast']['playing'])
        self.assertEqual(data['broadcast']['seq'], 0)

    def test_play_advances_and_pause_stops(self):
        self.jpost('/__api/broadcast',
                   {'action': 'start', 'packs': ['ming-emperors'],
                    'mode': 'sequence', 'loop': True})
        _, p = self.jpost('/__api/broadcast',
                         {'action': 'play', 'intervalMs': 200, 'loop': True})
        self.assertTrue(p['broadcast']['playing'])
        self.assertEqual(p['broadcast']['intervalMs'], 200)

        # 等待自动推进若干次。
        time.sleep(1.2)
        state = self.jget('/__api/broadcast')['broadcast']
        self.assertGreaterEqual(state['seq'], 3)
        self.assertTrue(state['playing'])

        # 暂停后不再推进。
        _, pp = self.jpost('/__api/broadcast', {'action': 'pause'})
        self.assertFalse(pp['broadcast']['playing'])
        seq_paused = pp['broadcast']['seq']
        time.sleep(0.6)
        self.assertEqual(self.jget('/__api/broadcast')['broadcast']['seq'], seq_paused)

    def test_play_stops_at_sequence_end_when_not_loop(self):
        _, data = self.jpost('/__api/broadcast',
                             {'action': 'start', 'packs': ['ming-emperors'],
                              'mode': 'sequence', 'loop': False})
        total = data['broadcast']['progress']['total']
        self.jpost('/__api/broadcast',
                   {'action': 'play', 'intervalMs': 200, 'loop': False})
        # 轮询直到停播（避免固定 sleep 在全量测试的负载下偶发不足而误报）。
        deadline = time.time() + total * 0.2 + 6.0
        state = self.jget('/__api/broadcast')['broadcast']
        while state['playing'] and time.time() < deadline:
            time.sleep(0.1)
            state = self.jget('/__api/broadcast')['broadcast']
        self.assertFalse(state['playing'])
        self.assertEqual(state['seq'], total)

    def test_play_rejects_bad_interval(self):
        self.jpost('/__api/broadcast',
                   {'action': 'start', 'packs': ['ming-emperors'], 'mode': 'sequence'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.jpost('/__api/broadcast', {'action': 'play', 'intervalMs': 50})
        self.assertEqual(ctx.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
