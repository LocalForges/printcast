"""P1：本机操作日志（纯函数层）与出场序列复现能力。

日志属于控制台专属能力：展示端不调用、也不上报，服务端统一埋点。
这里覆盖持久化、过滤、裁剪、清空、API 路由，以及固定 seed 的可复现性。
"""
import json
import urllib.parse

import printcast.config as cfg
from printcast import api, audit, storage


def _use_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, 'DATA_DIR', tmp_path)
    return tmp_path


def _dispatch(method, path, body=b''):
    parsed = urllib.parse.urlparse(path)
    resp = api.dispatch(method, parsed.path,
                        urllib.parse.parse_qs(parsed.query), {}, body)
    assert resp is not None
    return resp.status, json.loads(resp.body.decode('utf-8'))


def test_empty_log_stats(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    assert audit.list_entries() == []
    s = audit.stats()
    assert s['total'] == 0 and s['ok'] == 0 and s['failed'] == 0
    assert s['lastAt'] is None and s['actions'] == []
    assert s['limit'] == audit.MAX_ENTRIES


def test_record_and_list_newest_first(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    audit.record('pack.save', 'ming', True, 'HTTP 201', 201)
    audit.record('pack.delete', 'qing', False, 'HTTP 404', 404)
    entries = audit.list_entries()
    assert [e['action'] for e in entries] == ['pack.delete', 'pack.save']
    assert entries[0]['ok'] is False and entries[0]['status'] == 404
    assert entries[0]['id'] and entries[0]['at'].endswith('+00:00')
    s = audit.stats()
    assert (s['total'], s['ok'], s['failed']) == (2, 1, 1)
    assert s['actions'] == ['pack.delete', 'pack.save']


def test_filter_by_action_and_keyword(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    audit.record('pack.save', 'ming', True, '导入明朝包')
    audit.record('settings.update', 'branding', True, '改强调色')
    audit.record('pack.delete', 'qing', True, '删除大清包')
    assert len(audit.list_entries(action='pack.save')) == 1
    assert len(audit.list_entries(q='明朝')) == 1
    assert len(audit.list_entries(q='PACK')) == 2  # 关键词匹配 action
    assert len(audit.list_entries(action='all')) == 3
    assert len(audit.list_entries(limit=2)) == 2
    assert len(audit.list_entries(limit=9999)) == 3  # clamp 到上限内仍返回全部


def test_corrupt_lines_are_skipped(tmp_path, monkeypatch):
    root = _use_tmp(tmp_path, monkeypatch)
    path = root / 'audit.jsonl'
    path.write_text('not json\n' + json.dumps({'action': 'x', 'ok': True}) + '\n',
                    encoding='utf-8')
    assert audit.stats()['total'] == 1
    assert audit.list_entries()[0]['action'] == 'x'


def test_trim_keeps_last_entries(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    total_writes = audit.MAX_ENTRIES + 55
    for i in range(total_writes):
        audit.record('pack.save', 'p%d' % i)
    assert audit.stats()['total'] == audit.MAX_ENTRIES
    assert audit.list_entries(limit=1)[0]['target'] == 'p%d' % (total_writes - 1)


def test_clear_and_fields_clipped(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    entry = audit.record('x' * 100, 'y' * 500, True, 'z' * 500, 200)
    assert len(entry['action']) == 60
    assert len(entry['target']) == 120
    assert len(entry['detail']) == 240
    assert audit.clear() is True
    assert audit.stats()['total'] == 0
    assert audit.clear() is True  # 幂等


def test_audit_api_routes(tmp_path, monkeypatch):
    root = _use_tmp(tmp_path, monkeypatch)
    audit.record('pack.save', 'ming')
    status, data = _dispatch('GET', '/__api/audit?action=pack.save&q=ming')
    assert status == 200 and data['ok'] and len(data['entries']) == 1
    assert data['stats']['total'] == 1
    assert _dispatch('POST', '/__api/audit')[0] == 405
    status, data = _dispatch('DELETE', '/__api/audit')
    assert status == 200 and data['cleared'] is True
    assert not (root / 'audit.jsonl').exists()


def test_schedule_seed_is_echoed_and_reproducible(tmp_path, monkeypatch):
    """固定 seed 的出场序列可复现，且 count 有上限保护。"""
    _use_tmp(tmp_path, monkeypatch)
    pack = {
        'id': 'demo', 'title': '演示包', 'mode': 'weighted',
        'characters': [
            {'id': 'a', 'name': '甲', 'order': 1, 'weight': 3},
            {'id': 'b', 'name': '乙', 'order': 2, 'weight': 2},
            {'id': 'c', 'name': '丙', 'order': 3, 'weight': 1},
        ],
    }
    storage.save_pack(pack)
    url = '/__api/schedule?pack=demo&mode=weighted&seed=20261104&count=12'
    s1, d1 = _dispatch('GET', url)
    s2, d2 = _dispatch('GET', url)
    assert s1 == s2 == 200 and d1['ok']
    assert d1['seed'] == 20261104 and d1['count'] == 12
    assert len(d1['appearances']) == 12
    assert d1['appearances'] == d2['appearances'], '同 seed 必须完全复现'
    _, other = _dispatch('GET', url.replace('seed=20261104', 'seed=7'))
    assert other['appearances'] != d1['appearances'], '不同 seed 应产生不同序列'
    _, capped = _dispatch('GET', url.replace('count=12', 'count=99999'))
    assert capped['count'] == 300 and len(capped['appearances']) == 300
