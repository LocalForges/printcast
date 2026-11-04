"""本地 HTTP 服务的单元测试：静态资源、本机端点鉴权、信令转发。

用真实的 ThreadingHTTPServer 起在临时端口，跑完即关，不依赖外网也不碰 GPU。
"""
import json
import socket
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from printcast.server import LocalHTTPServer, ensure_server, make_handler

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 先向内核讨一个空闲端口，再用它构造 Handler —— make_handler 的 Host
        # 校验需要知道真实端口，所以不能先建 server 再补。
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

    def get(self, path, same_origin=True, host=None, sec_fetch_site=None):
        req = urllib.request.Request(self.url(path))
        if same_origin:
            req.add_header('Sec-Fetch-Site', 'same-origin')
            req.add_header('Host', f'127.0.0.1:{self.port}')
        else:
            # 真实跨站请求一定带 cross-site；过去用「不带该头」模拟跨站是错的，
            # Safari 等本来就不发这个头，不能据此判为外部站点。
            req.add_header('Sec-Fetch-Site', 'cross-site')
        if host is not None:
            req.add_header('Host', host)
        if sec_fetch_site is not None:
            req.add_header('Sec-Fetch-Site', sec_fetch_site)
        return _OPENER.open(req, timeout=3)

    # —— 静态文件 ——
    def test_static_pages(self):
        for path in ('/web/index.html', '/web/index-en.html', '/site/features.html',
                     '/src/collector/parse.mjs', '/assets/three.module.js'):
            with self.get(path) as response:
                self.assertEqual(response.status, 200, path)
                body = response.read()  # 消费完，避免服务端写半截触发 BrokenPipe
                self.assertGreater(len(body), 0, path)

    def test_no_store_header(self):
        with self.get('/web/index.html') as response:
            header = response.headers.get('Cache-Control', '')
            response.read()
        self.assertIn('no-store', header)

    def test_document_root_is_repo_root(self):
        # /site/guide.html 与 /web 同在仓库根下（分层改写后最易断的引用）。
        with self.get('/site/guide.html') as response:
            body = response.read()
        self.assertIn('使用教程'.encode('utf-8'), body)
        # 旧版第三方（志哥AI）广告条 / 微信号 / wx-copy 脚本已彻底移除。
        self.assertNotIn('志哥AI'.encode('utf-8'), body)
        self.assertNotIn(b'wx-copy.js', body)
        self.assertIn(b'../web/index.html', body)

    # —— 鉴权 ——
    def test_control_endpoint_denies_cross_site(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get('/__bridge-status', same_origin=False)
        self.assertEqual(ctx.exception.code, 403)

    def test_localhost_and_missing_fetch_site_are_allowed(self):
        # 用 localhost 打开工作台曾导致所有 /__api/* 403：内容包读不到、连接受阻。
        with self.get('/__api/packs', host=f'localhost:{self.port}') as response:
            self.assertEqual(response.status, 200)
            response.read()
        # Safari 等不发送 Sec-Fetch-Site；Host 白名单已足以挡外部站点。
        req = urllib.request.Request(self.url('/__api/packs'))
        req.add_header('Host', f'127.0.0.1:{self.port}')
        with _OPENER.open(req, timeout=3) as response:
            self.assertEqual(response.status, 200)
            response.read()

    def test_external_host_is_still_denied(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get('/__api/packs', host='evil.example.com:8080')
        self.assertEqual(ctx.exception.code, 403)

    def test_scene_events_emits_exactly_one_response(self):
        # _json 曾返回 None，导致 do_GET 路由循环继续走静态回退：
        # 先发 200 JSON、再叠一个 404，浏览器连接被污染并刷 OSError 41。
        conn = socket.create_connection(('127.0.0.1', self.port), timeout=3)
        req = ('GET /__scene-events?client=probe HTTP/1.0\r\n'
               f'Host: 127.0.0.1:{self.port}\r\n'
               'Sec-Fetch-Site: same-origin\r\n\r\n')
        conn.sendall(req.encode('ascii'))
        conn.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        conn.close()
        raw = b''.join(chunks)
        self.assertEqual(raw.count(b'HTTP/1.0 200'), 1, raw[:200])
        self.assertNotIn(b'HTTP/1.0 404', raw)
        self.assertNotIn(b'File not found', raw)
        data = json.loads(raw.split(b'\r\n\r\n', 1)[1])
        self.assertIn('cursor', data)

    def test_studio_shows_build_guide_when_dist_missing(self):
        from unittest import mock
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            with mock.patch('printcast.server.config.studio_dist_dir',
                            return_value=Path(td)):
                with self.get('/studio/') as response:
                    body = response.read()
                    self.assertEqual(response.status, 200)
        self.assertIn('工作台尚未构建'.encode('utf-8'), body)
        self.assertIn(b'build-studio.sh', body)

    def test_bridge_status_shape(self):
        with self.get('/__bridge-status') as response:
            data = json.load(response)
        self.assertIn('ok', data)

    def test_console_status_aggregates_runtime_state(self):
        with self.get('/__api/status') as response:
            data = json.load(response)
        self.assertTrue(data['ok'])
        self.assertEqual(data['service']['port'], self.port)
        self.assertIsInstance(data['service']['uptimeSeconds'], int)
        self.assertIn('ok', data['bridge'])
        self.assertIn('active', data['broadcast'])
        self.assertEqual(set(data['counts']), {'packs', 'media'})
        # 打印队列长度属于展示端内存，后端不得臆造。
        self.assertNotIn('queueLength', data)

    def test_console_status_requires_local_auth(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get('/__api/status', same_origin=False)
        self.assertEqual(ctx.exception.code, 403)

    def test_health_probe_is_open_and_identifies_service(self):
        # 存活探针无需 same-origin（只读、无副作用），供端口复用检测使用。
        with self.get('/__health', same_origin=False) as response:
            data = json.load(response)
        self.assertEqual(data['service'], 'printcast')
        self.assertTrue(Path(data['root']).is_dir())

    def test_scene_events_empty_cursor(self):
        with self.get('/__scene-events?client=tester') as response:
            data = json.load(response)
        self.assertEqual(data['cursor'], 0)
        self.assertEqual(data['messages'], [])

    def test_scene_message_publish_then_poll(self):
        payload = json.dumps({'client': 'main', 'message': {'type': 'view-ping', 'ts': 1}}).encode()
        req = urllib.request.Request(
            self.url('/__scene-message'), data=payload,
            headers={'Content-Type': 'application/json',
                     'Sec-Fetch-Site': 'same-origin',
                     'Host': f'127.0.0.1:{self.port}'})
        with _OPENER.open(req, timeout=3) as response:
            self.assertEqual(json.load(response), {'ok': True})
        with self.get('/__scene-events?client=viewer&after=0') as response:
            data = json.load(response)
        self.assertEqual([m['type'] for m in data['messages']], ['view-ping'])

    def test_bad_scene_message_rejected(self):
        payload = b'{"client":"x","message":{"type":"not-allowed"}}'
        req = urllib.request.Request(
            self.url('/__scene-message'), data=payload,
            headers={'Content-Type': 'application/json',
                     'Sec-Fetch-Site': 'same-origin',
                     'Host': f'127.0.0.1:{self.port}'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            _OPENER.open(req, timeout=3)
        self.assertEqual(ctx.exception.code, 400)

    def test_bad_scene_path_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get('/__open-scene?path=/../../etc/passwd&orient=landscape')
        self.assertEqual(ctx.exception.code, 400)

    # —— 内容包 API 经 GET 路由到 api 层（回归 do_GET 漏路由的 bug）——
    def test_api_schema_routed_via_get(self):
        with self.get('/__api/schema') as response:
            data = json.load(response)
        self.assertTrue(data['ok'])
        self.assertIn('packFields', data['schema'])

    def test_api_template_csv_downloadable(self):
        req = urllib.request.Request(self.url('/__api/template.csv'))
        req.add_header('Sec-Fetch-Site', 'same-origin')
        req.add_header('Host', f'127.0.0.1:{self.port}')
        with _OPENER.open(req, timeout=3) as response:
            body = response.read()
        self.assertTrue(body.startswith(b'\xef\xbb\xbf'))  # BOM

    def test_api_get_without_auth_is_403(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get('/__api/packs', same_origin=False)
        self.assertEqual(ctx.exception.code, 403)

    def test_api_media_and_packs_end_to_end(self):
        # 上传一张图片（魔数 PNG），确认返回 id 且可被媒体接口列出。
        png = b'\x89PNG\r\n\x1a\n' + b'x' * 16
        req = urllib.request.Request(
            self.url('/__api/media'), data=png,
            headers={'Content-Type': 'image/png', 'Sec-Fetch-Site': 'same-origin',
                     'Host': f'127.0.0.1:{self.port}'})
        with _OPENER.open(req, timeout=3) as response:
            self.assertEqual(response.status, 201)
            media = json.load(response)['media']
        self.assertTrue(media['id'].endswith('.png'))
        # 同一张非法文件应被拒（非图片）。
        bad = urllib.request.Request(
            self.url('/__api/media'), data=b'plain',
            headers={'Content-Type': 'image/png', 'Sec-Fetch-Site': 'same-origin',
                     'Host': f'127.0.0.1:{self.port}'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            _OPENER.open(bad, timeout=3)
        self.assertEqual(ctx.exception.code, 400)
        # 测试不该污染工作区：data/media 是运行时用户数据，用完即删。
        cleanup = urllib.request.Request(
            self.url('/__api/media/' + media['id']), method='DELETE',
            headers={'Sec-Fetch-Site': 'same-origin',
                     'Host': f'127.0.0.1:{self.port}'})
        with _OPENER.open(cleanup, timeout=3) as response:
            response.read()

    # —— P1：本机操作日志（端到端）——
    def test_audit_records_writes_and_clear_keeps_audit_trail(self):
        import tempfile
        from unittest import mock
        from printcast import config

        def request(method, path, payload=None):
            data = json.dumps(payload).encode('utf-8') if payload is not None else None
            req = urllib.request.Request(
                self.url(path), data=data, method=method,
                headers={'Content-Type': 'application/json',
                         'Sec-Fetch-Site': 'same-origin',
                         'Host': f'127.0.0.1:{self.port}'})
            return _OPENER.open(req, timeout=3)

        # 日志写到临时目录，避免污染仓库本机数据；服务端与 api 层共享 config 模块。
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(config, 'DATA_DIR', Path(tmp)):
                with request('DELETE', '/__api/packs/ghost-pack') as response:
                    response.read()
                with self.get('/__api/audit?action=pack.delete') as response:
                    data = json.load(response)
                self.assertTrue(data['ok'])
                self.assertEqual(len(data['entries']), 1)
                self.assertEqual(data['entries'][0]['action'], 'pack.delete')
                self.assertEqual(data['entries'][0]['target'], 'ghost-pack')
                self.assertTrue(data['entries'][0]['ok'])
                self.assertEqual(data['stats']['total'], 1)

                # 失败动作也要留痕（未知广播动作 → 400）。
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    request('POST', '/__api/broadcast',
                            {'action': 'definitely-unknown'}).read()
                self.assertEqual(ctx.exception.code, 400)
                with self.get('/__api/audit?action=broadcast.definitely-unknown') as response:
                    failed = json.load(response)
                self.assertEqual(len(failed['entries']), 1)
                self.assertFalse(failed['entries'][0]['ok'])
                self.assertEqual(failed['stats']['failed'], 1)

                # 清空后仍留一条「谁清过日志」，可回溯性不因清空而断。
                with request('DELETE', '/__api/audit') as response:
                    cleared = json.load(response)
                self.assertTrue(cleared['cleared'])
                with self.get('/__api/audit') as response:
                    after = json.load(response)
                self.assertEqual(after['stats']['total'], 1)
                self.assertEqual(after['entries'][0]['action'], 'audit.clear')

    def test_audit_get_is_read_only_and_requires_auth(self):
        with self.get('/__api/audit') as response:
            data = json.load(response)
        self.assertTrue(data['ok'])
        self.assertIn('entries', data)
        self.assertIn('stats', data)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get('/__api/audit', same_origin=False)
        self.assertEqual(ctx.exception.code, 403)


class EnsureServerTests(unittest.TestCase):
    def test_reuses_existing_printcast_instance(self):
        # 端口已被本程序占用时不应再起一个服务，返回 server=None 让调用方别去 shutdown。
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        server = LocalHTTPServer(('127.0.0.1', port), make_handler(port))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url, reused = ensure_server(port)
            self.assertIn(f':{port}/', url)
            self.assertIsNone(reused)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_explicit_port_is_honoured(self):
        # 回归：CLI 的 --port 曾被 `from config import HTTP_PORT` 的值绑定吞掉。
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        url, server = ensure_server(port)
        try:
            self.assertIn(f':{port}/', url)
            with _OPENER.open(url + 'web/index.html', timeout=3) as response:
                self.assertEqual(response.status, 200)
                response.read()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
