"""数据落库（SQLite）与「已知问题」修复的回归护栏。

覆盖：首次 JSON→DB 迁移、库为唯一数据源与 JSON 镜像、写事务串行化、
设置默认值不被污染、危险链接协议、路由精确匹配、seed 归一化、中文文件名、
日志筛选与原子清空、广播状态跨重启恢复、调度器 reset 重新播种、导出导入自检。
"""
import json
import sqlite3
import threading
import urllib.parse

import printcast.config as cfg
from printcast import api, audit, db, settings as settings_module, storage
from printcast.broadcast import BroadcastController
from printcast.relay import SceneRelay
from printcast.scheduler import ContentScheduler, normalize_seed

_PNG = b'\x89PNG\r\n\x1a\n' + b'x' * 16


def _use_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, 'DATA_DIR', tmp_path)
    return tmp_path


def _dispatch(method, path, body=b'', headers=None):
    parsed = urllib.parse.urlparse(path)
    resp = api.dispatch(method, parsed.path,
                        urllib.parse.parse_qs(parsed.query), headers or {}, body)
    assert resp is not None
    return resp.status, json.loads(resp.body.decode('utf-8'))


def _pack(pid='demo', count=3):
    return {
        'id': pid, 'title': '演示包', 'mode': 'sequence',
        'characters': [
            {'id': 'c%d' % i, 'name': '角色%d' % i, 'order': i + 1,
             'speech': '第%d位' % (i + 1), 'tags': '测试;演示', 'weight': 1}
            for i in range(count)
        ],
    }


# ——— 迁移与「库是唯一数据源」———

def test_first_start_migrates_all_legacy_json(tmp_path, monkeypatch):
    root = _use_tmp(tmp_path, monkeypatch)
    (root / 'packs').mkdir()
    (root / 'media').mkdir()
    (root / 'packs' / 'demo.json').write_text(json.dumps(_pack()), encoding='utf-8')
    (root / 'packs' / 'broken.json').write_text('[1,2,3]', encoding='utf-8')
    (root / 'settings.json').write_text(
        json.dumps({'branding': {'title': '旧配置'}}), encoding='utf-8')
    (root / 'media' / 'index.json').write_text(json.dumps({
        'a720442e27c1.png': {'id': 'a720442e27c1.png', 'name': '旧头像.png',
                             'size': 24, 'mime': 'image/png',
                             'created': '2026-11-04T00:00:00+00:00',
                             'url': '/media/a720442e27c1.png'},
    }), encoding='utf-8')
    (root / 'audit.jsonl').write_text(
        'not json\n' + json.dumps({
            'id': 'legacy1', 'at': '2026-11-04T00:00:00+00:00',
            'action': 'pack.save', 'target': 'demo', 'ok': True,
            'status': 201, 'detail': '旧日志',
        }) + '\n', encoding='utf-8')

    info = db.stats()
    assert info['backend'] == 'sqlite' and info['integrity'] == 'ok'
    assert info['migratedFrom'] == {
        'packs': 1, 'characters': 3, 'settings': 1, 'media': 1, 'audit': 1}
    assert [p['id'] for p in storage.list_packs()] == ['demo']
    assert settings_module.load_settings()['branding']['title'] == '旧配置'
    assert storage.list_media()[0]['name'] == '旧头像.png'
    assert audit.stats()['total'] == 1
    # 幂等：再次调用不再重复插入。
    db.migrate_from_json()
    assert db.stats()['tables']['packs'] == 1


def test_db_is_source_of_truth_and_json_is_mirror(tmp_path, monkeypatch):
    root = _use_tmp(tmp_path, monkeypatch)
    saved = storage.save_pack(_pack())
    assert 'updated' in saved
    assert (root / 'packs' / 'demo.json').is_file()
    (root / 'packs' / 'demo.json').unlink()
    assert storage.get_pack('demo')['title'] == '演示包'  # 库仍在
    assert db.stats()['tables']['characters'] == 3


def test_export_import_roundtrip_and_verify(tmp_path, monkeypatch):
    root = _use_tmp(tmp_path, monkeypatch)
    storage.save_pack(_pack('round'))
    settings_module.save_settings({'branding': {'title': '往返设置'}})
    assert db.verify()['ok'] is True
    exported = db.export_json()
    assert exported['packs'] == ['round'] and exported['settings'] is True
    # 模拟「库丢了但 JSON 备份还在」：直接清空库里的包，保留盘上的 JSON。
    with db.connect() as conn:
        conn.execute('DELETE FROM characters')
        conn.execute('DELETE FROM packs')
        conn.commit()
    assert storage.get_pack('round') is None
    result = db.import_json()
    assert result['packs'] == 1 and result['settings'] == 0
    assert [c['name'] for c in storage.get_pack('round')['characters']] == [
        '角色0', '角色1', '角色2']
    assert db.verify()['ok'] is True


