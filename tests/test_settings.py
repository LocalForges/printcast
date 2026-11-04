"""控制台设置：持久化、合并、校验，以及经 api.dispatch 的 GET/PUT。"""
import json

from printcast import settings as settings_module
from printcast import config


def _use_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    # settings_path() 依赖 config.DATA_DIR，storage 的 packs/media 也依赖它。
    return tmp_path


def test_defaults_when_missing(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    s = settings_module.load_settings()
    assert s['branding']['title'] == '头像打印机'
    assert s['branding']['links']
    assert s['broadcast']['scriptedPrint'] is True
    # 首次读取应顺手落盘默认配置。
    assert (tmp_path / 'settings.json').is_file()


def test_save_merges_and_persists(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    saved = settings_module.save_settings({'branding': {'title': '我的打印台'}})
    assert saved['branding']['title'] == '我的打印台'
    # 未提交的部分应保留默认值。
    assert saved['branding']['accent'] == '#4f8cff'
    # 重新加载应从磁盘读到合并结果。
    reloaded = settings_module.load_settings()
    assert reloaded['branding']['title'] == '我的打印台'


def test_sanitize_color_and_links(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    saved = settings_module.save_settings({
        'branding': {
            'accent': 'not-a-color',
            'links': [
                {'label': 'X', 'href': 'javascript:alert(1)'},
                {'label': 'OK', 'href': '/site/guide.html'},
                {'label': 'Y', 'href': 'https://example.com'},
                'bad-item',
            ],
        },
    })
    # 非法颜色回退默认。
    assert saved['branding']['accent'] == '#4f8cff'
    hrefs = [l['href'] for l in saved['branding']['links']]
    assert 'javascript:alert(1)' not in hrefs
    assert 'bad-item' not in hrefs
    assert '/site/guide.html' in hrefs
    assert 'https://example.com' in hrefs


def test_boolean_coercion(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    saved = settings_module.save_settings({
        'broadcast': {'scriptedPrint': 'true', 'autoStart': 'false', 'loop': 0},
        'printer': {'rules': {'comment': 'false', 'gift': 'true'}},
    })
    assert saved['broadcast']['scriptedPrint'] is True
    # 字符串 'false' 不能被 bool() 误判成真；这是展示端开关失灵的常见根因。
    assert saved['broadcast']['autoStart'] is False
    assert saved['broadcast']['loop'] is False
    assert saved['printer']['rules']['comment'] is False
    assert saved['printer']['rules']['gift'] is True


def test_sanitize_theme_numbers_and_unknown_sections(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    saved = settings_module.save_settings({
        'display': {'theme': 'neon', 'announceText': 'X' * 500},
        'printer': {'demoGapMs': '-5', 'idleSeconds': 999999},
        'bogus': {'should': 'not persist'},
    })
    assert saved['display']['theme'] == 'dark'
    assert len(saved['display']['announceText']) == 200
    assert saved['printer']['demoGapMs'] == 0
    assert saved['printer']['idleSeconds'] == 3600
    assert 'bogus' not in saved
    assert 'showAdStrip' not in saved.get('live', {}), '旧广告条开关已废弃'


def test_dangerous_link_schemes_rejected(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    saved = settings_module.save_settings({'branding': {'links': [
        {'label': 'x', 'href': 'data:text/html,<script>1</script>'},
        {'label': 'y', 'href': './site/guide.html'},
        {'label': 'z', 'href': 'https://example.com'},
    ]}})
    hrefs = [l['href'] for l in saved['branding']['links']]
    assert not any(h.startswith('data:') for h in hrefs)
    assert './site/guide.html' in hrefs
    assert 'https://example.com' in hrefs


def test_dispatch_get_and_put(monkeypatch):
    # 用独立临时目录，避免改动仓库 data/settings.json。
    import pathlib
    import tempfile
    monkeypatch.setattr(config, 'DATA_DIR', pathlib.Path(tempfile.mkdtemp()))
    from printcast import api
    r = api.dispatch('GET', '/__api/settings')
    assert r.status == 200
    body = json.loads(r.body)
    assert body['ok'] is True and 'branding' in body['settings']

    r = api.dispatch('PUT', '/__api/settings', body=json.dumps(
        {'branding': {'title': '控制台命名'}}).encode('utf-8'))
    assert r.status == 200
    assert json.loads(r.body)['settings']['branding']['title'] == '控制台命名'

    # 非 dict 拒绝。
    r = api.dispatch('PUT', '/__api/settings', body=b'[]')
    assert r.status == 400


def test_dispatch_delete_resets_settings(monkeypatch):
    import pathlib
    import tempfile
    monkeypatch.setattr(config, 'DATA_DIR', pathlib.Path(tempfile.mkdtemp()))
    from printcast import api
    api.dispatch('PUT', '/__api/settings', body=json.dumps(
        {'branding': {'title': '临时命名'}}).encode('utf-8'))
    r = api.dispatch('DELETE', '/__api/settings')
    assert r.status == 200
    assert json.loads(r.body)['settings']['branding']['title'] == '头像打印机'


def test_reset(tmp_path, monkeypatch):
    _use_tmp(tmp_path, monkeypatch)
    settings_module.save_settings({'branding': {'title': '临时'}})
    reset = settings_module.reset_settings()
    assert reset['branding']['title'] == '头像打印机'


def test_auto_start_broadcast_is_console_driven(tmp_path, monkeypatch):
    """autoStart / defaultPacks / strategy / mode / loop 由控制台设置驱动后端开播。"""
    from printcast import server
    _use_tmp(tmp_path, monkeypatch)

    class FakeBroadcast:
        def __init__(self):
            self.calls = []

        def start(self, **kwargs):
            self.calls.append(kwargs)
            return {'ok': True}

    fake = FakeBroadcast()
    settings_module.save_settings({'broadcast': {
        'autoStart': True, 'defaultPacks': ['ming-emperors'],
        'strategy': 'interleave', 'mode': 'weighted', 'loop': True,
    }})
    server.auto_start_broadcast(fake)
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call['pack_ids'] == ['ming-emperors']
    assert call['strategy'] == 'interleave'
    assert call['mode'] == 'weighted'
    assert call['loop'] is True

    # 默认关闭时不应开播；配置非法（包不存在）也不能抛异常拖垮服务启动。
    settings_module.reset_settings()
    never = FakeBroadcast()
    server.auto_start_broadcast(never)
    assert never.calls == []
    settings_module.save_settings({'broadcast': {
        'autoStart': True, 'defaultPacks': ['does-not-exist'],
    }})
    broken = FakeBroadcast()
    broken.start = lambda **kw: (_ for _ in ()).throw(RuntimeError('bad pack'))
    assert server.auto_start_broadcast(broken) is None
