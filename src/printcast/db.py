"""本机 SQLite 数据层：所有控制台数据的唯一运行时来源（source of truth）。

设计约束（与项目其它模块一致）：
- **纯 stdlib、零第三方依赖**：只用 sqlite3 + json，WAL 模式，短连接，不引入 ORM；
- **JSON 文件不是被删除，而是降级为「分发 / 备份 / 手改」格式**：首次启动把
  data/packs/*.json、settings.json、media/index.json、audit.jsonl 幂等迁移进库；
  `--db-export` 可以把库内容重新导出成同样结构的 JSON，便于 git 分发与人工检查；
- **并发安全**：所有写操作走 `BEGIN IMMEDIATE` 事务，取代原先 JSON 文件的
  读-改-写竞态（两个请求同时上传图片曾会互相覆盖 index.json）；
- **路径动态计算**：`db_path()` 每次读 config.DATA_DIR，测试 monkeypatch 后立即生效。

表结构：
  meta            schema 版本与迁移记录
  packs           内容包主表；doc 保存 schema.validate_pack 后的权威快照
  characters      packs.characters 的关系化投影，供统计与检索（写包时同步重建）
  media           上传图片的元数据（二进制仍在 data/media/，由 /media/<id> 静态服务提供）
  settings        单行 JSON 文档（设置本身是嵌套结构，深合并由 settings.py 在事务内完成）
  audit           本机操作日志，一行一条，带索引，容量上限由 audit.py 执行
  runtime_state   广播进度等重启不该丢的运行时状态
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA_VERSION = 1
DB_FILENAME = 'printcast.db'

_INITIALIZED = set()
_INIT_LOCK = threading.Lock()


def db_path() -> Path:
    return Path(config.DATA_DIR) / DB_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout = 10000')
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


@contextmanager
def connect():
    """只读连接（用完自动关闭）。"""
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction():
    """写事务：BEGIN IMMEDIATE 让并发写串行化，异常自动回滚。"""
    conn = _connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS packs (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    mode            TEXT NOT NULL DEFAULT 'sequence',
    loop            INTEGER NOT NULL DEFAULT 0,
    description     TEXT NOT NULL DEFAULT '',
    updated         TEXT NOT NULL,
    character_count INTEGER NOT NULL DEFAULT 0,
    doc             TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS characters (
    pack_id TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
    id      TEXT NOT NULL,
    name    TEXT NOT NULL,
    ord     INTEGER NOT NULL DEFAULT 0,
    speech  TEXT NOT NULL DEFAULT '',
    avatar  TEXT NOT NULL DEFAULT '',
    weight  REAL NOT NULL DEFAULT 1,
    tags    TEXT NOT NULL DEFAULT '[]',
    seq     INTEGER NOT NULL,
    PRIMARY KEY (pack_id, id)
);
CREATE INDEX IF NOT EXISTS idx_characters_pack ON characters(pack_id, seq);
CREATE TABLE IF NOT EXISTS media (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL DEFAULT '',
    size    INTEGER NOT NULL DEFAULT 0,
    mime    TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL,
    url     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    id      INTEGER PRIMARY KEY CHECK (id = 1),
    doc     TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id     TEXT PRIMARY KEY,
    at     TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    ok     INTEGER NOT NULL DEFAULT 1,
    status INTEGER NOT NULL DEFAULT 200,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit(at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit(action);
CREATE TABLE IF NOT EXISTS runtime_state (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL,
    updated TEXT NOT NULL
);
"""


def ensure_db():
    """建库 + 首次迁移。进程内按路径缓存，文件被删掉时会自动重建。"""
    path = db_path()
    key = str(path.resolve())
    with _INIT_LOCK:
        if key in _INITIALIZED and path.is_file():
            return
        conn = _connect()
        try:
            # WAL 是数据库级持久设置，只在初始化时设定一次。
            conn.execute('PRAGMA journal_mode = WAL')
            conn.executescript(_DDL)
            conn.execute('INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)',
                         ('schemaVersion', str(SCHEMA_VERSION)))
            conn.commit()
        finally:
            conn.close()
        # 只在 meta 里没有迁移记录时执行，保证重复启动幂等。
        with connect() as conn:
            migrated = conn.execute(
                "SELECT value FROM meta WHERE key = 'migratedFrom'").fetchone()
        if migrated is None:
            summary = migrate_from_json()
            with transaction() as conn:
                conn.execute('INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)',
                             ('migratedFrom', _json(summary)))
                conn.execute('INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)',
                             ('migratedAt', _now()))
        _INITIALIZED.add(key)


# ——— 内容包 ———