def test_verify_detects_corrupted_projection(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    storage.save_pack(_pack('integrity'))
    with db.connect() as conn:
        conn.execute("DELETE FROM characters WHERE pack_id = 'integrity'")
        conn.commit()
    result = db.verify()
    assert result['ok'] is False
    assert any('投影缺失' in e for e in result['errors'])


# ——— 并发与事务 ———

def test_settings_update_is_serialized(tmp_path, monkeypatch):
    """BEGIN IMMEDIATE：第二个写事务必须看到第一个已提交的文档。"""
    _use_tmp(tmp_path, monkeypatch)
    entered, release, seen = threading.Event(), threading.Event(), []

    def first(current):
        entered.set()
        release.wait(3)
        return {'branding': {'title': 'A'}}

    def second(current):
        seen.append(current)
        return {'display': {'announceText': 'B'}}

    t1 = threading.Thread(target=lambda: db.update_settings(first))
    t1.start()
    assert entered.wait(3)
    t2 = threading.Thread(target=lambda: db.update_settings(second))
    t2.start()
    release.set()
    t1.join(3)
    t2.join(3)
    assert seen and seen[0] and seen[0]['branding']['title'] == 'A'


def test_concurrent_media_uploads_do_not_lose_records(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    errors = []

    def upload(i):
        try:
            storage.save_media(_PNG + bytes([i]), '头像%d.png' % i, 'image/png')
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [threading.Thread(target=upload, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert not errors
    assert len(storage.list_media()) == 12


# ——— 已知缺陷修复 ———

def test_default_settings_are_never_polluted(tmp_path, monkeypatch):
    """D5：浅拷贝 + 原地净化曾把用户值写回 DEFAULT_SETTINGS。"""
    _use_tmp(tmp_path, monkeypatch)
    baseline = json.dumps(settings_module.DEFAULT_SETTINGS, ensure_ascii=False)
    settings_module.save_settings({
        'branding': {'title': '我的台', 'links': [
            {'label': '外链', 'href': 'https://example.com/x'}]},
        'printer': {'rules': {'comment': False}},
    })
    assert json.dumps(settings_module.DEFAULT_SETTINGS,
                      ensure_ascii=False) == baseline
    reset = settings_module.reset_settings()
    assert reset['branding']['title'] == '头像打印机'
    assert reset['printer']['rules']['comment'] is True
    assert [l['href'] for l in reset['branding']['links']] == [
        '/site/features.html', '/site/guide.html']


def test_link_scheme_bypass_is_rejected(tmp_path, monkeypatch):
    """D7：startswith('http') 曾让 httpjavascript: 绕过协议白名单。"""
    _use_tmp(tmp_path, monkeypatch)
    saved = settings_module.save_settings({'branding': {'links': [
        {'label': 'a', 'href': 'httpjavascript:alert(1)'},
        {'label': 'b', 'href': 'HTTP://example.com/x'},
        {'label': 'c', 'href': '//evil.example.com'},
        {'label': 'd', 'href': 'data:text/html,1'},
        {'label': 'e', 'href': '/site/guide.html'},
    ]}})
    hrefs = [l['href'] for l in saved['branding']['links']]
    assert hrefs == ['HTTP://example.com/x', '/site/guide.html']


def test_damaged_settings_document_is_repaired(tmp_path, monkeypatch):
    """D8：库里文档损坏时重新写回默认，而不是每次读取都假装正常。"""
    _use_tmp(tmp_path, monkeypatch)
    db.put_settings_doc({'branding': {'title': '正常'}})
    with db.connect() as conn:
        conn.execute("UPDATE settings SET doc = 'not json' WHERE id = 1")
        conn.commit()
    loaded = settings_module.load_settings()
    assert loaded['branding']['title'] == '头像打印机'
    assert settings_module.load_settings()['branding']['title'] == '头像打印机'


def test_extra_path_segments_cannot_reset_settings(tmp_path, monkeypatch):
    """D17：DELETE /__api/settings/anything 曾命中前缀并清空全部配置。"""
    _use_tmp(tmp_path, monkeypatch)
    settings_module.save_settings({'branding': {'title': '保留我'}})
    status, _ = _dispatch('DELETE', '/__api/settings/anything')
    assert status == 404
    assert settings_module.load_settings()['branding']['title'] == '保留我'
    assert _dispatch('GET', '/__api/settings-extra')[0] == 404
    assert _dispatch('GET', '/__api/packs/a/b')[0] == 404


def test_seed_normalization_is_single_source(tmp_path, monkeypatch):
    """D18/R1：URL 与 JSON body 两条入口同一个 seed 必须产生同一序列。"""
    assert normalize_seed('20261104') == 20261104
    assert normalize_seed(20261104) == 20261104
    assert normalize_seed('9007199254740993') == 9007199254740993  # 不丢精度
    assert normalize_seed('') is None and normalize_seed(True) is None
    assert normalize_seed('剧本A') == '剧本A'
    pack = dict(_pack('seed'), mode='weighted')
    a = ContentScheduler([pack], seed='20261104').plan(12)
    b = ContentScheduler([pack], seed=20261104).plan(12)
    assert a == b and len(a) == 12


def test_chinese_upload_filename_is_decoded(tmp_path, monkeypatch):
    """D19：前端 encodeURIComponent 的中文名后端要解码。"""
    _use_tmp(tmp_path, monkeypatch)
    status, data = _dispatch(
        'POST', '/__api/media', body=_PNG,
        headers={'content-type': 'image/png',
                 'x-file-name': urllib.parse.quote('皇帝.png')})
    assert status == 201
    assert data['media']['name'] == '皇帝.png'


def test_audit_only_failed_filter_ignores_window(tmp_path, monkeypatch):
    """D12：失败筛选在 SQL 里做，不能被「最近 100 条」窗口截断。"""
    _use_tmp(tmp_path, monkeypatch)
    audit.record('pack.save', 'old-failure', False, '失败', 500)
    for i in range(120):
        audit.record('pack.save', 'p%d' % i, True, '成功', 200)
    found = audit.list_entries(limit=100, only_failed=True)
    assert len(found) == 1 and found[0]['target'] == 'old-failure'
    assert audit.stats()['lastAt'] is not None  # D9：取最新而非最旧


def test_audit_clear_with_record_is_atomic(tmp_path, monkeypatch):
    """D11：清空与留痕一次事务完成，server 不会重复补记。"""
    _use_tmp(tmp_path, monkeypatch)
    audit.record('pack.save', 'demo')
    status, data = _dispatch('DELETE', '/__api/audit')
    assert status == 200 and data['cleared'] is True
    entries = audit.list_entries()
    assert len(entries) == 1 and entries[0]['action'] == 'audit.clear'


def test_scheduler_reset_reseeds_rng(tmp_path, monkeypatch):
    """D15：重置进度后 weighted 序列必须从 seed 开头复现。"""
    pack = dict(_pack('weighted', 5), mode='weighted')
    s = ContentScheduler([pack], seed='77')
    first = [a['name'] for a in s.plan(8)]
    s.next()
    s.next()
    s.reset()
    assert [a['name'] for a in s.plan(8)] == first


def test_scheduler_snapshot_restores_weighted_progress():
    pack = dict(_pack('snap', 5), mode='weighted')
    s1 = ContentScheduler([pack], seed='2026')
    for _ in range(4):
        s1.next()
    expected = [a['name'] for a in s1.plan(6)]
    s2 = ContentScheduler([pack], seed='2026')
    s2.restore_state(s1.snapshot_state())
    assert [a['name'] for a in s2.plan(6)] == expected
    assert s2.progress()['appeared'] == 4


# ——— 广播状态跨重启恢复 ———

def test_broadcast_state_survives_restart(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    storage.save_pack(_pack('restart', 6))
    first = BroadcastController(SceneRelay(), restore=False)
    first.start(['restart'], seed='20261104')
    first.next()
    first.next()
    state = first.state()
    assert state['seed'] == 20261104 and state['seq'] == 2

    restored = BroadcastController(SceneRelay(), restore=True)
    after = restored.state()
    assert after['active'] is True
    assert after['seq'] == 2 and after['seed'] == 20261104
    assert after['current']['id'] == state['current']['id']
    assert after['startedAt'] == state['startedAt']

    # 继续推进的结果应与「从未重启」的对照实例完全一致。
    reference = BroadcastController(SceneRelay(), restore=False)
    reference.start(['restart'], seed='20261104')
    for _ in range(3):
        reference.next()
    third = reference.state()['current']
    continued = restored.next()['current']
    assert continued['id'] == third['id'] and continued['index'] == third['index']


def test_restore_is_abandoned_when_pack_was_deleted(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    storage.save_pack(_pack('gone'))
    first = BroadcastController(SceneRelay(), restore=False)
    first.start(['gone'], seed='9')
    first.next()
    storage.delete_pack('gone')
    assert BroadcastController(SceneRelay(), restore=True).state()['active'] is False


def test_schedule_cli_preview_no_longer_crashes(tmp_path, monkeypatch, capsys):
    """--schedule 曾读 ap['index']，而 plan() 的预览字典根本没有该字段。"""
    from printcast import cli, samples
    _use_tmp(tmp_path, monkeypatch)
    db.ensure_db()
    samples.seed_builtin_packs()
    args = cli.parse_args(['--schedule', 'ming-emperors', '--count', '3'])
    cli._run_schedule(args)
    out = capsys.readouterr().out
    assert '朱元璋' in out and '朱允炆' in out and '朱棣' in out
    assert '朱由检' not in out
