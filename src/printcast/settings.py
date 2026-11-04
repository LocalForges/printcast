"""控制台设置：本程序唯一可写配置的落点（品牌 / 打印机 / 出场广播 / 直播 / 展示）。

边界原则（与「前端展示端只读」严格区分）：
- 写入只发生在这里（经 /__api/settings 的 PUT），以及工作台 UI 对它的调用；
- 所有展示页（web/index.html、broadcast.html、live-view.html、app.zh.mjs）只 GET，不 PUT；
- 这样「参数由控制台统一设置，其它端只负责展示」才成立。

持久化沿用 storage 的约束：纯 stdlib、原子写、路径收敛到 data/ 之内。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import config

# —— 默认配置（也是 schema 的唯一事实来源；工作台据此渲染表单）——
DEFAULT_SETTINGS = {
    'branding': {
        'title': '头像打印机',
        'subtitle': '直播间弹幕与剧本驱动的 3D 打印直播台',
        'accent': '#4f8cff',
        'footer': '本程序完全免费、本地运行，数据不上传任何云端。',
        'links': [
            {'label': '功能介绍', 'href': '/site/features.html'},
            {'label': '使用教程', 'href': '/site/guide.html'},
        ],
    },
    'display': {
        'theme': 'dark',
        'overlayText': 'PRINTCAST 01',
        'overlaySub': '正在制作专属头像，打印完成自动切换下一位',
        'showDemoBadge': True,
        # 公告条：取代旧版硬编码的第三方广告条。文案与链接全部来自控制台，
        # 展示页不含任何硬编码内容，默认关闭。
        'showAnnounce': False,
        'announceText': '',
    },
    'printer': {
        # 打印规则：与前端 printRules 默认值保持一致；控制台写入后优先生效。
        'rules': {
            'comment': True, 'join': False, 'like': False, 'follow': False,
            'gift': True, 'giftVoice': True, 'joinVoice': True,
        },
        'autoDemo': True,
        'demoGapMs': 30000,
        'idleFill': False,
        'idleSeconds': 30,
    },
    'broadcast': {
        'defaultPacks': [],
        'strategy': 'concat',
        'mode': '',
        'loop': False,
        'autoStart': False,
        'speech': True,
        # M1：把出场角色也打到 3D 打印机（"讲到谁就打谁"），默认开启。
        'scriptedPrint': True,
    },
    'live': {
        'defaultRoom': '',
        'platform': 'douyin',
    },
}

_SECTIONS = tuple(DEFAULT_SETTINGS.keys())
_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{3,8}$')
# 只放行 http(s) 与站内相对路径 / 锚点；拒绝 javascript:、data: 等可执行协议。
_LINK_RE = re.compile(r'^(?:https?://|/|\./|\.\./|#|\?)', re.I)


def _as_bool(value, default):
    """把控制台传来的 'false' / 0 之类正确收口成布尔，避免 bool('false') 为真。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ('false', '0', 'no', 'off', ''):
            return False
        if low in ('true', '1', 'yes', 'on'):
            return True
    return bool(value)


def _as_int(value, default, minimum=0, maximum=None):
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    if out < minimum:
        out = minimum
    if maximum is not None and out > maximum:
        out = maximum
    return out


def settings_path() -> Path:
    return config.DATA_DIR / 'settings.json'


def _deep_merge(base: dict, override: dict) -> dict:
    """深合并：override 的标量 / 列表覆盖 base；嵌套 dict 递归。"""
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _sanitize_settings(data: dict) -> dict:
    """对合并后的配置做收口校验：颜色、链接、开关类型。非法值回退到默认。"""
    data = _deep_merge(DEFAULT_SETTINGS, data)
    b = data.setdefault('branding', {})
    if not _COLOR_RE.match(str(b.get('accent', ''))):
        b['accent'] = DEFAULT_SETTINGS['branding']['accent']
    links = b.get('links')
    if not isinstance(links, list):
        b['links'] = DEFAULT_SETTINGS['branding']['links']
    else:
        clean = []
        for item in links:
            if not isinstance(item, dict):
                continue
            href = str(item.get('href', '') or '')
            label = str(item.get('label', '') or '')[:40]
            # 拒绝 javascript: 等危险协议，其余（相对路径 / http(s) / 锚点）放行。
            if not _LINK_RE.match(href) and not href.startswith('http'):
                continue
            if href.lower().startswith('javascript:'):
                continue
            clean.append({'label': label, 'href': href[:256]})
        b['links'] = clean
    # 布尔与数值收口，避免控制台误传字符串（'false' 会被 bool() 判成真）导致前端判断失灵。
    bool_fields = (
        ('display', 'showDemoBadge', True),
        ('display', 'showAnnounce', False),
        ('printer', 'autoDemo', True),
        ('printer', 'idleFill', False),
        ('broadcast', 'loop', False),
        ('broadcast', 'autoStart', False),
        ('broadcast', 'speech', True),
        ('broadcast', 'scriptedPrint', True),
    )
    for sec, key, default in bool_fields:
        node = data.setdefault(sec, {})
        node[key] = _as_bool(node.get(key, default), default)
    for key in ('comment', 'join', 'like', 'follow', 'gift', 'giftVoice', 'joinVoice'):
        node = data.setdefault('printer', {}).setdefault('rules', {})
        node[key] = _as_bool(node.get(key), DEFAULT_SETTINGS['printer']['rules'][key])

    printer = data.setdefault('printer', {})
    printer['demoGapMs'] = _as_int(printer.get('demoGapMs'),
                                  DEFAULT_SETTINGS['printer']['demoGapMs'], maximum=600000)
    printer['idleSeconds'] = _as_int(printer.get('idleSeconds'),
                                     DEFAULT_SETTINGS['printer']['idleSeconds'], 5, 3600)
    display = data.setdefault('display', {})
    if display.get('theme') not in ('dark', 'light'):
        display['theme'] = 'dark'
    display['announceText'] = str(display.get('announceText') or '')[:200]
    # 未知分区不落盘，避免脏配置无限膨胀。
    return {k: v for k, v in data.items() if k in _SECTIONS}


def load_settings() -> dict:
    """读取配置；文件缺失或损坏时返回默认配置（并顺手落盘一次，保证展示端总有稳定文档）。"""
    path = settings_path()
    data: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            data = {}
    if not path.is_file():
        return save_settings({})
    return _sanitize_settings(data)


def save_settings(partial: dict) -> dict:
    """合并并持久化控制台提交的部分配置，返回完整配置。"""
    current = load_settings() if settings_path().is_file() else dict(DEFAULT_SETTINGS)
    merged = _sanitize_settings(_deep_merge(current, partial or {}))
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp-' + os.urandom(4).hex())
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)
    return merged


def reset_settings() -> dict:
    path = settings_path()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    return load_settings()