def _pack_row(pack: dict):
    chars = pack.get('characters') or []
    return (
        pack['id'], str(pack.get('title') or pack['id']),
        str(pack.get('mode') or 'sequence'), 1 if pack.get('loop') else 0,
        str(pack.get('description') or ''), str(pack.get('updated') or ''),
        len(chars), _json(pack),
    )


def _pack_char_rows(pack: dict):
    rows = []
    for seq, c in enumerate(pack.get('characters') or []):
        rows.append((
            pack['id'], str(c.get('id') or ''), str(c.get('name') or ''),
            int(c.get('order') or 0), str(c.get('speech') or ''),
            str(c.get('avatar') or ''), float(c.get('weight') or 0),
            _json(c.get('tags') or []), seq,
        ))
    return rows


def save_pack(pack: dict) -> dict:
    """UPSERT 一个内容包，doc 与 characters 投影在同一事务里同步。"""
    ensure_db()
    with transaction() as conn:
        conn.execute('INSERT OR REPLACE INTO packs'
                     '(id,title,mode,loop,description,updated,character_count,doc)'
                     ' VALUES (?,?,?,?,?,?,?,?)', _pack_row(pack))
        conn.execute('DELETE FROM characters WHERE pack_id = ?', (pack['id'],))
        conn.executemany(
            'INSERT INTO characters(pack_id,id,name,ord,speech,avatar,weight,tags,seq)'
            ' VALUES (?,?,?,?,?,?,?,?,?)', _pack_char_rows(pack))
    return pack


def get_pack(pack_id: str):
    ensure_db()
    with connect() as conn:
        row = conn.execute('SELECT doc FROM packs WHERE id = ?', (pack_id,)).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row['doc'])
    except ValueError:
        return None


def list_packs() -> list:
    ensure_db()
    with connect() as conn:
        rows = conn.execute(
            'SELECT id,title,mode,updated,character_count FROM packs ORDER BY id').fetchall()
    return [{'id': r['id'], 'title': r['title'], 'mode': r['mode'],
             'count': r['character_count'], 'updated': r['updated']} for r in rows]


def delete_pack(pack_id: str) -> bool:
    ensure_db()
    with transaction() as conn:
        cur = conn.execute('DELETE FROM packs WHERE id = ?', (pack_id,))
        deleted = cur.rowcount > 0
        if deleted:
            conn.execute('DELETE FROM characters WHERE pack_id = ?', (pack_id,))
    return deleted


# ——— 媒体元数据（二进制仍在磁盘）———

def save_media_record(rec: dict) -> dict:
    ensure_db()
    with transaction() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO media(id,name,size,mime,created,url)'
            ' VALUES (?,?,?,?,?,?)',
            (rec['id'], str(rec.get('name') or ''), int(rec.get('size') or 0),
             str(rec.get('mime') or ''), str(rec.get('created') or ''),
             str(rec.get('url') or '')))
    return rec


def list_media() -> list:
    ensure_db()
    with connect() as conn:
        rows = conn.execute('SELECT * FROM media ORDER BY created DESC, id DESC').fetchall()
    return [dict(r) for r in rows]


def get_media_info(media_id: str):
    ensure_db()
    with connect() as conn:
        row = conn.execute('SELECT * FROM media WHERE id = ?', (media_id,)).fetchone()
    return dict(row) if row else None


def delete_media_record(media_id: str) -> bool:
    ensure_db()
    with transaction() as conn:
        cur = conn.execute('DELETE FROM media WHERE id = ?', (media_id,))
        return cur.rowcount > 0


# ——— 设置（单行 JSON 文档）———

def get_settings_doc():
    ensure_db()
    with connect() as conn:
        row = conn.execute('SELECT doc FROM settings WHERE id = 1').fetchone()
    if row is None:
        return None
    try:
        return json.loads(row['doc'])
    except ValueError:
        return None


def put_settings_doc(doc: dict) -> dict:
    ensure_db()
    with transaction() as conn:
        conn.execute('INSERT OR REPLACE INTO settings(id,doc,updated) VALUES (1,?,?)',
                     (_json(doc), _now()))
    return doc


def delete_settings_doc():
    ensure_db()
    with transaction() as conn:
        conn.execute('DELETE FROM settings WHERE id = 1')


def update_settings(mutator) -> dict:
    """在单个写事务里完成「读旧值 → mutator(旧值) → 写回」，消除并发 PUT 丢更新。"""
    ensure_db()
    conn = _connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT doc FROM settings WHERE id = 1').fetchone()
        current = None
        if row is not None:
            try:
                current = json.loads(row['doc'])
                if not isinstance(current, dict):
                    current = None
            except ValueError:
                current = None
        merged = mutator(current)
        conn.execute('INSERT OR REPLACE INTO settings(id,doc,updated) VALUES (1,?,?)',
                     (_json(merged), _now()))
        conn.commit()
        return merged
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ——— 操作日志 ———

