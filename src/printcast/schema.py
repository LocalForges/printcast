"""内容包领域模型：字段元数据是唯一事实来源。

同一份定义同时驱动四件事，新增字段只改这里一处：
  1. CSV 模板的列与示例行（templates.py）
  2. 导入时的逐行校验（importer.py）
  3. 前端表单 / 表格自动生成（GET /__api/schema）
  4. 规则层出场顺序调度（src/rules/）

刻意不引入 pydantic / marshmallow：核心层保持零第三方依赖，
而这份元数据本身已经足够表达约束，并可直接序列化给浏览器。
"""
from __future__ import annotations

import re

ID_PATTERN = r'^[a-z0-9][a-z0-9_-]{0,63}$'
_ID_RE = re.compile(ID_PATTERN)
# 允许媒体文件名里的中文与常见字符，但拒绝路径分隔符与控制字符。
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

MODES = {
    'sequence': '按 order 依次出场（叙事顺序，对应「明朝皇帝 / 故事人物出场先后」）',
    'weighted': '按 weight 加权随机出场',
    'trigger': '绑定礼物或评论事件触发，与 src/rules 的 RULES 对接',
}

PACK_FIELDS = [
    dict(key='id', label='内容包 ID', type='string', required=True,
         pattern=ID_PATTERN, maxLength=64, example='ming-emperors',
         hint='小写字母/数字/下划线/连字符，作为文件名与 URL 标识'),
    dict(key='title', label='标题', type='string', required=True,
         maxLength=80, example='明朝十六帝', hint='展示用名称'),
    dict(key='mode', label='出场模式', type='enum', required=False,
         values=list(MODES), default='sequence', example='sequence',
         hint='sequence / weighted / trigger'),
    dict(key='loop', label='循环播放', type='boolean', required=False,
         default=False, example='false', hint='true / false'),
    dict(key='description', label='说明', type='string', required=False,
         maxLength=500, example='按即位顺序依次出场', hint='可选'),
]

CHARACTER_FIELDS = [
    dict(key='id', label='唯一标识', type='string', required=True,
         pattern=ID_PATTERN, maxLength=64, example='hongwu',
         hint='小写字母/数字/下划线/连字符，包内唯一'),
    dict(key='name', label='名称', type='string', required=True,
         maxLength=64, example='朱元璋', hint='打印卡片与语音播报显示的名称'),
    dict(key='order', label='出场顺序', type='integer', required=False,
         min=0, max=9999, default=0, example='1',
         hint='sequence 模式下按此值升序出场，相同值按表中先后'),
    dict(key='avatar', label='头像文件', type='media', required=False,
         maxLength=255, example='hongwu.png',
         hint='上传后的媒体 id（见 /__api/media），留空用默认头像'),
    dict(key='speech', label='播报文案', type='string', required=False,
         maxLength=500, example='洪武开基，定鼎金陵', hint='可选，交给语音层朗读'),
    dict(key='weight', label='权重', type='number', required=False,
         min=0, max=100, default=1, example='1',
         hint='weighted 模式下的抽取权重，0 表示不参与'),
    dict(key='tags', label='标签', type='tags', required=False,
         maxItems=12, example='开国;帝王', hint='分号或逗号分隔，便于筛选'),
]


def csv_columns():
    return [f['key'] for f in CHARACTER_FIELDS]


def example_rows():
    """模板里的示例行，字段顺序必须与 csv_columns() 一致。"""
    return [
        {f['key']: f.get('example', '') for f in CHARACTER_FIELDS},
        dict(id='yongle', name='朱棣', order='2', avatar='yongle.png',
             speech='永乐迁都，四海宾服', weight='1', tags='迁都;帝王'),
    ]


def schema_document():
    """交给前端的契约：表单、表格、校验提示全部由此生成。"""
    return {
        'version': 1,
        'packFields': PACK_FIELDS,
        'characterFields': CHARACTER_FIELDS,
        'modes': MODES,
        'csvColumns': csv_columns(),
        'idPattern': ID_PATTERN,
        'exampleRows': example_rows(),
    }


def _err(line, field, message):
    return {'line': line, 'field': field, 'message': message}


