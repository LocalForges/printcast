import unittest
from printcast.relay import SceneRelay

class RelayTests(unittest.TestCase):
    def test_isolated_clients_receive_peer_messages_only(self):
        r=SceneRelay();self.assertEqual(r.poll('main')['cursor'],0)
        r.publish('main',{'type':'view-offer','sdp':{'type':'offer','sdp':'test'}})
        r.publish('view',{'type':'view-answer','sdp':{'type':'answer','sdp':'test'}})
        self.assertEqual([m['type'] for m in r.poll('main',0,0)['messages']],['view-answer'])
        self.assertEqual([m['type'] for m in r.poll('view',0,0)['messages']],['view-offer'])
    def test_new_client_does_not_replay_stale_offer(self):
        r=SceneRelay();r.publish('main',{'type':'view-offer'})
        snap = r.poll('new')
        self.assertEqual(snap['cursor'],1)
        self.assertEqual(snap['messages'],[])
        self.assertFalse(snap['gap'])
    def test_bounded_history_and_valid_types(self):
        r=SceneRelay()
        for _ in range(300):r.publish('main',{'type':'view-ping'})
        self.assertEqual(len(r.poll('view',0,0)['messages']),256)
        with self.assertRaises(ValueError):r.publish('bad',{'type':'execute'})
    def test_lagging_client_is_told_about_dropped_events(self):
        """有界队列挤出消息后必须显式告知 gap，不能让游标静默前进。"""
        r=SceneRelay()
        for _ in range(300):r.publish('main',{'type':'view-ping'})
        snap = r.poll('view',0,0)
        self.assertTrue(snap['gap'])
        self.assertEqual(snap['dropped'],44)
        self.assertEqual(snap['earliest'],45)
    def test_cursor_is_type_safe_and_clamped(self):
        r=SceneRelay();r.publish('main',{'type':'view-ping'})
        self.assertEqual(r.poll('v','1',0)['messages'],[])
        self.assertEqual(r.poll('v',-99,0)['messages'][0]['type'],'view-ping')
        with self.assertRaises(ValueError):r.poll('v','not-a-number',0)
if __name__=='__main__':unittest.main()
