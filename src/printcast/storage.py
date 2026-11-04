"""内容包与媒体资产的持久化适配层。

架构（数据落库后）：
- **SQLite 库（db.py）是运行时唯一数据源**。所有 CRUD、索引、并发安全都在事务里完成，
  取代了早期 JSON 文件的读-改-写（并发上传曾互相覆盖 index.json）。
- **JSON 文件降级为「分发 / 备份 / 手改」格式**：每次写库后尽力同步一份同构 JSON
  到 data/packs/、data/media/index.json，便于 git 分发、人工比对与回滚；镜像写失败
  不影响业务响应。首次启动由 db.migrate_from_json() 把已有 JSON 幂等导入库。
- 图片二进制仍以文件形式留在 data/media/，由 /media/<id> 静态服务直接提供；
  入库的是元数据（id / 名称 / 大小 / MIME / 时间 / URL）。
- 所有用户可控名称经过白名单，路径写盘前再校验 resolve 后仍在基目录内。

对外函数签名与返回形状与 JSON 时代完全一致，api / scheduler / 工作台无需感知后端变化。
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config, db
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


def _inside(base: Path, target: Path):
    """确认 target 解析后仍位于 base 之内。"""
    try:
        return target.resolve().is_relative_to(base.resolve())
    except (ValueError, OSError):
        return False


def _mirror(only_ids=None, write_meta=True):
    """尽力把库内容同步成 JSON 备份；镜像失败绝不影响业务响应。"""
    try:
        return db.export_json(only_ids=only_ids, write_meta=write_meta)
    except Exception:  # noqa: BLE001 — 备份是 best-effort
        return None


def valid_pack_id(raw):
    return bool(_SAFE_ID.fullmatch(str(raw or '')))


# ——— 内容包 ———

def pack_path(pack_id):
    """返回该内容包的 JSON 备份路径（仍做与旧版一致的路径校验）。"""
    if not valid_pack_id(pack_id):
        raise ValueError('非法的内容包 ID')
    path = config.packs_dir() / (pack_id + '.json')
    if not _inside(config.packs_dir(), path):
        raise ValueError('非法的内容包路径')
    return path


def list_packs():
    """返回摘要列表（走索引列，不反序列化整包）。"""
    return db.list_packs()


def get_pack(pack_id):
    if not valid_pack_id(pack_id):
        return None
    return db.get_pack(pack_id)


def save_pack(pack):
    """写入内容包并返回带 updated 时间戳的同一对象；doc 与人物投影在同一事务里同步。"""
    pack = dict(pack)
    if not valid_pack_id(pack.get('id')):
        raise ValueError('非法的内容包 ID')
    pack['updated'] = _now()
    db.save_pack(pack)
    _mirror(only_ids=[pack['id']], write_meta=False)
    return pack


def delete_pack(pack_id):
    """删除库内记录并同步清理 JSON 备份；整包删除是单事务，不会被并发写复活。"""
    if not valid_pack_id(pack_id):
        return False
    deleted = db.delete_pack(pack_id)
    if deleted:
        try:
            path = pack_path(pack_id)
            if path.is_file():
                path.unlink()
        except OSError:
            pass
    return deleted


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

    record = {
        'id': media_id,
        'name': str(original_name or '')[:255],
        'size': len(data),
        'mime': mime,
        'created': _now(),
        'url': '/media/' + media_id,
    }
    db.save_media_record(record)
    _mirror(only_ids=[])
    return record


def list_media():
    return db.list_media()


def get_media_info(media_id):
    if not _MEDIA_ID.fullmatch(str(media_id or '')):
        return None
    return db.get_media_info(media_id)


def media_path(media_id):
    if not _MEDIA_ID.fullmatch(str(media_id or '')):
        return None
    path = config.media_dir() / media_id
    if not _inside(config.media_dir(), path):
        return None
    if not path.is_file() or db.get_media_info(media_id) is None:
        return None
    return path


def delete_media(media_id):
    if not _MEDIA_ID.fullmatch(str(media_id or '')):
        return False
    path = media_path(media_id)
    if not path:
        return False
    try:
        path.unlink()
    except OSError:
        return False
    deleted = db.delete_media_record(media_id)
    _mirror(only_ids=[])
    return deleted
