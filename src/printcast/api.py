"""内容包 REST API：纯函数分发层，不依赖 http.server。

server.py 只负责读取字节与写回响应；所有路由、校验、错误格式都在这里，
因此 test_api.py 可以直接调 dispatch() 而不必起 HTTP 服务。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import config, importer, schema, storage, templates
from .scheduler import ContentScheduler

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
    """保存内容包：先校验再落盘，校验错误逐条返回。"""
    data = _json_body(body)
    cleaned, errors = schema.validate_pack(data)
    if errors:
        return Response(422, json.dumps(
            {'ok': False, 'error': '内容包校验失败', 'errors': errors},
            ensure_ascii=False).encode('utf-8'))
    saved = storage.save_pack(cleaned)
    return _ok({'ok': True, 'pack': saved}, 201)


def dispatch(method, path, query=None, headers=None, body=b''):
    """返回 Response；路径不属于 /__api/ 时返回 None 交给上层继续匹配。"""
    method = (method or 'GET').upper()
    query, headers = query or {}, headers or {}
    if not path.startswith('/__api/'):
        return None

    parts = [p for p in path.split('?')[0].split('/') if p]
    # parts = ['__api', <resource>, <id>?]

    if path.startswith('/__api/schema'):
        if method != 'GET':
            return _bad('只支持 GET', 405)
        doc = schema.schema_document()
        doc['limits'] = {
            'maxJsonBytes': config.MAX_JSON_BYTES,
            'maxMediaBytes': config.MAX_MEDIA_BYTES,
            'allowedImageExt': sorted(config.ALLOWED_IMAGE_EXT),
        }
        return _ok({'ok': True, 'schema': doc})

    if re.fullmatch(r'/__api/template\.(csv|json)', path):
        if method != 'GET':
            return _bad('只支持 GET', 405)
        fmt = path.rsplit('.', 1)[1]
        data, ctype, filename = templates.template_bytes(fmt)
        return Response(200, data, ctype, {
            'Content-Disposition': 'attachment; filename="%s"' % filename,
        })

    if path.startswith('/__api/packs'):
        pack_id = parts[2] if len(parts) > 2 else ''
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

    if path.startswith('/__api/import'):
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

    if path.startswith('/__api/media'):
        media_id = parts[2] if len(parts) > 2 else ''
        if method == 'GET' and not media_id:
            return _ok({'ok': True, 'media': storage.list_media()})
        if method == 'POST' and not media_id:
            original = (_query_first(query, 'name')
                        or headers.get('x-file-name')
                        or headers.get('x-filename') or 'upload')
            try:
                record = storage.save_media(
                    body, original, headers.get('content-type', ''))
            except ValueError as exc:
                return _bad(str(exc))
            return _ok({'ok': True, 'media': record}, 201)
        if method == 'DELETE' and media_id:
            return _ok({'ok': True, 'deleted': storage.delete_media(media_id)})
        return _bad('不支持的方法', 405)

    if path.startswith('/__api/schedule'):
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
        seed_raw = _query_first(query, 'seed', '')
        seed = int(seed_raw) if seed_raw.isdigit() else (seed_raw or None)
        count_raw = _query_first(query, 'count', '')
        count = int(count_raw) if count_raw.isdigit() else None
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
            'appearances': sched.plan(count),
            'progress': sched.progress(),
        })

    return _bad('未知的 API 路径', 404)
