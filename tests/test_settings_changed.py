"""配置变更信令：控制台一保存，展示端应立即知道，而不是等 5s 轮询。

两件事要锁住：
1. relay 白名单接受 settings-changed（否则 publish 抛 ValueError，被上层吞掉）；
2. 只有「设置写成功」才发信令——读请求、失败请求、其它资源都不发，避免刷订阅端。
"""
import unittest

from printcast import server
from printcast.relay import SceneRelay


class FakeRelay:
    def __init__(self):
        self.published = []

    def publish(self, client, message):
        self.published.append((client, message))


class SettingsChangedSignalTests(unittest.TestCase):
    def test_relay_accepts_settings_changed(self):
        relay = SceneRelay()
        relay.publish('settings', {'type': 'settings-changed', 'at': 1})
        messages = relay.poll('renderer', 0, 0)['messages']
        self.assertEqual([m['type'] for m in messages], ['settings-changed'])

    def test_publishes_on_successful_settings_write(self):
        relay = FakeRelay()
        server.notify_settings_changed(relay, ['__api', 'settings'], 200)
        self.assertEqual(len(relay.published), 1)
        client, message = relay.published[0]
        self.assertEqual(client, 'settings')
        self.assertEqual(message['type'], 'settings-changed')
        self.assertIn('at', message)

    def test_silent_for_other_resources_reads_and_failures(self):
        cases = [
            (['__api', 'packs'], 200),      # 别的资源
            (['__api', 'settings'], 400),   # 写失败
            (['__api', 'settings'], 422),   # 校验失败
            (['__api'], 200),               # 路径段不足
        ]
        for segments, status in cases:
            relay = FakeRelay()
            server.notify_settings_changed(relay, segments, status)
            self.assertEqual(relay.published, [], '%s/%s 不应发信令' % (segments, status))

    def test_never_raises_when_relay_is_broken(self):
        class Broken:
            def publish(self, *a, **k):
                raise RuntimeError('relay down')

        # 广播失败绝不能影响这次写请求：这里只要不抛异常即可。
        self.assertIsNone(server.notify_settings_changed(Broken(), ['__api', 'settings'], 200))
        self.assertIsNone(server.notify_settings_changed(None, ['__api', 'settings'], 200))


if __name__ == '__main__':
    unittest.main()