def audit_insert(entry: dict, keep_after_clear=False, trim_to=None):
    """插入一条日志；keep_after_clear / 容量裁剪都在同一事务内完成，避免竞态。"""
    ensure_db()
    with transaction() as conn:
        if keep_after_clear:
            conn.execute('DELETE FROM audit')
        conn.execute(
            'INSERT OR REPLACE INTO audit(id,at,action,target,ok,status,detail)'
            ' VALUES (?,?,?,?,?,?,?)',
            (entry['id'], entry['at'], entry['action'], entry['target'],
             1 if entry['ok'] else 0, int(entry['status']), entry['detail']))
        if trim_to:
            conn.execute(
                'DELETE FROM audit WHERE rowid IN ('
                '  SELECT rowid FROM audit ORDER BY at DESC, rowid DESC LIMIT -1 OFFSET ?)',
                (max(1, int(trim_to)),))


def audit_list(limit=100, action='', q='', only_failed=False) -> list:
    ensure_db()
    try:
        limit = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        limit = 100
    where, args = [], []
    if action and action != 'all':
        where.append('action = ?')
        args.append(action)
    if only_failed:
        where.append('ok = 0')
    if q:
        needle = '%' + str(q).lower() + '%'
        where.append('(lower(action) LIKE ? OR lower(target) LIKE ? OR lower(detail) LIKE ?)')
        args += [needle, needle, needle]
    sql = 'SELECT * FROM audit'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY at DESC, rowid DESC LIMIT ?'
    args.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [{'id': r['id'], 'at': r['at'], 'action': r['action'],
             'target': r['target'], 'ok': bool(r['ok']),
             'status': r['status'], 'detail': r['detail']} for r in rows]


def audit_stats() -> dict:
    ensure_db()
    with connect() as conn:
        row = conn.execute(
            'SELECT COUNT(*) AS total, COALESCE(SUM(ok),0) AS ok,'
            ' MAX(at) AS last_at FROM audit').fetchone()
        actions = [r['action'] for r in conn.execute(
            'SELECT DISTINCT action FROM audit ORDER BY action').fetchall()]
    total = int(row['total'] or 0)
    ok = int(row['ok'] or 0)
    return {'total': total, 'ok': ok, 'failed': total - ok,
            'lastAt': row['last_at'], 'actions': actions}


def audit_clear() -> bool:
    ensure_db()
    with transaction() as conn:
        conn.execute('DELETE FROM audit')
    return True


def audit_trim(max_entries=500):
    """只保留最新 max_entries 条，SQL 一次完成，避免 JSONL 时代的全量读写放大。"""
    ensure_db()
    with transaction() as conn:
        conn.execute(
            'DELETE FROM audit WHERE rowid IN ('
            '  SELECT rowid FROM audit ORDER BY at DESC, rowid DESC LIMIT -1 OFFSET ?)',
            (max(1, int(max_entries)),))


# ——— 运行时状态（广播进度等）———

def get_state(key: str):
    ensure_db()
    with connect() as conn:
        row = conn.execute('SELECT value FROM runtime_state WHERE key = ?', (key,)).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row['value'])
    except ValueError:
        return None


def set_state(key: str, value) -> None:
    ensure_db()
    with transaction() as conn:
        conn.execute('INSERT OR REPLACE INTO runtime_state(key,value,updated) VALUES (?,?,?)',
                     (key, _json(value), _now()))


def del_state(key: str) -> None:
    ensure_db()
    with transaction() as conn:
        conn.execute('DELETE FROM runtime_state WHERE key = ?', (key,))


# ——— JSON ⇄ DB 迁移 / 导出 ———

