"""内容包出场顺序调度器：消费 schema 定义的内容包，按 mode 产出出场序列。

三档出场模式（见 schema.MODES）：
- sequence：按 characters[].order 升序出场（schema 已稳定排序），loop 可循环；
- weighted：按 weight 加权随机出场，避免连续重复同一角色；
- trigger ：不自动出场，由 broadcast.trigger(char_id) 在事件（礼物 / 评论）时推上场。

「扩展更多」能力：
- 多内容包组合（playlist）：
    concat     顺次播完一个包再播下一个；
    interleave 各包按位轮转（用于把「明朝皇帝」与「故事人物」穿插对照）；
    merged     合并后按 order 统一排序（跨包叙事顺序）；
- 可复现：传入 seed 即固定 weighted 的随机结果，便于测试与回放；
- 进度与历史：progress() / history() 让 UI 与下游渲染知道「现在是谁、还剩多少」。

零第三方依赖：纯 stdlib，可被 api / broadcast / cli / 测试直接调用。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

from . import schema

# (角色, 所属包 id, 所属包标题) 的内部三元组
_Item = Tuple[dict, str, str]


@dataclass
class Appearance:
    """一次出场事件：谁、来自哪个包、在调度内的全局序号与轮次。"""
    character: dict
    pack_id: str
    pack_title: str
    index: int            # 在本调度内的全局序号（从 0 起）
    mode: str
    loop: int = 0         # 第几轮循环（仅 sequence + loop 时 > 0）

    def to_dict(self) -> dict:
        """派生出的展示字段，直接交给前端 / 渲染层。"""
        c = self.character
        return {
            'id': c.get('id'),
            'name': c.get('name'),
            'avatar': c.get('avatar'),
            'speech': c.get('speech'),
            'tags': c.get('tags', []),
            'order': c.get('order'),
            'weight': c.get('weight'),
            'packId': self.pack_id,
            'packTitle': self.pack_title,
            'index': self.index,
            'loop': self.loop,
            'mode': self.mode,
        }


class ContentScheduler:
    """把一个或多个已校验内容包编排成可递进的出场序列。"""

    STRATEGIES = ('concat', 'interleave', 'merged')

    def __init__(self, packs: Iterable[dict], strategy: str = 'concat', seed=None):
        self.raw_packs = [p for p in packs if isinstance(p, dict)]
        if not self.raw_packs:
            raise ValueError('至少需要一个内容包')
        if strategy not in self.STRATEGIES:
            raise ValueError('未知的组合策略：%s' % strategy)
        self.strategy = strategy
        self._seed = seed
        self.rng = random.Random(seed)
        self.packs = self._validated()
        # 多包场景以首个包的 mode 为主调度模式；叙事类组合默认都应是 sequence。
        self.mode = (self.packs[0].get('mode') or 'sequence')
        if self.mode not in schema.MODES:
            self.mode = 'sequence'
        self.loop = any(bool(p.get('loop')) for p in self.packs)
        self._build()
        self.reset()

    # —— 构造期 ——

    def _validated(self) -> List[dict]:
        cleaned = []
        for p in self.raw_packs:
            ok, errs = schema.validate_pack(p)
            if errs:
                raise ValueError('内容包「%s」校验失败：%s'
                                 % (p.get('id', '?'), errs))
            cleaned.append(ok)
        return cleaned

    def _build(self):
        packs_chars = [(p['characters'], p['id'], p.get('title', p['id']))
                       for p in self.packs]
        self._ordered = self._build_ordered(packs_chars, self.strategy)
        # weighted 候选用所有 weight > 0 的角色，与组合策略无关。
        self._roster = [(c, pid, pt) for chars, pid, pt in packs_chars
                        for c in chars if (c.get('weight') or 0) > 0]
        # trigger 队列初始按 sequence 顺序排列，trigger 时按需弹出。
        self._pending = list(self._ordered)

    @staticmethod
    def _build_ordered(packs_chars, strategy) -> List[_Item]:
        if strategy == 'interleave':
            maxlen = max((len(chars) for chars, _, _ in packs_chars), default=0)
            ordered: List[_Item] = []
            for i in range(maxlen):
                for chars, pid, pt in packs_chars:
                    if i < len(chars):
                        ordered.append((chars[i], pid, pt))
            return ordered
        if strategy == 'merged':
            items = []
            for pi, (chars, pid, pt) in enumerate(packs_chars):
                for ci, c in enumerate(chars):
                    items.append((c.get('order', 0), pi, ci, c, pid, pt))
            items.sort(key=lambda t: (t[0], t[1], t[2]))
            return [(c, pid, pt) for _, _, _, c, pid, pt in items]
        # concat（默认）：按包顺序拼接
        return [(c, pid, pt) for chars, pid, pt in packs_chars for c in chars]

    # —— 运行期状态 ——

    def reset(self):
        self._pos = 0
        self._loop_count = 0
        self._last_weighted = None
        self._history: List[Appearance] = []
        # trigger 队列在 reset 时回到完整顺序
        self._pending = list(self._ordered)
        return self

    def next(self) -> Optional[Appearance]:
        if self.mode == 'sequence':
            return self._next_sequence()
        if self.mode == 'weighted':
            return self._next_weighted()
        # trigger 模式下不自动出场；显式 trigger() 才推。
        return None

    def _next_sequence(self) -> Optional[Appearance]:
        if not self._ordered:
            return None
        if self._pos >= len(self._ordered):
            if self.loop:
                self._pos = 0
                self._loop_count += 1
            else:
                return None
        c, pid, pt = self._ordered[self._pos]
        self._pos += 1
        return self._emit(c, pid, pt, loop=self._loop_count)

    def _next_weighted(self) -> Optional[Appearance]:
        if not self._roster:
            return None
        if len(self._roster) == 1:
            c, pid, pt = self._roster[0]
            return self._emit(c, pid, pt)
        eligible = [(c, pid, pt) for (c, pid, pt) in self._roster
                    if id(c) != id(self._last_weighted)] or self._roster
        weights = [c.get('weight') or 0 for c, _, _ in eligible]
        chosen = self.rng.choices(eligible, weights=weights, k=1)[0]
        self._last_weighted = chosen[0]
        return self._emit(chosen[0], chosen[1], chosen[2])

    def trigger(self, char_id: Optional[str] = None) -> Optional[Appearance]:
        """事件驱动出场：不自动推进，由外部（礼物 / 评论 / 手动点名）调用。

        char_id 给定则精确点名（跨包查找）；否则弹队首。loop 开启时队首出列后
        补到队尾，形成无限循环。返回 None 表示无可用角色。
        """
        if char_id:
            for source in (self._pending, self._ordered):
                for c, pid, pt in source:
                    if c.get('id') == char_id:
                        return self._emit(c, pid, pt)
            return None
        if not self._pending:
            if not self._ordered:
                return None
            self._pending = list(self._ordered)
        c, pid, pt = self._pending.pop(0)
        if self.loop:
            self._pending.append((c, pid, pt))
        return self._emit(c, pid, pt)

    def _emit(self, c, pid, pt, loop=0) -> Appearance:
        ap = Appearance(character=c, pack_id=pid, pack_title=pt,
                        index=len(self._history), mode=self.mode, loop=loop)
        self._history.append(ap)
        return ap

    def peek(self) -> Optional[dict]:
        """预览下一个出场角色（不推进游标）。weighted / trigger 返回 None。"""
        if self.mode == 'sequence' and self._ordered:
            if self._pos < len(self._ordered):
                c, pid, pt = self._ordered[self._pos]
                return self._preview_dict(c, pid, pt, loop=self._loop_count)
        return None

    def plan(self, count: Optional[int] = None) -> List[dict]:
        """生成出场序列的预览（**不改动**实时游标 / 历史），供 API 与 UI 调用。

        - sequence 非 loop：从当前位置到末尾（可被 count 截断）；
        - sequence + loop：循环 count 次（count 缺省为一轮长度）；
        - weighted：按 seed 复现地抽样 count 次（count 缺省 20 或候选数）；
        - trigger ：返回当前待出场队列。
        """
        if self.mode == 'weighted':
            return self._plan_weighted(count)
        if self.mode == 'trigger':
            return [self._preview_dict(c, pid, pt)
                    for c, pid, pt in self._pending]
        # sequence
        if self.loop:
            return self._plan_loop(count or len(self._ordered))
        seq = self._ordered[self._pos:]
        if count is not None:
            seq = seq[:count]
        return [self._preview_dict(c, pid, pt, loop=0) for c, pid, pt in seq]

    def _plan_loop(self, count: int) -> List[dict]:
        if not self._ordered:
            return []
        out, n = [], max(1, count)
        for k in range(n):
            c, pid, pt = self._ordered[k % len(self._ordered)]
            out.append(self._preview_dict(c, pid, pt, loop=k // len(self._ordered)))
        return out

    def _plan_weighted(self, count: Optional[int]) -> List[dict]:
        if not self._roster:
            return []
        n = count or min(20, len(self._roster))
        r = random.Random(self._seed)
        last = None
        out: List[dict] = []
        for _ in range(n):
            eligible = (self._roster if len(self._roster) == 1
                        else [x for x in self._roster if id(x[0]) != id(last)])
            weights = [x[0].get('weight') or 0 for x in eligible]
            if sum(weights) <= 0:
                eligible, weights = self._roster, [x[0].get('weight') or 0
                                                   for x in self._roster]
            chosen = r.choices(eligible, weights=weights, k=1)[0]
            last = chosen[0]
            out.append(self._preview_dict(chosen[0], chosen[1], chosen[2]))
        return out

    @staticmethod
    def _preview_dict(c, pid, pt, loop=0) -> dict:
        return {
            'id': c.get('id'), 'name': c.get('name'), 'avatar': c.get('avatar'),
            'speech': c.get('speech'), 'tags': c.get('tags', []),
            'order': c.get('order'), 'weight': c.get('weight'),
            'packId': pid, 'packTitle': pt, 'loop': loop, 'mode': None,
        }

    # —— 查询 ——

    def progress(self) -> dict:
        total = len(self._ordered) if self.mode != 'weighted' else len(self._roster)
        if self.mode == 'trigger':
            total = len(self._pending)
        return {
            'mode': self.mode,
            'strategy': self.strategy,
            'loop': self.loop,
            'position': self._pos,
            'total': total,
            'remaining': max(0, total - self._pos) if self.mode == 'sequence' and not self.loop else None,
            'appeared': len(self._history),
            'cycle': self._loop_count,
        }

    def history(self) -> List[dict]:
        return [ap.to_dict() for ap in self._history]

    def roster(self) -> List[dict]:
        """当前调度覆盖的全部角色（按出场顺序排列），供 UI 展示完整清单。"""
        source = self._ordered if self.mode != 'weighted' else self._roster
        if self.mode == 'trigger':
            source = self._pending
        return [self._preview_dict(c, pid, pt) for c, pid, pt in source]

    def is_exhausted(self) -> bool:
        if self.loop:
            return False
        if self.mode == 'sequence':
            return self._pos >= len(self._ordered)
        if self.mode == 'weighted':
            return not self._roster
        return not self._pending
