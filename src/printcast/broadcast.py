"""出场广播控制器：把调度器的「下一个角色」经 SceneRelay 推给所有浏览器。

放在 server 的闭包里（与 SceneRelay 同一进程实例），因此多标签页 / 多窗口
共享同一份实时进度。控制器本身无网络、无鉴权——鉴权由 server 层把关。

消息类型沿用 relay 的白名单：view-appearance，载荷即 Appearance.to_dict()。
"""
from __future__ import annotations

import time
from typing import List, Optional

from . import storage
from .scheduler import ContentScheduler

_BROADCAST_CLIENT = 'printcast-broadcast'


class BroadcastError(Exception):
    pass


class BroadcastController:
    def __init__(self, relay):
        self.relay = relay
        self.scheduler: Optional[ContentScheduler] = None
        self.pack_ids: List[str] = []
        self.strategy = 'concat'
        self.seed = None
        self.current = None
        self.seq = 0
        self.started_at = None

    # —— 生命周期 ——

    def start(self, pack_ids: List[str], strategy: str = 'concat',
              mode: Optional[str] = None, seed=None, loop: Optional[bool] = None):
        packs = []
        for pid in pack_ids:
            pack = storage.get_pack(pid) if storage.valid_pack_id(pid) else None
            if pack is None:
                raise BroadcastError('内容包不存在：%s' % pid)
            packs.append(pack)
        self.scheduler = ContentScheduler(packs, strategy=strategy, seed=seed)
        if mode:
            if mode not in ('sequence', 'weighted', 'trigger'):
                raise BroadcastError('非法出场模式：%s' % mode)
            self.scheduler.mode = mode
        if loop is not None:
            self.scheduler.loop = bool(loop)
        self.pack_ids = list(pack_ids)
        self.strategy = strategy
        # 固定 seed 是「序列可复现」的凭据：工作台把预演参数原样带回 start，
        # state() 回显 seed，才能核对刚才预演的确实是这一轮真实广播。
        self.seed = seed
        self.current = None
        self.seq = 0
        self.started_at = time.time()
        self.scheduler.reset()
        return self.state()

    def reset(self):
        if self.scheduler is None:
            raise BroadcastError('尚未开始广播，请先 start')
        self.scheduler.reset()
        self.current = None
        self.seq = 0
        return self.state()

    # —— 出场推进 ——

    def next(self):
        ap = self._require().next()
        if ap is None:
            raise BroadcastError('出场序列已结束（如需循环请在 start 时设置 loop=true）')
        return self._publish(ap)

    def trigger(self, char_id: Optional[str] = None):
        ap = self._require().trigger(char_id)
        if ap is None:
            raise BroadcastError('没有可触发的角色' + (f'：{char_id}' if char_id else ''))
        return self._publish(ap)

    def _publish(self, ap):
        self.seq += 1
        self.current = ap.to_dict()
        self.relay.publish(_BROADCAST_CLIENT, {
            'type': 'view-appearance',
            'seq': self.seq,
            'appearance': self.current,
        })
        return self.state()

    def _require(self) -> ContentScheduler:
        if self.scheduler is None:
            raise BroadcastError('尚未开始广播，请先 start')
        return self.scheduler

    # —— 查询 ——

    def state(self) -> dict:
        if self.scheduler is None:
            return {'active': False, 'startedAt': None}
        return {
            'active': True,
            'startedAt': self.started_at,
            'packIds': self.pack_ids,
            'strategy': self.strategy,
            'seed': self.seed,
            'mode': self.scheduler.mode,
            'loop': self.scheduler.loop,
            'seq': self.seq,
            'current': self.current,
            'progress': self.scheduler.progress(),
        }

    def plan(self, count: Optional[int] = None) -> dict:
        """预览出场序列（不改动实时状态）。"""
        sched = self._require()
        return {
            'packIds': self.pack_ids,
            'strategy': self.strategy,
            'mode': sched.mode,
            'loop': sched.loop,
            'appearances': sched.plan(count),
            'progress': sched.progress(),
        }
