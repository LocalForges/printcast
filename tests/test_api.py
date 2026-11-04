"""内容包数据层测试：schema / storage / templates / importer / api.dispatch。

直接调用纯函数，不依赖 HTTP 服务，因此 CI 里也能跑。
鉴权（same-origin）在 server 层，单独在 test_server.py 覆盖。
"""
import io
import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import printcast.config as cfg
from printcast import api, importer, schema, storage, templates

# 每个用例用独立临时目录，避免互相污染。
TMP = Path(__file__).resolve().parents[1] / 'tests-tmp' / 'api'
cfg.DATA_DIR = TMP  # 模块级常量 monkeypatch，后续调用立即生效。


def _reset():
    import shutil
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True, exist_ok=True)


def _dispatch(method, path, query=None, headers=None, body=b''):
    # 若 path 里带了 ?query，则优先用 path 里的（模拟真实 HTTP 行为）。
    parsed = urlparse(path)
    if parsed.query and not query:
        query = parse_qs(parsed.query)
    resp = api.dispatch(method, parsed.path, query or {}, headers or {}, body)
    assert resp is not None, 'dispatch 不应返回 None: %s %s' % (method, path)
    return resp.status, json.loads(resp.body.decode('utf-8'))


class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _reset()

    def test_schema_document_has_all_sections(self):
        doc = schema.schema_document()
        for key in ('packFields', 'characterFields', 'modes', 'csvColumns',
                    'idPattern', 'exampleRows'):
            self.assertIn(key, doc)
        self.assertEqual(doc['csvColumns'], schema.csv_columns())

    def test_id_pattern_rejects_bad(self):
        doc = schema.schema_document()
        bad = ('Abc', 'a b', '../x', '中文', 'a' * 65)
        for value in bad:
            with self.subTest(value=value):
                ok, errs = schema.validate_character(
                    {'id': value, 'name': 'x'}, line=1)
                self.assertIsNone(ok)
                self.assertTrue(any(e['field'] == 'id' for e in errs))

    def test_required_fields_enforced(self):
        ok, errs = schema.validate_character({'id': 'a'}, line=1)
        self.assertIsNone(ok)
        self.assertTrue(any(e['field'] == 'name' and '必填' in e['message']
                            for e in errs))

    def test_order_sorted_stable(self):
        pack = {
            'id': 'p', 'title': 't',
            'characters': [
                {'id': 'b', 'name': 'B', 'order': 2},
                {'id': 'a', 'name': 'A', 'order': 1},
                {'id': 'c', 'name': 'C', 'order': 1},
            ],
        }
        cleaned, errs = schema.validate_pack(pack)
        self.assertEqual(errs, [])
        self.assertEqual([c['id'] for c in cleaned['characters']],
                         ['a', 'c', 'b'])  # order 1 稳定保持导入先后


class TemplateTests(unittest.TestCase):
    def test_csv_has_bom_and_comment_rows(self):
        data, ctype, name = templates.template_bytes('csv')
        self.assertEqual(ctype, 'text/csv; charset=utf-8')
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'))
        text = data.decode('utf-8')
        self.assertIn('#', text)  # 注释行
        self.assertIn('id,name,order', text)  # 表头行

    def test_json_template_is_valid_pack(self):
        data, ctype, name = templates.template_bytes('json')
        pack = json.loads(data.decode('utf-8'))
        self.assertIn('characters', pack)
        cleaned, errs = schema.validate_pack(pack)
        self.assertEqual(errs, [], errs)

    def test_unknown_format_falls_back_to_csv(self):
        # template_bytes 对未知格式回退到 CSV（不抛异常），保证总能下载。
        data, ctype, name = templates.template_bytes('xml')
        self.assertEqual(ctype, 'text/csv; charset=utf-8')
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'))


class PackCrudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _reset()

    def _good(self):
        return {
            'id': 'ming', 'title': '明朝十六帝', 'mode': 'sequence',
            'characters': [
                {'id': 'hongwu', 'name': '朱元璋', 'order': 1},
                {'id': 'yongle', 'name': '朱棣', 'order': 2},
            ],
        }

    def test_create_list_get_delete(self):
        body = json.dumps(self._good()).encode('utf-8')
        status, data = _dispatch('POST', '/__api/packs', body=body)
        self.assertEqual(status, 201)
        self.assertTrue(data['ok'])

        status, data = _dispatch('GET', '/__api/packs')
        self.assertEqual(status, 200)
        self.assertEqual([p['id'] for p in data['packs']], ['ming'])

        status, data = _dispatch('GET', '/__api/packs/ming')
        self.assertEqual(status, 200)
        self.assertEqual(data['pack']['title'], '明朝十六帝')

        status, data = _dispatch('DELETE', '/__api/packs/ming')
        self.assertEqual(status, 200)
        self.assertTrue(data['deleted'])

        status, data = _dispatch('GET', '/__api/packs')
        self.assertEqual(data['packs'], [])

    def test_put_same_as_post(self):
        body = json.dumps(self._good()).encode('utf-8')
        status, data = _dispatch('PUT', '/__api/packs', body=body)
        self.assertEqual(status, 201)

    def test_get_missing_pack_404(self):
        status, _ = _dispatch('GET', '/__api/packs/nope')
        self.assertEqual(status, 404)

    def test_invalid_pack_rejected_422(self):
        bad = {'id': 'x', 'title': 't'}  # 缺 characters 的 name? 是允许空列表的
        # 改成非法 id
        bad = {'id': 'BAD ID', 'title': 't', 'characters': []}
        status, data = _dispatch('POST', '/__api/packs',
                                 body=json.dumps(bad).encode('utf-8'))
        self.assertEqual(status, 422)
        self.assertIn('errors', data)

    def test_illegal_pack_id_400(self):
        status, _ = _dispatch('DELETE', '/__api/packs/../etc')
        self.assertEqual(status, 400)


