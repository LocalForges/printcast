"""本机操作日志：控制台写操作的可回溯记录。

边界：只有控制台（Studio + 本机 API）会产生写操作；展示端全程只读。
因此这份日志只记录服务端实际执行的动作，不依赖浏览器上报，也不会因为
展示页刷新、3D 渲染心跳或信令轮询而膨胀。

持久化已从 JSON Lines 迁到 SQLite（db.py）：
- 一条日志一行记录，带索引；筛选（动作 / 关键词 / 只看失败）在 SQL 里完成，
  不再受「先取 100 条再前端过滤」的窗口截断影响；
- 容量上限用一条 DELETE 完成，取代每次写入都全量重写文件；
- 「清空并留一条 audit.clear」在同一事务里原子完成，杜绝并发写插入破坏可回溯性；
- 写入失败由调用方统一兜底，绝不影响业务响应。

实现约束：纯 stdlib、零第三方依赖；不记请求体（避免把内容包、图片二进制或
用户文案写进日志），所有字段做长度截断。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config, db

MAX_ENTRIES = 500


def log_path() -> Path:
    """旧版 JSONL 路径（仅用于首次迁移与人工检查；库才是运行时数据源）。"""
    return config.DATA_DIR / 'audit.jsonl'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _clip(value, size=160) -> str:
    return str(value if value is not None else '')[:size]


def _entry(action, target, ok, detail, status) -> dict:
    return {
        'id': uuid.uuid4().hex[:12],
        'at': _now(),
        'action': _clip(action, 60),
        'target': _clip(target, 120),
        'ok': bool(ok),
        'status': int(status),
        'detail': _clip(detail, 240),
    }


def record(action, target='', ok=True, detail='', status=200) -> dict:
    """追加一条写操作记录（含容量裁剪，单事务），返回该条记录。"""
    entry = _entry(action, target, ok, detail, status)
    db.audit_insert(entry, trim_to=MAX_ENTRIES)
    return entry


def list_entries(limit=100, action='', q='', only_failed=False) -> list:
    """倒序（最新在前）返回记录，支持动作 / 关键词 / 只看失败组合过滤。"""
    return db.audit_list(limit=limit, action=action, q=q, only_failed=only_failed)


def stats() -> dict:
    """全量统计（不受 limit 影响）；lastAt 取最新一条时间。"""
    out = db.audit_stats()
    out['limit'] = MAX_ENTRIES
    return out


def clear() -> bool:
    """清空日志。HTTP 端点请用 clear_with_record()，保证「清空留痕」原子。"""
    return db.audit_clear()


def clear_with_record(detail='清空操作日志', status=200) -> dict:
    """原子完成「清空 + 补记一条 audit.clear」，中间不会插入任何并发写。"""
    entry = _entry('audit.clear', '', True, detail, status)
    db.audit_insert(entry, keep_after_clear=True)
    return entry