def _coerce(raw, field, line):
    """把 CSV 字符串或 JSON 值收敛成规范类型；返回 (值, 错误列表)。"""
    key, typ = field['key'], field['type']
    key_label = field['label']
    blank = raw is None or (isinstance(raw, str) and not raw.strip())
    if blank:
        if field.get('required'):
            return None, [_err(line, key, f'{key_label}为必填项')]
        return field.get('default'), []

    if typ == 'integer' or typ == 'number':
        try:
            num = float(str(raw).strip())
        except (TypeError, ValueError):
            return None, [_err(line, key, f'{key_label}必须是数字')]
        if typ == 'integer':
            if not float(num).is_integer():
                return None, [_err(line, key, f'{key_label}必须是整数')]
            num = int(num)
        if 'min' in field and num < field['min']:
            return None, [_err(line, key, f'{key_label}不能小于 {field["min"]}')]
        if 'max' in field and num > field['max']:
            return None, [_err(line, key, f'{key_label}不能大于 {field["max"]}')]
        return num, []

    if typ == 'boolean':
        text = str(raw).strip().lower()
        if text in ('true', '1', 'yes', 'on', '是'):
            return True, []
        if text in ('false', '0', 'no', 'off', '否'):
            return False, []
        return None, [_err(line, key, f'{key_label}只能是 true / false')]

    if typ == 'enum':
        text = str(raw).strip()
        if text not in field['values']:
            return None, [_err(line, key,
                               f'{key_label}只能是 {" / ".join(field["values"])}')]
        return text, []

    if typ == 'tags':
        parts = [x.strip() for x in re.split(r'[;,，、]', str(raw)) if x.strip()]
        if len(parts) > field.get('maxItems', 12):
            return None, [_err(line, key,
                               f'{key_label}最多 {field["maxItems"]} 个')]
        return parts, []

    text = str(raw).strip()
    if 'maxLength' in field and len(text) > field['maxLength']:
        return None, [_err(line, key,
                           f'{key_label}不能超过 {field["maxLength"]} 个字符')]
    if field.get('pattern') and not _ID_RE.fullmatch(text):
        return None, [_err(line, key,
                           f'{key_label}格式不符：只允许小写字母、数字、_ 和 -')]
    if typ == 'media':
        if _UNSAFE_FILENAME_RE.search(text):
            return None, [_err(line, key, f'{key_label}含有非法路径字符')]
        if text in ('.', '..') or text.startswith('.'):
            return None, [_err(line, key, f'{key_label}不是合法文件名')]
    return text, []


def validate_character(row, line=0, seen_ids=None):
    """校验单行人物数据，返回 (规范化后的 dict 或 None, 错误列表)。"""
    if not isinstance(row, dict):
        return None, [_err(line, '', '该行不是对象')]
    errors, out = [], {}
    # 额外的列直接忽略，不判错：用户常在模板右侧留备注列，不该因此整批导入失败。
    for field in CHARACTER_FIELDS:
        value, field_errors = _coerce(row.get(field['key']), field, line)
        errors.extend(field_errors)
        if value is not None:
            out[field['key']] = value
    if seen_ids is not None and out.get('id'):
        if out['id'] in seen_ids:
            errors.append(_err(line, 'id', f'唯一标识重复：{out["id"]}'))
        seen_ids.add(out['id'])
    return (None if errors else out), errors


def validate_pack(data, line_offset=0):
    """校验完整内容包（含 characters），返回 (规范化后的 dict 或 None, 错误列表)。"""
    if not isinstance(data, dict):
        return None, [_err(line_offset, '', '内容包必须是对象')]
    errors, out = [], {}
    for field in PACK_FIELDS:
        value, field_errors = _coerce(data.get(field['key']), field, line_offset)
        errors.extend(field_errors)
        if value is not None:
            out[field['key']] = value

    rows = data.get('characters')
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        errors.append(_err(line_offset, 'characters', 'characters 必须是数组'))
        rows = []

    seen, characters = set(), []
    for index, row in enumerate(rows):
        cleaned, row_errors = validate_character(
            row, line_offset + index + 1, seen)
        errors.extend(row_errors)
        if cleaned is not None:
            characters.append(cleaned)
    # sorted 是稳定的：order 相同的行保持导入时的先后，无需二次索引。
    out['characters'] = sorted(characters, key=lambda c: c.get('order', 0))
    return (None if errors else out), errors
