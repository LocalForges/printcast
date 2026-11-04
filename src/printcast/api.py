"""内容包 REST API：纯函数分发层，不依赖 http.server。

server.py 只负责读取字节与写回响应；所有路由、校验、错误格式都在这里，
因此 test_api.py 可以直接调 dispatch() 而不必起 HTTP 服务。

路由采用「段精确匹配」：早期用 `path.startswith('/__api/settings')`，导致
`DELETE /__api/settings/anything` 也会命中并清空全部配置。现在按 URL 段解析，
多余尾段一律 404，写操作尤其不接受模糊前缀。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

from . import audit, config, db, importer, schema, storage, templates
from . import settings as settings_module
from .scheduler import ContentScheduler, normalize_seed

_JSON = 'application/json; charset=utf-8'


@dataclass
class Response:
    status: int
    body: bytes
    content_type: str = _JSON
    headers: dict = field(default_factory=dict)


def _ok(value, status=200):
    return Response(status, json.dumps(value, ensure_ascii=False).encode('utf-8'))


def _bad(message, status=400):
    return _ok({'ok': False, 'error': message}, status)


def _query_first(query, key, default=''):
    value = query.get(key, [default])
    return value[0] if isinstance(value, list) and value else (value or default)


def _truthy(value):
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _json_body(body):
    if not body:
        raise ValueError('请求体为空')
    if len(body) > config.MAX_JSON_BYTES:
        raise ValueError('请求体超过 %d MB 上限' % (config.MAX_JSON_BYTES // 1024 // 1024))
    try:
        return json.loads(body.decode('utf-8-sig'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError('JSON 解析失败：%s' % exc)


def _pack_json(body):
    """保存内容包：先校验再落库，校验错误逐条返回。"""
    data = _json_body(body)
    cleaned, errors = schema.validate_pack(data)
    if errors:
        return Response(422, json.dumps(
            {'ok': False, 'error': '内容包校验失败', 'errors': errors},
            ensure_ascii=False).encode('utf-8'))
    saved = storage.save_pack(cleaned)
    return _ok({'ok': True, 'pack': saved}, 201)


def _route(path):
    """返回 (clean_path, resource, extras)；不属于 /__api/ 时 resource 为 None。"""
    clean = path.split('?', 1)[0]
    parts = [p for p in clean.split('/') if p]
    if len(parts) < 2 or parts[0] != '__api':
        return clean, None, []
    return clean, parts[1], parts[2:]


def dispatch(method, path, query=None, headers=None, body=b''):
    """返回 Response；路径不属于 /__api/ 时返回 None 交给上层继续匹配。"""
    method = (method or 'GET').upper()
    query, headers = query or {}, headers or {}
    clean, resource, extras = _route(path)
    if resource is None:
        return None

    if resource == 'schema' and not extras:
        if method != 'GET':
            return _bad('只支持 GET', 405)
        doc = schema.schema_document()
        doc['limits'] = {
            'maxJsonBytes': config.MAX_JSON_BYTES,
            'maxMediaBytes': config.MAX_MEDIA_BYTES,
            'allowedImageExt': sorted(config.ALLOWED_IMAGE_EXT),
        }
        return _ok({'ok': True, 'schema': doc})

    if re.fullmatch(r'/__api/template\.(csv|json)', clean):
        if method != 'GET':
            return _bad('只支持 GET', 405)
        fmt = clean.rsplit('.', 1)[1]
        data, ctype, filename = templates.template_bytes(fmt)
        return Response(200, data, ctype, {
            'Content-Disposition': 'attachment; filename="%s"' % filename,
        })

    # —— 数据库状态（只读，供工作台确认「数据已落库」）——
    if resource == 'db' and not extras:
        if method != 'GET':
            return _bad('只支持 GET', 405)
        return _ok({'ok': True, 'db': db.stats()})

    # —— 控制台设置（唯一可写配置来源；展示端只读）——
    if resource == 'settings' and not extras:
        if method == 'GET':
            return _ok({'ok': True, 'settings': settings_module.load_settings()})
        if method == 'DELETE':
            return _ok({'ok': True, 'settings': settings_module.reset_settings()})
        if method in ('POST', 'PUT'):
            try:
                parsed = _json_body(body)
            except ValueError as exc:
                return _bad(str(exc))
            if not isinstance(parsed, dict):
                return _bad('设置必须是 JSON 对象')
            return _ok({'ok': True, 'settings': settings_module.save_settings(parsed)})
        return _bad('不支持的方法', 405)

    # —— 本机操作日志（控制台专属，展示端不调用）——
    # GET 只读；DELETE 清空。写操作日志由 server 层统一埋点，保证所有入口
    # （内容包 / 设置 / 媒体 / 广播 / 数据桥 / 窗口）都覆盖到，而非靠前端上报。
    if resource == 'audit' and not extras:
        if method == 'GET':
            limit = _query_first(query, 'limit', '100')
            action = _query_first(query, 'action', '')
            q = _query_first(query, 'q', '')
            only_failed = _truthy(_query_first(query, 'onlyFailed', '')
                                  or _query_first(query, 'failed', ''))
            return _ok({'ok': True,
                        'entries': audit.list_entries(limit, action, q, only_failed),
                        'stats': audit.stats()})
        if method == 'DELETE':
            # 清空与「补记一条 audit.clear」在同一事务里原子完成；server 不再补记。
            audit.clear_with_record('清空操作日志')
            return _ok({'ok': True, 'cleared': True})
        return _bad('不支持的方法', 405)

    # 路径穿越类 ID 一律先判非法（400），不要被「多余尾段 404」掩盖，
    # 也不要落到文件系统路径解析。
    if resource == 'packs' and extras and not storage.valid_pack_id(extras[0]):
        return _bad('非法的内容包 ID')

    if resource == 'packs' and len(extras) <= 1:
        pack_id = extras[0] if extras else ''
        if method == 'GET' and not pack_id:
            return _ok({'ok': True, 'packs': storage.list_packs()})
        if method == 'GET':
            pack = storage.get_pack(pack_id) if storage.valid_pack_id(pack_id) else None
            return _ok({'ok': True, 'pack': pack}) if pack else _bad('内容包不存在', 404)
        if method in ('POST', 'PUT'):
            try:
                return _pack_json(body)
            except ValueError as exc:
                return _bad(str(exc))
        if method == 'DELETE' and pack_id:
            if not storage.valid_pack_id(pack_id):
                return _bad('非法的内容包 ID')
            return _ok({'ok': True, 'deleted': storage.delete_pack(pack_id)})
        return _bad('不支持的方法', 405)

    if resource == 'import' and not extras:
        if method != 'POST':
            return _bad('只支持 POST', 405)
        try:
            payload = _json_body(body)
        except ValueError as exc:
            return _bad(str(exc))
        pack, errors, stats = importer.parse_payload(payload)
        report = {
            'ok': pack is not None,
            'errors': errors,
            'stats': stats,
            'preview': [{'id': c['id'], 'name': c['name'], 'order': c.get('order', 0)}
                        for c in (pack or {}).get('characters', [])[:10]],
            'committed': False,
        }
        if pack is None:
            report['error'] = '校验未通过，未写入任何数据'
            return Response(422, json.dumps(report, ensure_ascii=False).encode('utf-8'))
        if _truthy(_query_first(query, 'commit')):
            saved = storage.save_pack(pack)
            report['committed'] = True
            report['pack'] = saved
        else:
            report['pack'] = pack
        return _ok(report)

    if resource == 'media' and len(extras) <= 1:
        media_id = extras[0] if extras else ''
        if method == 'GET' and not media_id:
            return _ok({'ok': True, 'media': storage.list_media()})
        if method == 'POST' and not media_id:
            # 前端用 encodeURIComponent 传中文文件名，后端必须解码后再存。
            original = unquote(str(_query_first(query, 'name')
                                   or headers.get('x-file-name')
                                   or headers.get('x-filename') or 'upload'))
            try:
                record = storage.save_media(
                    body, original, headers.get('content-type', ''))
            except ValueError as exc:
                return _bad(str(exc))
            return _ok({'ok': True, 'media': record}, 201)
        if method == 'DELETE' and media_id:
            return _ok({'ok': True, 'deleted': storage.delete_media(media_id)})
        return _bad('不支持的方法', 405)

    if resource == 'schedule' and not extras:
        if method != 'GET':
            return _bad('只支持 GET', 405)
        pack_ids = query.get('pack', query.get('packs', []))
        if isinstance(pack_ids, str):
            pack_ids = [pack_ids]
        pack_ids = [p for p in pack_ids if p]
        if not pack_ids:
            return _bad('至少指定一个 pack 参数，如 /__api/schedule?pack=ming-emperors', 400)
        strategy = _query_first(query, 'strategy', 'concat')
        mode = _query_first(query, 'mode', '') or None
        # 与 /broadcast 共用同一个归一化函数：纯数字字符串与数字必须产生同一序列。
        seed = normalize_seed(_query_first(query, 'seed', ''))
        count_raw = _query_first(query, 'count', '')
        count = int(count_raw) if str(count_raw).isdigit() else None
        # 预演序列要渲染成时间轴卡片，超过一个合理上限会拖垮页面与后端。
        if count is not None:
            count = max(1, min(count, 300))
        loop_raw = _query_first(query, 'loop', '')
        loop = _truthy(loop_raw) if loop_raw else None
        packs, missing = [], []
        for pid in pack_ids:
            pack = storage.get_pack(pid) if storage.valid_pack_id(pid) else None
            if pack is None:
                missing.append(pid)
            else:
                packs.append(pack)
        if missing:
            return _bad('内容包不存在：%s' % ','.join(missing), 404)
        try:
            sched = ContentScheduler(packs, strategy=strategy, seed=seed)
        except ValueError as exc:
            return _bad(str(exc))
        if mode:
            if mode not in ('sequence', 'weighted', 'trigger'):
                return _bad('非法出场模式：%s' % mode)
            sched.mode = mode
        if loop is not None:
            sched.loop = loop
        return _ok({
            'ok': True,
            'packIds': pack_ids,
            'strategy': strategy,
            'mode': sched.mode,
            'loop': sched.loop,
            # 回显 seed / count 让「固定 seed 复现」可被复制、比对与回放。
            'seed': seed,
            'count': count,
            'appearances': sched.plan(count),
            'progress': sched.progress(),
        })

    return _bad('未知的 API 路径', 404)
