"""Bounded, local-only signalling for separately isolated WebView profiles."""
import time
from collections import deque
from threading import Condition

ALLOWED_TYPES = frozenset({
    'view-request', 'view-offer', 'view-answer', 'view-ice', 'view-ping',
    'view-ready', 'view-bye', 'view-size', 'view-stats', 'view-camera',
    'view-camera-request', 'view-camera-change',
    # 内容包角色「出场」广播：调度器把下一个角色推给所有订阅的浏览器标签页。
    'view-appearance',
    # 控制台写设置后广播一条「配置已变」信令：展示端不必等 5s 轮询，收到即重读。
    'settings-changed',
})


class SceneRelay:
    """场景镜像的信令中转。

    设计约束：
    - 有界（deque maxlen=256）—— 客户端长时间不轮询也不能把内存吃光；
    - 只转发、不广播给发起者自己 —— 避免 SDP 回声；
    - publish 校验类型白名单，非法消息直接抛 ValueError，不污染队列。
    """

    def __init__(self):
        self.condition = Condition()
        self.sequence = 0
        self.events = deque(maxlen=256)

    def publish(self, client, message):
        if not isinstance(client, str) or not 1 <= len(client) <= 80:
            raise ValueError('bad client')
        if not isinstance(message, dict) or message.get('type') not in ALLOWED_TYPES:
            raise ValueError('bad message')
        with self.condition:
            self.sequence += 1
            self.events.append((self.sequence, client, message))
            self.condition.notify_all()

    def poll(self, client, after=None, timeout=15):
        """长轮询取增量事件。

        - after=None 是「握手」语义：立刻返回当前游标，不回放历史；
        - after 统一收口成 int 并钳制到 [0, sequence]，避免字符串比较 TypeError
          或负数游标把整段历史重放给客户端；
        - deque 有界，客户端落后超过 256 条时事件会被挤出。返回 gap / dropped /
          earliest 让订阅方知道自己漏了消息，可主动拉 /__api/broadcast 补位，
          而不是「静默丢事件且游标照常前进」。
        """
        with self.condition:
            if after is None:
                return {'cursor': self.sequence, 'messages': [],
                        'gap': False, 'dropped': 0,
                        'earliest': self.events[0][0] if self.events else self.sequence + 1}
            try:
                after = int(after)
            except (TypeError, ValueError):
                raise ValueError('bad cursor')
            after = max(0, min(after, self.sequence))
            deadline = time.monotonic() + timeout
            while self.sequence <= after and time.monotonic() < deadline:
                self.condition.wait(max(0, deadline - time.monotonic()))
            earliest = self.events[0][0] if self.events else self.sequence + 1
            dropped = max(0, earliest - 1 - after)
            return {
                'cursor': self.sequence,
                'messages': [m for n, c, m in self.events if n > after and c != client],
                'gap': dropped > 0,
                'dropped': dropped,
                'earliest': earliest,
            }
