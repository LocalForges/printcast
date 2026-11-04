"""出场调度引擎测试：三模式 / 多包组合 / seed 可复现 / 进度历史。

直接调用纯函数，不依赖 HTTP 服务与磁盘内容包。
"""
import unittest

from printcast import samples, scheduler
from printcast.scheduler import ContentScheduler, Appearance


def _pack(pid, chars):
    return {'id': pid, 'title': pid, 'mode': 'sequence',
            'characters': [{'id': c[0], 'name': c[1], 'order': c[2],
                            'weight': c[3] if len(c) > 3 else 1} for c in chars]}


MING = _pack('ming', [
    ('h', '洪武', 1, 3), ('j', '建文', 2, 1), ('y', '永乐', 3, 3), ('c', '崇祯', 16, 3)])
SG = _pack('sg', [
    ('lb', '刘备', 1, 2), ('cc', '曹操', 2, 3), ('sq', '孙权', 3, 2)])


class SequenceTests(unittest.TestCase):
    def test_sequence_follows_order(self):
        s = ContentScheduler([MING])
        self.assertEqual([a['name'] for a in s.plan()], ['洪武', '建文', '永乐', '崇祯'])

    def test_next_advances_and_exhausts(self):
        s = ContentScheduler([MING])
        names = [s.next().character['name'] for _ in range(4)]
        self.assertEqual(names, ['洪武', '建文', '永乐', '崇祯'])
        self.assertIsNone(s.next())          # 非 loop 耗尽
        self.assertTrue(s.is_exhausted())

    def test_loop_restarts_and_counts_cycles(self):
        s = ContentScheduler([MING])
        s.loop = True
        out = [s.next().character['name'] for _ in range(9)]  # 两轮 + 1
        self.assertEqual(out[:4], ['洪武', '建文', '永乐', '崇祯'])
        self.assertEqual(out[4:], ['洪武', '建文', '永乐', '崇祯', '洪武'])
        self.assertEqual(s.progress()['cycle'], 2)

    def test_peek_does_not_advance(self):
        s = ContentScheduler([MING])
        self.assertEqual(s.peek()['name'], '洪武')
        self.assertEqual(s.peek()['name'], '洪武')
        self.assertEqual(s.progress()['appeared'], 0)

    def test_reset_restores(self):
        s = ContentScheduler([MING])
        s.next(); s.next()
        self.assertEqual(s.progress()['position'], 2)
        s.reset()
        self.assertEqual(s.progress()['position'], 0)
        self.assertEqual(s.peek()['name'], '洪武')


class WeightedTests(unittest.TestCase):
    def test_weighted_avoid_immediate_repeat(self):
        s = ContentScheduler([MING], seed=1)
        s.mode = 'weighted'
        seq = [s.next().character['id'] for _ in range(40)]
        for a, b in zip(seq, seq[1:]):
            self.assertNotEqual(a, b)         # 无连续重复（>1 候选时）

    def test_weighted_deterministic_with_seed(self):
        a = ContentScheduler([MING], seed=7); a.mode = 'weighted'
        b = ContentScheduler([MING], seed=7); b.mode = 'weighted'
        self.assertEqual([x['id'] for x in a.plan(15)],
                         [x['id'] for x in b.plan(15)])

    def test_weighted_plan_is_preview_only(self):
        s = ContentScheduler([MING], seed=2); s.mode = 'weighted'
        s.plan(10)
        self.assertEqual(s.progress()['appeared'], 0)   # plan 不动游标

    def test_weighted_zero_weight_excluded(self):
        pack = _pack('z', [('x', 'X', 1, 0), ('y', 'Y', 2, 5)])
        s = ContentScheduler([pack], seed=1); s.mode = 'weighted'
        ids = {x.character['id'] for x in [s.next() for _ in range(20)]}
        self.assertNotIn('x', ids)            # weight 0 永不出现


class TriggerTests(unittest.TestCase):
    def test_trigger_named_and_auto(self):
        s = ContentScheduler([SG]); s.mode = 'trigger'
        self.assertEqual(s.trigger('cc').character['name'], '曹操')
        self.assertEqual(s.trigger().character['name'], '刘备')  # 队首
        self.assertIsNone(s.next())          # trigger 模式不自动出场

    def test_trigger_loop_cycles(self):
        s = ContentScheduler([SG]); s.mode = 'trigger'; s.loop = True
        out = [s.trigger().character['id'] for _ in range(7)]
        self.assertEqual(out, ['lb', 'cc', 'sq', 'lb', 'cc', 'sq', 'lb'])

    def test_trigger_unknown_id_returns_none(self):
        s = ContentScheduler([SG]); s.mode = 'trigger'
        self.assertIsNone(s.trigger('nope'))


