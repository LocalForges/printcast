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
        with self.condition:
            if after is None:
                return {'cursor': self.sequence, 'messages': []}
            deadline = time.monotonic() + timeout
            while self.sequence <= after and time.monotonic() < deadline:
                self.condition.wait(max(0, deadline - time.monotonic()))
            return {'cursor': self.sequence,
                    'messages': [m for n, c, m in self.events if n > after and c != client]}
