"""数据导入：CSV / JSON 解析 + 逐行校验 + 结构化错误报告。

原则：**绝不静默丢行**。任何一行有错，整批都不落盘，并把
{line, field, message} 全部返回给前端，让用户一次改完再提交。
校验通过且 commit=1 时才由 api 层写入 storage。
"""
from __future__ import annotations

import csv
import io
import json

from .schema import csv_columns, validate_pack


def _err(line, field, message):
    return {'line': line, 'field': field, 'message': message}


def parse_rows(text):
    """解析 CSV 文本（跳过 # 注释与空行），返回 (rows, errors)。"""
    rows, errors = [], []
    lines = text.splitlines()
    kept = []
    for number, raw in enumerate(lines, start=1):
        stripped = raw.lstrip('\ufeff').strip()
        if not stripped or stripped.startswith('#'):
            continue
        kept.append((number, raw))

    if not kept:
        return [], [_err(0, 'file', '没有可导入的数据行（模板的说明/示例行以 # 开头，需去掉 # 才能作为数据）')]

    reader = csv.DictReader(
        io.StringIO('\n'.join(raw for _, raw in kept)),
        restkey='__extra__', restval='')
    header = reader.fieldnames or []
    columns = set(csv_columns())
    missing_required = [c for c in ('id', 'name') if c not in header]
    if missing_required:
        errors.append(_err(kept[0][0], 'header',
                           '表头缺少必需列：%s' % ' / '.join(missing_required)))
    unknown = [h for h in header if h and h not in columns]
    if unknown:
        # 只提示，不判错：导入时会忽略额外列。
        errors.append(_err(kept[0][0], 'header',
                           '检测到额外列（将被忽略）：%s' % ' / '.join(unknown)))

    for offset, values in enumerate(reader):
        line = kept[offset + 1][0] if offset + 1 < len(kept) else offset + 2
        row = {}
        for key in columns:
            if key in values:
                row[key] = values[key]
        rows.append((line, row))
    return rows, errors


def parse_payload(payload):
    """payload: {format: csv|json, pack: {...}, content: str|dict}
    返回 (pack_dict_or_None, errors, stats)。
    """
    if not isinstance(payload, dict):
        return None, [_err(0, 'body', '请求体必须是 JSON 对象')], {}

    fmt = str(payload.get('format', 'csv')).lower()
    content = payload.get('content')
    meta = payload.get('pack') or {}
    if not isinstance(meta, dict):
        return None, [_err(0, 'pack', 'pack 必须是对象')], {}

    errors = []
    csv_line_numbers = []
    if fmt == 'csv':
        if not isinstance(content, str):
            return None, [_err(0, 'content', 'CSV 导入时 content 必须是文本')], {}
        rows, parse_errors = parse_rows(content)
        errors.extend(parse_errors)
        characters = [row for _, row in rows]
        csv_line_numbers = [number for number, _ in rows]
        pack = dict(meta)
        pack['characters'] = characters
        total = len(characters)
    elif fmt == 'json':
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except ValueError as exc:
                return None, [_err(0, 'content', 'JSON 解析失败：%s' % exc)], {}
        if not isinstance(content, dict):
            return None, [_err(0, 'content', 'JSON 导入时 content 必须是内容包对象')], {}
        pack = dict(meta)
        pack.update(content)
        total = len(pack.get('characters') or []) if isinstance(
            pack.get('characters'), list) else 0
    else:
        return None, [_err(0, 'format', 'format 只能是 csv 或 json')], {}

    cleaned, validation_errors = validate_pack(pack)
    # 把「第 N 条数据」映射回 CSV 原始行号，用户能直接在 Excel 里定位。
    if csv_line_numbers:
        for item in validation_errors:
            index = item.get('line', 0)
            if 1 <= index <= len(csv_line_numbers):
                item['line'] = csv_line_numbers[index - 1]
    errors.extend(validation_errors)
    # 表头的提示类错误不应阻止导入（额外列会被忽略）。
    blocking = [e for e in errors if not (
        e.get('field') == 'header' and '额外列' in e.get('message', ''))]
    stats = {
        'total': total,
        'accepted': len(cleaned['characters']) if cleaned else 0,
        'errors': len(blocking),
        'format': fmt,
    }
    return (cleaned if not blocking else None), errors, stats
