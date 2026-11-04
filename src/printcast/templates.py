"""数据模板生成：CSV / JSON 两种，字段全部来自 schema.py。

CSV 带 UTF-8 BOM（Excel 双击不乱码），顶部 # 注释行写字段说明，
示例行也以 # 注释——这样「下载模板后直接导入」不会产生脏数据，
用户取消注释即可照抄。导入器会跳过所有 # 行。
"""
from __future__ import annotations

import csv
import io
import json

from .schema import CHARACTER_FIELDS, PACK_FIELDS, csv_columns, example_rows


def csv_template_bytes():
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\r\n')

    writer.writerow(['# printcast 内容包导入模板：删除 # 开头的说明行，从第 1 行数据开始填写'])
    writer.writerow(['# 字段：' + ' | '.join(
        '%s=%s' % (f['key'], f['label']) for f in CHARACTER_FIELDS)])
    writer.writerow(['# 提示：' + ' ; '.join(
        '%s %s' % (f['key'], f.get('hint', '')) for f in CHARACTER_FIELDS)])
    writer.writerow(['# 示例（去掉行首 # 即可作为数据）：'])
    writer.writerow(csv_columns())
    for row in example_rows():
        writer.writerow(['# ' + ','.join(
            _csv_cell(row.get(key, '')) for key in csv_columns())])

    # 注释示例行用单个字段承载，csv.writer 会正确转义其中的逗号与引号。
    return ('\ufeff' + out.getvalue()).encode('utf-8')


def _csv_cell(value):
    text = str(value)
    if any(ch in text for ch in (',', '"', '\r', '\n')):
        return '"' + text.replace('"', '""') + '"'
    return text


def json_template_bytes():
    pack = {f['key']: f.get('example', '') for f in PACK_FIELDS}
    pack['loop'] = False
    pack['characters'] = [
        {f['key']: f.get('example', '') for f in CHARACTER_FIELDS},
        dict(id='yongle', name='朱棣', order=2, avatar='yongle.png',
             speech='永乐迁都，四海宾服', weight=1, tags=['迁都', '帝王']),
    ]
    return json.dumps(pack, ensure_ascii=False, indent=2).encode('utf-8')


def template_bytes(fmt):
    if fmt == 'json':
        return json_template_bytes(), 'application/json; charset=utf-8', 'printcast-template.json'
    return csv_template_bytes(), 'text/csv; charset=utf-8', 'printcast-template.csv'
