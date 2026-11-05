"""内置示例内容包：把「明朝皇帝 / 故事人物出场顺序」做成开箱即用的数据。

- ming-emperors：明朝十六帝，按即位 order 升序，适合 sequence 叙事；
- sanguo / shuihu / honglou / xiyouji：经典故事人物，可单独用，也可与明朝包
  通过 interleave / merged 组合，呈现「帝王 × 故事人物」的跨包出场对照。

所有包都走 schema.validate_pack 校验后才写盘，保证与用户自己导入的包字段一致。
头像（avatar）留空，运行时由用户通过 /__api/media 上传后回填，演示空头像降级路径。
"""
from __future__ import annotations

import hashlib
import os

from . import config, storage


def builtin_packs() -> list:
    """返回全部内置内容包的原始 dict 列表（未落盘）。"""
    return [
        _demo_people(),
        _ming_emperors(),
        _sanguo(),
        _shuihu(),
        _honglou(),
        _xiyouji(),
    ]


# 演示人物：与展示端内置 demoNames 一致，开箱即有数据、头像真实可见（彩色首字 SVG）。
_DEMO_NAMES = [
    '橘子汽水', '星星同学', '奶油小熊', '薄荷拿铁', '蓝莓布丁', '桃桃乌龙',
    '快乐阿柴', '月亮晚安', '杨梅吐气', '椰奶泡泡', '芝士芋泥', '焦糖玛奇朵',
    '苏打绿豆', '元气布丁', '西瓜甜不甜', '奶盖十三', '柚子茶茶', '豆乳盒子',
    '麻薯团子', '蛋挞小伙', '软糖阿姨', '气泡水呀', '栗子同学', '糯米滋滋',
]


def _demo_people() -> dict:
    people = []
    for i, name in enumerate(_DEMO_NAMES):
        people.append((f'demo-{i}', name, i + 1, f'欢迎{name}来到直播间，为你现场打印专属头像', '演示;头像打印', 2))
    pack = _pack('demo-people', '演示人物', 'sequence', False,
                 '开箱即用的演示内容包：24 位虚拟观众，头像为彩色首字，无需上传即可体验', people)
    # 头像存为纯文件名（schema 不允许斜杠）；展示端 mediaUrl 会把 *.svg 映射到 /avatars/ 静态路由。
    for i, ch in enumerate(pack['characters']):
        ch['avatar'] = 'demo-%d.svg' % i
    return pack


def _ensure_demo_media() -> None:
    """把演示人物的彩色首字 SVG 头像落盘到 data/media/（幂等：已存在则跳过）。

    零第三方依赖：纯文本 SVG，由浏览器光栅化为 WebGL 贴图；
    若某浏览器无法作为贴图加载，展示端会回退到同款首字彩色徽章。
    """
    media_dir = os.path.join(config.DATA_DIR, 'media')
    try:
        os.makedirs(media_dir, exist_ok=True)
    except OSError:
        return
    for i, name in enumerate(_DEMO_NAMES):
        svg = _initial_avatar_svg(name)
        path = os.path.join(media_dir, f'demo-{i}.svg')
        if os.path.exists(path):
            continue
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(svg)
        except OSError:
            continue


def _initial_avatar_svg(name: str) -> str:
    label = name[:2] if len(name) >= 2 else name
    h = int(hashlib.md5(name.encode('utf-8')).hexdigest(), 16) % 360
    h2 = (h + 38) % 360
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="hsl({h},62%,56%)"/>'
        f'<stop offset="1" stop-color="hsl({h2},60%,42%)"/>'
        '</linearGradient></defs>'
        '<rect width="512" height="512" rx="104" fill="url(#g)"/>'
        f'<text x="256" y="266" font-size="208" fill="#ffffff" fill-opacity="0.96" '
        'text-anchor="middle" dominant-baseline="central" '
        'font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">'
        f'{label}</text></svg>'
    )


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
        # tags 以分号分隔的字符串传入，交给 schema.validate_pack 收敛成列表，
        # 与用户从 CSV/JSON 导入的字段完全一致（不要预拆成 list，否则会被 _coerce 二次字符串化）。
        characters.append({
            'id': cid, 'name': name, 'order': order,
            'speech': speech, 'tags': tags, 'weight': weight,
        })
    return {
        'id': pack_id, 'title': title, 'mode': mode, 'loop': loop,
        'description': desc, 'characters': characters,
    }


def seed_builtin_packs(overwrite: bool = False) -> dict:
    """把内置原始示例包写入 SQLite，并同步落盘 data/packs/*.json 镜像。

    返回 {written, skipped, errors}。存在性判断以库为准（不再是「看 JSON 文件
    在不在」）；overwrite=False 时跳过已存在同 id 的包，避免覆盖用户自有数据。
    """
    _ensure_demo_media()
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
