"""内置示例内容包：把「明朝皇帝 / 故事人物出场顺序」做成开箱即用的数据。

- ming-emperors：明朝十六帝，按即位 order 升序，适合 sequence 叙事；
- sanguo / shuihu / honglou / xiyouji：经典故事人物，可单独用，也可与明朝包
  通过 interleave / merged 组合，呈现「帝王 × 故事人物」的跨包出场对照。

所有包都走 schema.validate_pack 校验后才写盘，保证与用户自己导入的包字段一致。
头像（avatar）留空，运行时由用户通过 /__api/media 上传后回填，演示空头像降级路径。
"""
from __future__ import annotations

from . import storage


def builtin_packs() -> list:
    """返回全部内置内容包的原始 dict 列表（未落盘）。"""
    return [
        _ming_emperors(),
        _sanguo(),
        _shuihu(),
        _honglou(),
        _xiyouji(),
    ]


def _ming_emperors() -> dict:
    emperors = [
        ('hongwu', '朱元璋', 1, '洪武开基，驱元复汉，定鼎金陵', '开国;帝王', 3),
        ('jianwen', '朱允炆', 2, '建文削藩，靖难起兵，宫闱一炬', '帝王', 1),
        ('yongle', '朱棣', 3, '永乐靖难，迁都北京，郑和西洋', '迁都;帝王', 3),
        ('hongxi', '朱高炽', 4, '洪熙守成，仁宣之治先声', '帝王', 1),
        ('xuande', '朱瞻基', 5, '宣德善绘，促织之戏留名', '帝王', 1),
        ('zhengtong', '朱祁镇', 6, '正统北狩，土木之变；天顺夺门', '帝王', 1),
        ('jingtai', '朱祁钰', 7, '景泰监国，北京保卫战功成', '帝王', 1),
        ('chenghua', '朱见深', 8, '成化宠溺，万贵妃专房', '帝王', 1),
        ('hongzhi', '朱祐樘', 9, '弘治中兴，一夫一妻帝王', '帝王', 1),
        ('zhengde', '朱厚照', 10, '正德游幸，豹房佞幸', '帝王', 1),
        ('jiajing', '朱厚熜', 11, '嘉靖修道，海瑞上疏', '帝王', 1),
        ('longqing', '朱载坖', 12, '隆庆开关，俺答封贡', '帝王', 1),
        ('wanli', '朱翊钧', 13, '万历中兴，后期怠政', '帝王', 2),
        ('taichang', '朱常洛', 14, '泰昌一月，红丸疑案', '帝王', 1),
        ('tianqi', '朱由校', 15, '天启木工，魏忠贤乱政', '帝王', 1),
        ('chongzhen', '朱由检', 16, '崇祯殉国，甲申之变，明亡', '亡国;帝王', 3),
    ]
    return _pack('ming-emperors', '明朝十六帝', 'sequence', False,
                 '按即位先后出场，从洪武到崇祯', emperors)


def _sanguo() -> dict:
    people = [
        ('liubei', '刘备', 1, '汉室宗亲，仁德布于天下', '蜀汉;君主', 2),
        ('caocao', '曹操', 2, '魏武挥鞭，挟天子令诸侯', '曹魏;奸雄', 3),
        ('sunquan', '孙权', 3, '坐断东南，赤壁联刘拒曹', '东吴;君主', 2),
        ('zhugeliang', '诸葛亮', 4, '鞠躬尽瘁，六出祁山', '蜀汉;谋臣', 3),
        ('guanyu', '关羽', 5, '过五关斩六将，义薄云天', '蜀汉;武将', 3),
        ('zhangfei', '张飞', 6, '当阳桥断喝，喝退曹兵', '蜀汉;武将', 2),
        ('zhaoyun', '赵云', 7, '长坂坡单骑救主', '蜀汉;武将', 2),
        ('zhouyu', '周瑜', 8, '赤壁火攻，羽扇纶巾', '东吴;谋臣', 2),
        ('simayi', '司马懿', 9, '隐忍待时，三家归晋', '曹魏;谋臣', 2),
        ('luxun', '陆逊', 10, '夷陵火烧连营', '东吴;谋臣', 1),
        ('huangzhong', '黄忠', 11, '定军山斩夏侯渊', '蜀汉;武将', 1),
        ('diaochan', '貂蝉', 12, '连环计离间董吕', '群芳;谋士', 1),
    ]
    return _pack('sanguo', '三国演义', 'sequence', False,
                 '三国群英按登场戏份排序', people)


