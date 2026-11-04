"""内容包与媒体资产的持久化。

设计约束：
- 纯 stdlib，零第三方依赖；JSON 文件 + 原子写（临时文件 + os.replace），
  内容包可以直接 git 分发、手改、当产品交付，单机单人无需数据库事务。
- 所有用户可控的名称都经过白名单，且写盘前再校验 resolve 后的路径仍在基目录内，
  杜绝 ../ 穿越与绝对路径注入。
- 路径通过 config.packs_dir() / media_dir() 动态取得，测试可 monkeypatch DATA_DIR。
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .schema import ID_PATTERN

_SAFE_ID = re.compile(ID_PATTERN)
_MEDIA_ID = re.compile(r'^[a-f0-9]{12}\.(?:png|jpe?g|webp)$')
_MEDIA_INDEX = 'index.json'


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex[:8])
    with open(tmp, 'wb') as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')


def _inside(base: Path, target: Path):
    """确认 target 解析后仍位于 base 之内。"""
    try:
        return target.resolve().is_relative_to(base.resolve())
    except (ValueError, OSError):
        return False


def valid_pack_id(raw):
    return bool(_SAFE_ID.fullmatch(str(raw or '')))


# ——— 内容包 ———

def pack_path(pack_id):
    if not valid_pack_id(pack_id):
        raise ValueError('非法的内容包 ID')
    path = config.packs_dir() / (pack_id + '.json')
    if not _inside(config.packs_dir(), path):
        raise ValueError('非法的内容包路径')
    return path


def list_packs():
    """返回摘要列表（不读全文，避免大包拖慢列表接口）。"""
    items = []
    for path in sorted(config.packs_dir().glob('*.json')):
        if path.name == _MEDIA_INDEX:
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        items.append({
            'id': data.get('id', path.stem),
            'title': data.get('title', path.stem),
            'mode': data.get('mode', 'sequence'),
            'count': len(data.get('characters') or []),
            'updated': data.get('updated', ''),
        })
    return items


def get_pack(pack_id):
    path = pack_path(pack_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def save_pack(pack):
    """写入内容包，返回带 updated 时间戳的同一对象。"""
    pack = dict(pack)
    pack['updated'] = _now()
    _atomic_write(pack_path(pack['id']), _json_bytes(pack))
    return pack


def delete_pack(pack_id):
    path = pack_path(pack_id)
    if not path.is_file():
        return False
    path.unlink()
    return True


# ——— 媒体资产 ———

def sniff_image(data: bytes):
    """按魔数判定真实图片类型，返回 (mime, ext) 或 None。不信客户端声明。"""
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png', '.png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg', '.jpg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp', '.webp'
    return None


def _index_path():
    return config.media_dir() / _MEDIA_INDEX


def _read_index():
    path = _index_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_index(index):
    _atomic_write(_index_path(), _json_bytes(index))


def save_media(data: bytes, original_name: str, declared_mime: str = ''):
    """保存上传图片，返回媒体记录；失败抛 ValueError（由 api 层转成 400）。"""
    if not data:
        raise ValueError('文件内容为空')
    if len(data) > config.MAX_MEDIA_BYTES:
        raise ValueError('图片超过 %d MB 上限' % (config.MAX_MEDIA_BYTES // 1024 // 1024))
    detected = sniff_image(data)
    if not detected:
        raise ValueError('不是受支持的图片（仅 PNG / JPEG / WebP），或文件头损坏')
    mime, ext = detected
    # 声明的 MIME 若存在且与魔数不符，直接拒绝，避免前端把 SVG/HTML 当图片用。
    declared = (declared_mime or '').split(';')[0].strip().lower()
    if declared and declared not in ('image/png', 'image/jpeg', 'image/webp',
                                     'application/octet-stream'):
        raise ValueError('不支持的 Content-Type：%s' % declared)
    if declared.startswith('image/') and declared != mime:
        raise ValueError('Content-Type 与文件实际格式不一致')

    media_id = uuid.uuid4().hex[:12] + ext
    path = config.media_dir() / media_id
    if not _inside(config.media_dir(), path):
        raise ValueError('非法的媒体路径')
    _atomic_write(path, data)

    index = _read_index()
    index[media_id] = {
        'id': media_id,
        'name': str(original_name or '')[:255],
        'size': len(data),
        'mime': mime,
        'created': _now(),
        'url': '/media/' + media_id,
    }
    _write_index(index)
    return index[media_id]


def list_media():
    index = _read_index()
    return sorted(index.values(), key=lambda x: x.get('created', ''), reverse=True)


def get_media_info(media_id):
    if not _MEDIA_ID.fullmatch(str(media_id or '')):
        return None
    return _read_index().get(media_id)


def media_path(media_id):
    if not _MEDIA_ID.fullmatch(str(media_id or '')):
        return None
    path = config.media_dir() / media_id
    if not _inside(config.media_dir(), path):
        return None
    return path if path.is_file() else None


def delete_media(media_id):
    path = media_path(media_id)
    if not path:
        return False
    path.unlink()
    index = _read_index()
    index.pop(media_id, None)
    _write_index(index)
    return True