class MultiPackTests(unittest.TestCase):
    def test_concat(self):
        s = ContentScheduler([MING, SG], strategy='concat')
        ids = [a['name'] for a in s.plan()]
        self.assertEqual(ids, ['洪武', '建文', '永乐', '崇祯', '刘备', '曹操', '孙权'])

    def test_interleave(self):
        s = ContentScheduler([MING, SG], strategy='interleave')
        ids = [a['name'] for a in s.plan()]
        self.assertEqual(ids[0:4], ['洪武', '刘备', '建文', '曹操'])

    def test_merged_orders_across_packs(self):
        s = ContentScheduler([MING, SG], strategy='merged')
        # 两包 order 1..16 / 1..3，合并后按 order 升序；同 order 时按输入次序（MING 在前）。
        ids = [a['name'] for a in s.plan()]
        self.assertEqual(ids[0:4], ['洪武', '刘备', '建文', '曹操'])

    def test_interleave_with_uneven_lengths(self):
        short = _pack('s', [('a', 'A', 1), ('b', 'B', 2)])
        s = ContentScheduler([short, MING], strategy='interleave')
        names = [a['name'] for a in s.plan()]
        # 短包耗尽后只轮转长包
        self.assertEqual(names, ['A', '洪武', 'B', '建文', '永乐', '崇祯'])


class SamplesTests(unittest.TestCase):
    def test_builtin_packs_validate(self):
        for pack in samples.builtin_packs():
            from printcast import schema
            ok, errs = schema.validate_pack(pack)
            self.assertEqual(errs, [], msg='内置包 %s 校验失败: %s' % (pack['id'], errs))

    def test_ming_emperors_order_1_to_16(self):
        ming = next(p for p in samples.builtin_packs() if p['id'] == 'ming-emperors')
        orders = [c['order'] for c in ming['characters']]
        self.assertEqual(orders, list(range(1, 17)))
        names = [c['name'] for c in ming['characters']]
        self.assertEqual(names[0], '朱元璋')
        self.assertEqual(names[-1], '朱由检')

    def test_four_story_packs_present(self):
        ids = {p['id'] for p in samples.builtin_packs()}
        for needed in ('sanguo', 'shuihu', 'honglou', 'xiyouji'):
            self.assertIn(needed, ids)


class ApiScheduleTests(unittest.TestCase):
    """/__api/schedule 纯函数预览（用临时 DATA_DIR，不污染）。"""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from pathlib import Path
        from printcast import config, storage
        cls.tmp = Path(tempfile.mkdtemp())
        config.DATA_DIR = cls.tmp
        for pack in samples.builtin_packs():
            storage.save_pack(pack)

    def test_schedule_sequence_preview(self):
        from printcast import api
        status, data = _dispatch('GET', '/__api/schedule?pack=ming-emperors')
        self.assertEqual(status, 200)
        self.assertTrue(data['ok'])
        self.assertEqual(len(data['appearances']), 16)
        self.assertEqual(data['appearances'][0]['name'], '朱元璋')

    def test_schedule_multi_pack_interleave(self):
        from printcast import api
        status, data = _dispatch('GET',
            '/__api/schedule?pack=ming-emperors&pack=sanguo&strategy=interleave&count=4')
        self.assertEqual(status, 200)
        self.assertEqual([a['name'] for a in data['appearances']],
                         ['朱元璋', '刘备', '朱允炆', '曹操'])

    def test_schedule_weighted_deterministic(self):
        from printcast import api
        _, a = _dispatch('GET', '/__api/schedule?pack=ming-emperors&mode=weighted&seed=5&count=10')
        _, b = _dispatch('GET', '/__api/schedule?pack=ming-emperors&mode=weighted&seed=5&count=10')
        self.assertEqual([x['id'] for x in a['appearances']],
                         [x['id'] for x in b['appearances']])

    def test_schedule_missing_pack_404(self):
        from printcast import api
        status, _ = _dispatch('GET', '/__api/schedule?pack=does-not-exist')
        self.assertEqual(status, 404)

    def test_schedule_no_pack_400(self):
        from printcast import api
        status, _ = _dispatch('GET', '/__api/schedule')
        self.assertEqual(status, 400)


def _dispatch(method, path):
    from printcast import api as _api
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(path)
    query = parse_qs(parsed.query) if parsed.query else {}
    resp = _api.dispatch(method, parsed.path, query, {}, b'')
    import json
    return resp.status, json.loads(resp.body.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