def _shuihu() -> dict:
    people = [
        ('songjiang', '宋江', 1, '呼保义，替天行道聚义厅', '梁山;首领', 3),
        ('lujunyi', '卢俊义', 2, '玉麒麟，棍棒天下无对', '梁山;首领', 2),
        ('wuyong', '吴用', 3, '智多星，运筹忠义堂', '梁山;谋士', 2),
        ('linchong', '林冲', 4, '豹子头，风雪山神庙', '梁山;武将', 3),
        ('wusong', '武松', 5, '行者，景阳冈打虎', '梁山;武将', 3),
        ('luzhishen', '鲁智深', 6, '花和尚，倒拔垂杨柳', '梁山;武将', 3),
        ('lida', '李逵', 7, '黑旋风，双斧嗜血', '梁山;武将', 2),
        ('huarong', '花荣', 8, '小李广，神箭无双', '梁山;武将', 2),
        ('shijin', '史进', 9, '九纹龙，少华山下拜师', '梁山;武将', 1),
        ('yangzhi', '杨志', 10, '青面兽，卖刀杀牛二', '梁山;武将', 1),
        ('chaijin', '柴进', 11, '小旋风，仗义疏财', '梁山;头领', 1),
        ('sunerniang', '孙二娘', 12, '母夜叉，十字坡开店', '梁山;头领', 1),
    ]
    return _pack('shuihu', '水浒传', 'sequence', False,
                 '梁山好汉按座次与戏份排序', people)


def _honglou() -> dict:
    people = [
        ('baoyu', '贾宝玉', 1, '衔玉而生，情根历劫', '主角;贾府', 3),
        ('daiyu', '林黛玉', 2, '潇湘妃子，葬花吟愁', '主角;群芳', 3),
        ('baochai', '薛宝钗', 3, '停机德，金锁配通灵', '主角;群芳', 3),
        ('wangxifeng', '王熙凤', 4, '凤辣子，机关算尽', '贾府;管家', 3),
        ('jiamu', '贾母', 5, '史太君，荣国府尊', '贾府;长辈', 2),
        ('tanchun', '贾探春', 6, '敏探春，兴利除弊', '贾府;才女', 2),
        ('xiangyun', '史湘云', 7, '憨湘云，醉眠芍药', '群芳;才女', 2),
        ('miaoyu', '妙玉', 8, '槛外人，洁癖孤高', '群芳;方外', 1),
        ('qingwen', '晴雯', 9, '撕扇千金笑，补裘病中', '贾府;丫鬟', 2),
        ('xifeng_husband', '贾琏', 10, '琏二爷，偷娶尤二姐', '贾府;晚辈', 1),
    ]
    return _pack('honglou', '红楼梦', 'sequence', False,
                 '金陵十二钗与贾府子弟按戏份排序', people)


def _xiyouji() -> dict:
    people = [
        ('tangsen', '唐僧', 1, '金蝉长老，誓取真经', '取经;师父', 3),
        ('wukong', '孙悟空', 2, '齐天大圣，火眼金睛', '取经;大徒弟', 3),
        ('bajie', '猪八戒', 3, '天蓬元帅，好吃懒做', '取经;二徒弟', 3),
        ('shaseng', '沙僧', 4, '卷帘大将，挑担牵马', '取经;三徒弟', 2),
        ('bailongma', '白龙马', 5, '西海龙王三太子，化身坐骑', '取经;脚力', 1),
        ('niumo', '牛魔王', 6, '平天大圣，火焰山借扇', '妖王;对立', 2),
        ('tieshan', '铁扇公主', 7, '罗刹女，芭蕉扇克火', '妖王;对立', 1),
        ('baigujing', '白骨精', 8, '尸魔三戏唐三藏', '妖王;对立', 2),
    ]
    return _pack('xiyouji', '西游记', 'sequence', False,
                 '取经团队与主要妖王按登场排序', people)


def _pack(pack_id, title, mode, loop, desc, rows) -> dict:
    characters = []
    for cid, name, order, speech, tags, weight in rows:
        characters.append({
            'id': cid, 'name': name, 'order': order,
            'speech': speech, 'tags': tags.split(';'), 'weight': weight,
        })
    return {
        'id': pack_id, 'title': title, 'mode': mode, 'loop': loop,
        'description': desc, 'characters': characters,
    }


def seed_builtin_packs(overwrite: bool = False) -> dict:
    """把内置内容包写入 data/packs/，返回 {written, skipped, errors}。

    overwrite=False 时跳过已存在同 id 的包，避免覆盖用户自有数据。
    """
    written, skipped, errors = [], [], []
    for pack in builtin_packs():
        try:
            from . import schema
            cleaned, errs = schema.validate_pack(pack)
            if errs:
                errors.append({'id': pack['id'], 'errors': errs})
                continue
            if storage.get_pack(pack['id']) and not overwrite:
                skipped.append(pack['id'])
                continue
            storage.save_pack(cleaned)
            written.append(pack['id'])
        except Exception as exc:  # noqa: BLE001 — 单个包失败不应阻断其余
            errors.append({'id': pack['id'], 'error': str(exc)})
    return {'written': written, 'skipped': skipped, 'errors': errors}