def _read_json(path: Path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data
    except (OSError, ValueError, UnicodeError):
        return None


def migrate_from_json() -> dict:
    """首次启动把现有 JSON 运行数据导入 DB（INSERT OR IGNORE，绝不覆盖已有库内容）。"""
    base = Path(config.DATA_DIR)
    summary = {'packs': 0, 'characters': 0, 'settings': 0, 'media': 0, 'audit': 0}
    pack_docs = []
    for path in sorted((base / 'packs').glob('*.json')):
        if path.name == 'index.json':
            continue
        doc = _read_json(path)
        if not isinstance(doc, dict) or not isinstance(doc.get('id'), str):
            continue
        pack_docs.append(doc)
    settings_doc = _read_json(base / 'settings.json')
    media_index = _read_json(base / 'media' / 'index.json')
    audit_lines = []
    log = base / 'audit.jsonl'
    if log.is_file():
        try:
            audit_lines = log.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeError):
            audit_lines = []

    with transaction() as conn:
        for doc in pack_docs:
            cur = conn.execute('INSERT OR IGNORE INTO packs'
                               '(id,title,mode,loop,description,updated,character_count,doc)'
                               ' VALUES (?,?,?,?,?,?,?,?)', _pack_row(doc))
            if cur.rowcount:
                conn.executemany(
                    'INSERT OR IGNORE INTO characters'
                    '(pack_id,id,name,ord,speech,avatar,weight,tags,seq)'
                    ' VALUES (?,?,?,?,?,?,?,?,?)', _pack_char_rows(doc))
                summary['packs'] += 1
                summary['characters'] += len(doc.get('characters') or [])
        if isinstance(settings_doc, dict):
            cur = conn.execute('INSERT OR IGNORE INTO settings(id,doc,updated) VALUES (1,?,?)',
                               (_json(settings_doc), _now()))
            summary['settings'] = cur.rowcount
        if isinstance(media_index, dict):
            for mid, rec in media_index.items():
                if not isinstance(rec, dict):
                    continue
                cur = conn.execute(
                    'INSERT OR IGNORE INTO media(id,name,size,mime,created,url)'
                    ' VALUES (?,?,?,?,?,?)',
                    (mid, str(rec.get('name') or ''), int(rec.get('size') or 0),
                     str(rec.get('mime') or ''), str(rec.get('created') or ''),
                     str(rec.get('url') or '/media/' + str(mid))))
                summary['media'] += cur.rowcount
        for line in audit_lines:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if not isinstance(item, dict) or not item.get('id'):
                continue
            cur = conn.execute(
                'INSERT OR IGNORE INTO audit(id,at,action,target,ok,status,detail)'
                ' VALUES (?,?,?,?,?,?,?)',
                (str(item['id']), str(item.get('at') or ''), str(item.get('action') or ''),
                 str(item.get('target') or ''), 1 if item.get('ok') else 0,
                 int(item.get('status') or 200), str(item.get('detail') or '')))
            summary['audit'] += cur.rowcount
    return summary


def import_json(overwrite=False) -> dict:
    """把 data/ 下的 JSON 重新导入 DB（overwrite=True 时以文件内容覆盖同 id 记录）。"""
    ensure_db()
    base = Path(config.DATA_DIR)
    result = {'packs': 0, 'skipped': 0, 'settings': 0, 'media': 0, 'errors': []}
    for path in sorted((base / 'packs').glob('*.json')):
        if path.name == 'index.json':
            continue
        doc = _read_json(path)
        if not isinstance(doc, dict) or not isinstance(doc.get('id'), str):
            result['errors'].append('%s: 不是合法内容包对象' % path.name)
            continue
        if not overwrite and get_pack(doc['id']) is not None:
            result['skipped'] += 1
            continue
        try:
            save_pack(doc)
            result['packs'] += 1
        except Exception as exc:  # noqa: BLE001 — 单文件失败不阻断其余
            result['errors'].append('%s: %s' % (path.name, exc))
    doc = _read_json(base / 'settings.json')
    if isinstance(doc, dict) and (overwrite or get_settings_doc() is None):
        put_settings_doc(doc)
        result['settings'] = 1
    index = _read_json(base / 'media' / 'index.json')
    if isinstance(index, dict):
        for mid, rec in index.items():
            if not isinstance(rec, dict):
                continue
            if not overwrite and get_media_info(mid):
                continue
            save_media_record({
                'id': mid, 'name': rec.get('name') or '', 'size': rec.get('size') or 0,
                'mime': rec.get('mime') or '', 'created': rec.get('created') or _now(),
                'url': rec.get('url') or '/media/' + str(mid),
            })
            result['media'] += 1
    return result


