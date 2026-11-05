"""控制台设置：本程序唯一可写配置的落点（品牌 / 打印机 / 出场广播 / 直播 / 展示）。

边界原则（与「前端展示端只读」严格区分）：
- 写入只发生在这里（经 /__api/settings 的 PUT），以及工作台 UI 对它的调用；
- 所有展示页（web/index.html、web/live-view.html、web-src/ 渲染模块）只 GET，不 PUT；
- 这样「参数由控制台统一设置，其它端只负责展示」才成立。

持久化：SQLite（db.py）是运行时唯一数据源，深合并与净化在单个写事务里完成，
消除了早期「读 JSON → 合并 → 覆盖写」的并发丢更新；同时尽力同步一份
data/settings.json 作为可读的分发 / 备份镜像。纯 stdlib，零第三方依赖。
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from . import config, db

# —— 默认配置（也是 schema 的唯一事实来源；工作台据此渲染表单）——
DEFAULT_SETTINGS = {
    'branding': {
        'title': '头像打印机',
        'subtitle': '直播间弹幕与剧本驱动的 3D 打印直播台',
        'accent': '#4f8cff',
        'footer': '本程序完全免费、本地运行，数据不上传任何云端。',
        # 宣传页已下线；控制台可自行配置外链，默认不挂任何链接。
        'links': [],
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
        'defaultPacks': ['demo-people'],
        'strategy': 'concat',
        'mode': 'sequence',
        'loop': True,
        # 出场广播默认开机即播：启动后自动开播并连续出场，展示端无需手动点「推进下一个」。
        'autoStart': True,
        'autoPlay': True,
        'autoPlayIntervalMs': 5000,
        'speech': True,
        # M1：把出场角色也打到 3D 打印机（"讲到谁就打谁"），默认开启。
        'scriptedPrint': True,
    },
    'live': {
        'defaultRoom': '',
        'platform': 'douyin',
        # 未接入真实采集时，用内置演示人物填充直播画面，保证开箱即用、第一时间看到效果。
        'demoFill': True,
    },
}

_SECTIONS = tuple(DEFAULT_SETTINGS.keys())
_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{3,8}$')
# 只放行 http(s) 与站内相对路径 / 锚点；拒绝 javascript:、data: 等可执行协议。
_LINK_RE = re.compile(r'^(?:https?://|/|\./|\.\./|#|\?)', re.I)
_DANGEROUS_SCHEMES = ('javascript:', 'data:', 'vbscript:', 'file:', 'blob:')


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
    """JSON 备份镜像路径（DB 才是运行时数据源）。"""
    return config.DATA_DIR / 'settings.json'


def _deep_merge(base: dict, override: dict) -> dict:
    """深合并：override 的标量 / 列表覆盖 base；嵌套 dict 递归。

    必须深拷贝 base —— 早期用 `dict(base)` 浅拷贝，净化函数原地写 nested dict
    会把用户值写回模块级 DEFAULT_SETTINGS，导致「恢复出厂设置」被污染。
    """
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _safe_href(href: str):
    """链接协议白名单：http(s) 绝对地址，或站内相对路径 / 锚点；其余一律拒绝。

    旧实现用 `href.startswith('http')` 兜底，形如 `httpjavascript:alert(1)` 能绕过。
    """
    if not href or len(href) > 256:
        return None
    low = href.lower()
    if low.startswith(_DANGEROUS_SCHEMES):
        return None
    if low.startswith(('http://', 'https://')):
        parts = urlsplit(href)
        return href if parts.scheme.lower() in ('http', 'https') and parts.netloc else None
    if low.startswith('//'):
        return None  # 协议相对 URL 可能指向任意站点，不纳入白名单
    return href if _LINK_RE.match(href) else None


def _sanitize_settings(data: dict) -> dict:
    """对合并后的配置做收口校验：颜色、链接、开关类型。非法值回退到默认。"""
    data = _deep_merge(DEFAULT_SETTINGS, data)
    b = data.setdefault('branding', {})
    if not _COLOR_RE.match(str(b.get('accent', ''))):
        b['accent'] = DEFAULT_SETTINGS['branding']['accent']
    links = b.get('links')
    if not isinstance(links, list):
        b['links'] = copy.deepcopy(DEFAULT_SETTINGS['branding']['links'])
    else:
        clean = []
        for item in links:
            if not isinstance(item, dict):
                continue
            href = _safe_href(str(item.get('href', '') or ''))
            if href is None:
                continue
            label = str(item.get('label', '') or '')[:40]
            clean.append({'label': label, 'href': href})
        b['links'] = clean
    # 布尔与数值收口，避免控制台误传字符串（'false' 会被 bool() 判成真）导致前端判断失灵。
    bool_fields = (
        ('display', 'showDemoBadge', True),
        ('display', 'showAnnounce', False),
        ('printer', 'autoDemo', True),
        ('printer', 'idleFill', False),
        ('broadcast', 'loop', False),
        ('broadcast', 'autoStart', False),
        ('broadcast', 'autoPlay', False),
        ('broadcast', 'speech', True),
        ('broadcast', 'scriptedPrint', True),
        ('live', 'demoFill', True),
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
    # 自动播放间隔：200ms–60s 之间收口，越界回退默认 5000ms。
    broadcast = data.setdefault('broadcast', {})
    broadcast['autoPlayIntervalMs'] = _as_int(broadcast.get('autoPlayIntervalMs'),
                                              DEFAULT_SETTINGS['broadcast']['autoPlayIntervalMs'],
                                              200, 60000)
    display = data.setdefault('display', {})
    if display.get('theme') not in ('dark', 'light'):
        display['theme'] = 'dark'
    display['announceText'] = str(display.get('announceText') or '')[:200]
    # 采集平台：只认采集器注册表里的 id，未知值回落 douyin（老配置里的 'other' 也落到这里）。
    live = data.setdefault('live', {})
    if live.get('platform') not in ('douyin', 'generic'):
        live['platform'] = 'douyin'
    live['defaultRoom'] = str(live.get('defaultRoom') or '')[:64]
    # 未知分区不落盘，避免脏配置无限膨胀。
    return {k: v for k, v in data.items() if k in _SECTIONS}


def _mirror():
    """尽力同步 settings.json / media/index.json 备份；失败不影响业务响应。"""
    try:
        db.export_json(only_ids=[], write_meta=True)
    except Exception:  # noqa: BLE001 — 备份是 best-effort
        pass


def load_settings() -> dict:
    """读取配置；库里缺失或文档损坏时写入净化后的默认配置并落盘一次。"""
    doc = db.get_settings_doc()
    if doc is None:
        return save_settings({})
    return _sanitize_settings(doc)


def save_settings(partial: dict) -> dict:
    """在单个写事务里合并、净化并持久化，返回完整配置。"""
    def mutate(current):
        base = current if isinstance(current, dict) else {}
        return _sanitize_settings(_deep_merge(base, partial or {}))

    merged = db.update_settings(mutate)
    _mirror()
    return merged


def reset_settings() -> dict:
    db.delete_settings_doc()
    return load_settings()
