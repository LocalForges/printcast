"""出场广播控制器：把调度器的「下一个角色」经 SceneRelay 推给所有浏览器。

放在 server 的闭包里（与 SceneRelay 同一进程实例），因此多标签页 / 多窗口
共享同一份实时进度。控制器本身无网络、无鉴权——鉴权由 server 层把关。

消息类型沿用 relay 的白名单：view-appearance，载荷即 Appearance.to_dict()。

状态持久化：每次 start / next / trigger / reset 后把配置 + 进度 + 调度器游标
写入 db.runtime_state；服务重启时自动恢复，避免「重启即归零、固定 seed 失效」。
所有状态变更都在一把可重入锁内完成，防止两个标签页同时点「下一位」撕裂状态。
"""
from __future__ import annotations

import sys
import threading
import time
from typing import List, Optional

from . import db, storage
from .scheduler import ContentScheduler, normalize_seed

_BROADCAST_CLIENT = 'printcast-broadcast'
_STATE_KEY = 'broadcast'


class BroadcastError(Exception):
    pass


class BroadcastController:
    def __init__(self, relay, restore=True):
        self.relay = relay
        self._lock = threading.RLock()
        self.scheduler: Optional[ContentScheduler] = None
        self.pack_ids: List[str] = []
        self.strategy = 'concat'
        self.seed = None
        self.current = None
        self.seq = 0
        self.started_at = None
        # 自动播放（定时器推进）运行态。
        self.playing = False
        self.interval_ms = 4000
        self._play_timer = None
        self._play_gen = 0
        if restore:
            self.restore()

    # —— 生命周期 ——

    def start(self, pack_ids: List[str], strategy: str = 'concat',
              mode: Optional[str] = None, seed=None, loop: Optional[bool] = None):
        with self._lock:
            packs = []
            for pid in pack_ids:
                pack = storage.get_pack(pid) if storage.valid_pack_id(pid) else None
                if pack is None:
                    raise BroadcastError('内容包不存在：%s' % pid)
                packs.append(pack)
            seed = normalize_seed(seed)
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
            # 重新开播必须先停掉任何在跑的自动播放定时器，避免两个推进源互相打架。
            self.playing = False
            self._play_gen += 1
            if self._play_timer is not None:
                self._play_timer.cancel()
                self._play_timer = None
            self.scheduler.reset()
            self._persist()
            return self.state()

    def reset(self):
        with self._lock:
            if self.scheduler is None:
                raise BroadcastError('尚未开始广播，请先 start')
            # 重置视为完全停播，清掉自动播放定时器。
            self.playing = False
            self._play_gen += 1
            if self._play_timer is not None:
                self._play_timer.cancel()
                self._play_timer = None
            self.scheduler.reset()
            self.current = None
            self.seq = 0
            self._persist()
            return self.state()

    # —— 出场推进 ——

    def next(self):
        with self._lock:
            ap = self._require().next()
            if ap is None:
                raise BroadcastError('出场序列已结束（如需循环请在 start 时设置 loop=true）')
            return self._publish(ap)

    def trigger(self, char_id: Optional[str] = None):
        with self._lock:
            ap = self._require().trigger(char_id)
            if ap is None:
                raise BroadcastError('没有可触发的角色' + (f'：{char_id}' if char_id else ''))
            return self._publish(ap)

    # —— 自动播放（定时器推进）——
    # 展示端只读，必须有人持续「推进下一个」画面才会动。自动播放用一个守护 Timer
    # 线程按 interval_ms 反复调用 _step()，让开播后无需手动点击也能连续出场。
    # _play_gen 是代次令牌：play/pause/start/reset 都让它自增并使旧定时器失效，
    # 避免暂停后仍有滞留的 tick 重新挂起播放（竞态导致「暂停即续播」）。

    def play(self, interval_ms=None, loop=None):
        with self._lock:
            if self.scheduler is None:
                raise BroadcastError('尚未开始广播，请先 start')
            if interval_ms is not None:
                try:
                    iv = int(interval_ms)
                except (TypeError, ValueError):
                    raise BroadcastError('intervalMs 必须是整数（毫秒）')
                if iv < 200 or iv > 60000:
                    raise BroadcastError('intervalMs 需在 200–60000 毫秒之间')
                self.interval_ms = iv
            if loop is not None:
                self.scheduler.loop = bool(loop)
            self.playing = True
            self._persist()
        self._arm_timer()
        return self.state()

    def pause(self):
        with self._lock:
            was_playing = self.playing
            self.playing = False
            self._play_gen += 1
            if self._play_timer is not None:
                self._play_timer.cancel()
                self._play_timer = None
            if was_playing:
                self._persist()
        return self.state()

    def _arm_timer(self):
        # 调用方不持有锁。
        self._play_gen += 1
        gen = self._play_gen
        timer = threading.Timer(self.interval_ms / 1000.0, self._tick, args=(gen,))
        timer.daemon = True
        timer.start()
        self._play_timer = timer

    def _tick(self, gen):
        if gen != self._play_gen or not self.playing or self.scheduler is None:
            return
        state = self._step()
        if state is None:
            with self._lock:
                self.playing = False
                self._persist()
            return
        if self.playing and gen == self._play_gen:
            self._arm_timer()

    def _step(self):
        """推进一位并发布；序列结束且非 loop 时返回 None。调用方不持有锁。"""
        with self._lock:
            if self.scheduler is None:
                return None
            ap = self.scheduler.next()
            if ap is None and self.scheduler.loop:
                # 兜底：极少数调度器在 loop 边界返回 None 的实现，这里续播一次。
                self.scheduler.reset()
                ap = self.scheduler.next()
            if ap is None:
                return None
            return self._publish(ap)

    def _publish(self, ap):
        # 调用方已持有 _lock。
        self.seq += 1
        self.current = ap.to_dict()
        self.relay.publish(_BROADCAST_CLIENT, {
            'type': 'view-appearance',
            'seq': self.seq,
            'appearance': self.current,
        })
        self._persist()
        return self.state()

    def _require(self) -> ContentScheduler:
        if self.scheduler is None:
            raise BroadcastError('尚未开始广播，请先 start')
        return self.scheduler

    # —— 查询 ——

    def state(self) -> dict:
        with self._lock:
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
            'playing': self.playing,
            'intervalMs': self.interval_ms,
            'current': self.current,
            'progress': self.scheduler.progress(),
            }

    def plan(self, count: Optional[int] = None) -> dict:
        """预览出场序列（不改动实时状态）。"""
        with self._lock:
            sched = self._require()
            return {
                'packIds': self.pack_ids,
                'strategy': self.strategy,
                'mode': sched.mode,
                'loop': sched.loop,
                'appearances': sched.plan(count),
                'progress': sched.progress(),
            }

    # —— 持久化 / 恢复 ——

    def _persist(self):
        try:
            if self.scheduler is None:
                db.del_state(_STATE_KEY)
                return
            db.set_state(_STATE_KEY, {
                'active': True,
                'startedAt': self.started_at,
                'packIds': self.pack_ids,
                'strategy': self.strategy,
                'seed': self.seed,
                'mode': self.scheduler.mode,
                'loop': self.scheduler.loop,
                'seq': self.seq,
                'current': self.current,
                'playing': self.playing,
                'intervalMs': self.interval_ms,
                'scheduler': self.scheduler.snapshot_state(),
            })
        except Exception as exc:  # 落库失败不能拖垮直播流程，但要留下痕迹
            print('[printcast] 广播状态落库失败：%s' % exc, file=sys.stderr)

    def restore(self) -> bool:
        """从 runtime_state 恢复上次广播（配置 + 进度 + 调度器游标）。

        内容包已被删除或快照损坏时静默放弃恢复，由 autoStart 或用户手动开播。
        出场历史（SceneRelay 事件）不跨重启，但当前角色与进度会保留。
        """
        try:
            snap = db.get_state(_STATE_KEY)
            if not isinstance(snap, dict) or not snap.get('active'):
                return False
            pack_ids = snap.get('packIds') or []
            packs = []
            for pid in pack_ids:
                pack = storage.get_pack(pid) if storage.valid_pack_id(pid) else None
                if pack is None:
                    return False
                packs.append(pack)
            if not packs:
                return False
            sched = ContentScheduler(packs, strategy=snap.get('strategy') or 'concat',
                                     seed=snap.get('seed'))
            if snap.get('mode') in ('sequence', 'weighted', 'trigger'):
                sched.mode = snap['mode']
            if snap.get('loop') is not None:
                sched.loop = bool(snap['loop'])
            sched.restore_state(snap.get('scheduler') or {})
        except Exception as exc:
            print('[printcast] 广播状态恢复失败，将从头开播：%s' % exc, file=sys.stderr)
            return False
        with self._lock:
            self.scheduler = sched
            self.pack_ids = list(pack_ids)
            self.strategy = snap.get('strategy') or 'concat'
            self.seed = normalize_seed(snap.get('seed'))
            self.current = snap.get('current')
            self.seq = int(snap.get('seq') or 0)
            self.started_at = snap.get('startedAt')
            self.playing = bool(snap.get('playing'))
            self.interval_ms = int(snap.get('intervalMs') or 4000)
        # 重启后若上次正在自动播放，重新挂起定时器，避免「重启即停播」。
        if self.playing and self.scheduler is not None:
            self._arm_timer()
        return True
