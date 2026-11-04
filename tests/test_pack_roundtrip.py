"""P1：内容包抽屉的「查看 → 编辑 → 保存 / 复制 / 导出再导入」数据契约。

前端 normalizePackForSave() 会把 schema 规范化出来的 tags 数组还原成分号串，
因为 POST /__api/packs 与 /__api/import 的校验层只对字符串做切分；若直接把
数组回传，会被 str(list) 变成脏标签 —— 这正是 M0 修过的根因，必须有回归护栏。
"""
import json
from urllib.parse import parse_qs, urlparse

import printcast.config as cfg
from printcast import api, schema, storage


def _dispatch(method, path, body=b''):
    parsed = urlparse(path)
    resp = api.dispatch(method, parsed.path, parse_qs(parsed.query), {}, body)
    assert resp is not None
    return resp.status, json.loads(resp.body.decode('utf-8'))


def _wire(pack):
    """模拟 studio/src/App.vue 的 normalizePackForSave()。"""
    out = json.loads(json.dumps(pack))
    out.pop('updated', None)
    for c in out.get('characters', []):
        if isinstance(c.get('tags'), list):
            c['tags'] = ';'.join(c['tags'])
    return out


def _source():
    cleaned, errors = schema.validate_pack({
        'id': 'roundtrip', 'title': '往返包', 'mode': 'sequence',
        'description': '抽屉编辑回归',
        'characters': [
            {'id': 'a', 'name': '甲', 'order': 1, 'weight': 2,
             'tags': '开国;帝王', 'speech': '甲登场'},
            {'id': 'b', 'name': '乙', 'order': 2, 'weight': 1, 'tags': '迁都'},
        ],
    })
    assert errors == []
    return cleaned


def test_edit_save_keeps_tags_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, 'DATA_DIR', tmp_path)
    storage.save_pack(_source())
    wire = _wire(storage.get_pack('roundtrip'))
    wire['characters'][0]['name'] = '甲（已改名）'
    status, data = _dispatch('POST', '/__api/packs',
                             json.dumps(wire, ensure_ascii=False).encode('utf-8'))
    assert status == 201 and data['ok']
    chars = data['pack']['characters']
    assert chars[0]['name'] == '甲（已改名）'
    assert chars[0]['tags'] == ['开国', '帝王']
    assert chars[1]['tags'] == ['迁都']
    assert storage.get_pack('roundtrip')['characters'][0]['name'] == '甲（已改名）'


def test_duplicate_creates_new_pack_and_keeps_original(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, 'DATA_DIR', tmp_path)
    storage.save_pack(_source())
    copy = _wire(storage.get_pack('roundtrip'))
    copy['id'] = 'roundtrip-copy'
    copy['title'] = '往返包 副本'
    status, data = _dispatch('POST', '/__api/packs',
                             json.dumps(copy, ensure_ascii=False).encode('utf-8'))
    assert status == 201
    assert set(p['id'] for p in storage.list_packs()) == {'roundtrip', 'roundtrip-copy'}
    assert storage.get_pack('roundtrip')['title'] == '往返包'
    assert storage.get_pack('roundtrip-copy')['characters'][0]['tags'] == ['开国', '帝王']


def test_exported_json_can_be_reimported_via_import_api(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, 'DATA_DIR', tmp_path)
    storage.save_pack(_source())
    exported = _wire(storage.get_pack('roundtrip'))
    exported['id'] = 'reimported'
    payload = {'format': 'json', 'pack': {}, 'content': exported}
    status, report = _dispatch('POST', '/__api/import?commit=1',
                               json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    assert status == 200 and report['ok'] and report['committed']
    saved = storage.get_pack('reimported')
    assert saved and saved['characters'][0]['tags'] == ['开国', '帝王']
    assert saved['characters'][0]['speech'] == '甲登场'


def test_invalid_edit_is_rejected_without_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, 'DATA_DIR', tmp_path)
    storage.save_pack(_source())
    wire = _wire(storage.get_pack('roundtrip'))
    wire['characters'][0]['id'] = 'BAD ID/../x'   # 抽屉里手改坏 ID
    status, data = _dispatch('POST', '/__api/packs',
                             json.dumps(wire, ensure_ascii=False).encode('utf-8'))
    assert status == 422 and data['error'] == '内容包校验失败'
    assert data['errors'] and data['errors'][0]['field'] == 'id'
    assert storage.get_pack('roundtrip')['characters'][0]['id'] == 'a'