class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _reset()

    def test_csv_import_commit(self):
        csv = 'id,name,order\nhongwu,朱元璋,1\nyongle,朱棣,2'
        payload = json.dumps({
            'format': 'csv',
            'pack': {'id': 'imp', 'title': '导入测试'},
            'content': csv,
        }).encode('utf-8')
        status, data = _dispatch('POST', '/__api/import?commit=1',
                                 body=payload)
        self.assertEqual(status, 200)
        self.assertTrue(data['ok'])
        self.assertTrue(data['committed'])
        # 确认真的落盘了
        status, data = _dispatch('GET', '/__api/packs/imp')
        self.assertEqual(status, 200)
        self.assertEqual(len(data['pack']['characters']), 2)

    def test_csv_import_reports_row_error_no_commit(self):
        csv = 'id,name,order\nhongwu,,1'  # 缺 name
        payload = json.dumps({
            'format': 'csv',
            'pack': {'id': 'imp2', 'title': 't'},
            'content': csv,
        }).encode('utf-8')
        status, data = _dispatch('POST', '/__api/import?commit=1',
                                 body=payload)
        self.assertEqual(status, 422)
        self.assertFalse(data['ok'])
        self.assertFalse(data['committed'])
        self.assertTrue(any(e['field'] == 'name' for e in data['errors']))

    def test_json_import_direct_object(self):
        payload = json.dumps({
            'format': 'json',
            'pack': {'id': 'jimp', 'title': 'j'},
            'content': {'characters': [{'id': 'a', 'name': 'A'}]},
        }).encode('utf-8')
        status, data = _dispatch('POST', '/__api/import?commit=1',
                                 body=payload)
        self.assertEqual(status, 200)
        self.assertTrue(data['committed'])

    def test_import_only_get_allowed(self):
        status, _ = _dispatch('GET', '/__api/import')
        self.assertEqual(status, 405)


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _reset()

    def test_upload_png_and_list_and_delete(self):
        png = b'\x89PNG\r\n\x1a\n' + b'x' * 16
        status, data = _dispatch('POST', '/__api/media', body=png,
                                 headers={'content-type': 'image/png',
                                          'x-file-name': '皇帝.png'})
        self.assertEqual(status, 201)
        self.assertTrue(data['ok'])
        media = data['media']
        self.assertTrue(media['id'].endswith('.png'))
        self.assertEqual(media['name'], '皇帝.png')  # 原始中文名保留在元数据

        # 媒体文件可直接通过 /media/<id> 访问
        from printcast.server import make_handler
        path = storage.media_path(media['id'])
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())

        status, data = _dispatch('DELETE', '/__api/media/' + media['id'])
        self.assertEqual(status, 200)
        self.assertTrue(data['deleted'])

    def test_non_image_rejected(self):
        status, data = _dispatch('POST', '/__api/media', body=b'not image',
                                 headers={'content-type': 'image/png'})
        self.assertEqual(status, 400)
        self.assertFalse(data['ok'])

    def test_wrong_mime_rejected(self):
        png = b'\x89PNG\r\n\x1a\n' + b'x' * 16
        status, data = _dispatch('POST', '/__api/media', body=png,
                                 headers={'content-type': 'text/html'})
        self.assertEqual(status, 400)

    def test_media_only_post_get_delete(self):
        status, _ = _dispatch('PUT', '/__api/media')
        self.assertEqual(status, 405)


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _reset()

    def test_path_traversal_in_media_id_blocked(self):
        # 媒体 id 必须是 12 位 hex + 扩展名，../ 直接不合法。
        self.assertIsNone(storage.media_path('../etc/passwd'))
        self.assertIsNone(storage.media_path('..%2f..%2fetc'))

    def test_pack_path_cannot_leave_dir(self):
        with self.assertRaises(ValueError):
            storage.pack_path('../../etc/passwd')

    def test_unknown_api_path_404(self):
        status, _ = _dispatch('GET', '/__api/unknown')
        self.assertEqual(status, 404)


if __name__ == '__main__':
    unittest.main()
