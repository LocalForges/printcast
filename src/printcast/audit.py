"""本机操作日志：控制台写操作的可回溯记录。

边界：只有控制台（Studio + 本机 API）会产生写操作；展示端全程只读。
因此这份日志只记录服务端实际执行的动作，不依赖浏览器上报，也不会因为
展示页刷新、3D 渲染心跳或信令轮询而膨胀。

实现约束（与 storage / settings 一致）：纯 stdlib、零第三方依赖。
- JSON Lines 追加写：单次写操作只落一行，无需重写整份历史；
- 进程内互斥锁：ThreadingHTTPServer 下多个请求并发写不会互相截断；
- 条数上限：超过 MAX_ENTRIES 后裁剪最旧的记录（原子替换），避免无限膨胀；
- 字段截断：只记动作、目标、结果与短说明，绝不落请求体全文（避免把内容包、
  图片二进制或用户文案写进日志）。
- 日志写入失败绝不影响主流程：调用方统一 try/except 兜底。
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config

MAX_ENTRIES = 500
_MAX_LIMIT = 500

_LOCK = threading.Lock()


def log_path() -> Path:
    """路径随 config.DATA_DIR 动态计算，测试可 monkeypatch 到临时目录。"""
    return config.DATA_DIR / 'audit.jsonl'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _clip(value, size=160) -> str:
    return str(value if value is not None else '')[:size]


def _read_lines() -> list:
    path = log_path()
    if not path.is_file():
        return []
    try:
        return path.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeError):
        return []


def _trim_locked():
    """调用时必须已持有 _LOCK。"""
    lines = _read_lines()
    if len(lines) <= MAX_ENTRIES:
        return
    kept = lines[-MAX_ENTRIES:]
    path = log_path()
    tmp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex[:8])
    tmp.write_text('\n'.join(kept) + ('\n' if kept else ''), encoding='utf-8')
    os.replace(tmp, path)


def record(action, target='', ok=True, detail='', status=200) -> dict:
    """追加一条写操作记录，返回该条记录。"""
    entry = {
        'id': uuid.uuid4().hex[:12],
        'at': _now(),
        'action': _clip(action, 60),
        'target': _clip(target, 120),
        'ok': bool(ok),
        'status': int(status),
        'detail': _clip(detail, 240),
    }
    with _LOCK:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + '\n')
        _trim_locked()
    return entry


def _parse(line):
    try:
        data = json.loads(line)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


def list_entries(limit=100, action='', q='') -> list:
    """倒序（最新在前）返回记录，支持按动作与关键词过滤。"""
    try:
        limit = max(1, min(int(limit), _MAX_LIMIT))
    except (TypeError, ValueError):
        limit = 100
    needle = str(q or '').strip().lower()
    action = str(action or '').strip()
    out = []
    for line in reversed(_read_lines()):
        item = _parse(line)
        if item is None:
            continue
        if action and action != 'all' and item.get('action') != action:
            continue
        if needle:
            haystack = ' '.join(str(item.get(k) or '')
                                for k in ('action', 'target', 'detail')).lower()
            if needle not in haystack:
                continue
        out.append(item)
        if len(out) >= limit:
            break
    return out


def stats() -> dict:
    """全量统计（不受 limit 影响），供控制台指标卡使用。"""
    total = ok = failed = 0
    last_at = None
    actions = set()
    for line in _read_lines():
        item = _parse(line)
        if item is None:
            continue
        total += 1
        if item.get('ok'):
            ok += 1
        else:
            failed += 1
        actions.add(str(item.get('action') or ''))
        if last_at is None:
            last_at = item.get('at')
    return {
        'total': total, 'ok': ok, 'failed': failed,
        'lastAt': last_at, 'actions': sorted(a for a in actions if a),
        'limit': MAX_ENTRIES,
    }


def clear() -> bool:
    """清空日志。调用方（server）会在清空后补记一条「清空日志」，保留可回溯性。"""
    with _LOCK:
        path = log_path()
        if not path.exists():
            return True
        try:
            path.unlink()
            return True
        except OSError:
            return False