def export_json(only_ids=None, write_meta=True) -> dict:
    """把库内容导出成与旧版完全同构的 JSON 文件（分发 / 备份 / git 可比对）。

    only_ids=None 导出全部内容包；给定列表只导出这些包；空列表表示不写包文件。
    write_meta 控制是否同步 settings.json 与 media/index.json 两份镜像。
    """
    ensure_db()
    base = Path(config.DATA_DIR)
    packs_dir = base / 'packs'
    media_dir = base / 'media'
    packs_dir.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)
    ids = set(only_ids) if only_ids is not None else None
    written = []
    with connect() as conn:
        rows = conn.execute('SELECT id,doc FROM packs ORDER BY id').fetchall()
        media_rows = conn.execute('SELECT * FROM media ORDER BY id').fetchall()
        settings_row = conn.execute('SELECT doc FROM settings WHERE id = 1').fetchone()
    def pretty(raw_json):
        """库里存紧凑 JSON（省空间），导出成与人手可改的文件一致的缩进格式。"""
        try:
            return json.dumps(json.loads(raw_json), ensure_ascii=False, indent=2)
        except (ValueError, TypeError):
            return raw_json

    for row in rows:
        if ids is not None and row['id'] not in ids:
            continue
        path = packs_dir / (row['id'] + '.json')
        _atomic_text(path, pretty(row['doc']))
        written.append(row['id'])
    if write_meta:
        if settings_row is not None:
            _atomic_text(base / 'settings.json', pretty(settings_row['doc']))
        index = {r['id']: {k: r[k] for k in ('id', 'name', 'size', 'mime', 'created', 'url')}
                 for r in media_rows}
        _atomic_text(media_dir / 'index.json',
                     json.dumps(index, ensure_ascii=False, indent=2))
    return {'packs': written, 'settings': settings_row is not None,
            'media': len(media_rows)}


def _atomic_text(path: Path, text: str):
    tmp = path.with_name(path.name + '.tmp-' + os.urandom(4).hex())
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(text if text.endswith('\n') else text + '\n')
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# ——— 状态与自检 ———

def stats() -> dict:
    ensure_db()
    path = db_path()
    with connect() as conn:
        tables = {}
        for name in ('packs', 'characters', 'media', 'settings', 'audit', 'runtime_state'):
            tables[name] = int(conn.execute(
                'SELECT COUNT(*) FROM ' + name).fetchone()[0])
        integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
        version = conn.execute(
            "SELECT value FROM meta WHERE key = 'schemaVersion'").fetchone()
        migrated = conn.execute(
            "SELECT value FROM meta WHERE key = 'migratedFrom'").fetchone()
        migrated_at = conn.execute(
            "SELECT value FROM meta WHERE key = 'migratedAt'").fetchone()
    try:
        rel = str(path.relative_to(config.ROOT))
    except ValueError:
        rel = str(path)
    return {
        'backend': 'sqlite',
        'schemaVersion': int(version['value']) if version else SCHEMA_VERSION,
        'dbPath': rel,
        'sizeBytes': path.stat().st_size if path.is_file() else 0,
        'tables': tables,
        'integrity': integrity,
        'migratedFrom': json.loads(migrated['value']) if migrated else None,
        'migratedAt': migrated_at['value'] if migrated_at else None,
    }


def verify() -> dict:
    """完整性自检：SQLite 层 + 内容包 doc/投影一致性 + 设置文档可解析。"""
    info = stats()
    errors = []
    checks = []
    if info['integrity'] != 'ok':
        errors.append('PRAGMA integrity_check: %s' % info['integrity'])
    checks.append('integrity_check=%s' % info['integrity'])
    with connect() as conn:
        fk = conn.execute('PRAGMA foreign_key_check').fetchall()
        if fk:
            errors.append('外键不一致：%d 行' % len(fk))
        checks.append('foreign_key_check=%d' % len(fk))
        bad = 0
        for row in conn.execute('SELECT id,doc,character_count FROM packs'):
            try:
                doc = json.loads(row['doc'])
            except ValueError:
                bad += 1
                errors.append('内容包 %s 的 doc 不是合法 JSON' % row['id'])
                continue
            if doc.get('id') != row['id']:
                bad += 1
                errors.append('内容包 %s 的 doc.id 与主键不一致' % row['id'])
            if len(doc.get('characters') or []) != row['character_count']:
                bad += 1
                errors.append('内容包 %s 的人物计数不一致' % row['id'])
            projected = conn.execute(
                'SELECT COUNT(*) FROM characters WHERE pack_id = ?', (row['id'],)).fetchone()[0]
            if projected != row['character_count']:
                bad += 1
                errors.append('内容包 %s 的 characters 投影缺失' % row['id'])
        checks.append('packs_checked=%d' % info['tables']['packs'])
        checks.append('packs_bad=%d' % bad)
        s = conn.execute('SELECT doc FROM settings WHERE id = 1').fetchone()
        if s is not None:
            try:
                parsed = json.loads(s['doc'])
                if not isinstance(parsed, dict):
                    errors.append('设置文档不是 JSON 对象')
            except ValueError:
                errors.append('设置文档不是合法 JSON')
            checks.append('settings_doc=checked')
    return {'ok': not errors, 'checks': checks, 'errors': errors, 'stats': info}
