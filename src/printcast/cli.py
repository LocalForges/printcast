"""命令行入口：python -m printcast [选项] / printcast [选项]。

三种运行形态：
1. 桌面版（默认）   —— pywebview 窗口，带可调用 JS API；
2. --server-only    —— 只起 HTTP 服务，自动开浏览器，适合纯前台调试；
3. --live-room / --scene-view —— 独立子窗口（由主进程拉起，一般不手动用）。
"""
import argparse
import os
import subprocess
import sys
import threading

from .config import CAPTURE_COMPAT_FILE, IS_MAC, IS_WIN, LIVE_DEBUG_PORT, ROOT, WEBVIEW_GUI
from .server import ensure_server
from .probe import listening


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog='printcast',
        description='直播间弹幕驱动的 3D 打印直播台')
    parser.add_argument('--server-only', action='store_true',
                        help='只启动本地 HTTP 服务，不打开桌面窗口')
    parser.add_argument('--open-browser', dest='open_browser', action='store_true',
                        help='--server-only 时自动用默认浏览器打开页面（默认开启）')
    parser.add_argument('--no-open-browser', dest='open_browser', action='store_false',
                        help='--server-only 时只起服务，不打开浏览器')
    parser.add_argument('--port', type=int, help='HTTP 端口（默认 8080，被占用时自动顺延）')
    parser.add_argument('--room', help='启动后直接打开该直播间并开始抓取')
    parser.add_argument('--capture', action='store_true', help='配合 --room：自动点开始抓取')
    parser.add_argument('--live-room', help=argparse.SUPPRESS)
    parser.add_argument('--scene-view', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--scene-orient', default='landscape', help=argparse.SUPPRESS)
    # —— 内容包 / 出场调度 ——
    parser.add_argument('--seed', action='store_true',
                        help='把内置原始示例包（明朝十六帝 + 四故事包）写入 SQLite 并同步落盘 JSON')
    parser.add_argument('--overwrite', action='store_true',
                        help='配合 --seed / --db import：覆盖已存在的内容包（默认跳过）')
    parser.add_argument('--db', choices=['info', 'verify', 'import', 'export'],
                        help='数据库维护：info 状态 / verify 自检 / import 从 JSON 导入 / export 导出 JSON')
    parser.add_argument('--schedule', nargs='*', metavar='PACK',
                        help='预览指定内容包的出场顺序后退出；不跟包名则列出全部可用包')
    parser.add_argument('--strategy', default='concat',
                        choices=['concat', 'interleave', 'merged'],
                        help='多包组合策略（仅 --schedule 多包时生效）')
    parser.add_argument('--mode', default=None,
                        choices=['sequence', 'weighted', 'trigger'],
                        help='覆盖出场模式（仅 --schedule 时生效）')
    parser.add_argument('--count', type=int, default=None,
                        help='预览出场数量（仅 --schedule 时生效）')
    parser.set_defaults(open_browser=True)
    return parser.parse_args(argv)


def _prepare_webview_env():
    """让被遮挡的窗口继续渲染（否则切到场景小窗时打印会停）。"""
    flags = os.environ.get('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', '')
    flags += (' --disable-backgrounding-occluded-windows --disable-renderer-backgrounding'
              ' --disable-background-timer-throttling')
    if CAPTURE_COMPAT_FILE.exists():
        flags += ' --disable-gpu --disable-accelerated-video-decode'
    os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = flags


def open_in_browser(url):
    """用系统默认浏览器打开本地页面。纯服务模式下的入口，比依赖窗口后端更可靠。"""
    try:
        if IS_MAC:
            subprocess.Popen(['open', url])
        elif IS_WIN:
            os.startfile(url)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(['xdg-open', url])
        return True
    except Exception:
        return False


def _run_schedule(args):
    """打印指定内容包的出场顺序预览（不启动服务）。"""
    from . import storage, scheduler as _sched

    ids = list(args.schedule)
    if not ids:
        ids = [p['id'] for p in storage.list_packs()]
        if not ids:
            print('data/packs 中没有任何内容包。')
            print('先运行：python -m printcast --seed  写入内置示例包。')
            return
        print('未指定包，预览全部 %d 个内容包（concat 组合）：' % len(ids))

    packs, missing = [], []
    for pid in ids:
        pack = storage.get_pack(pid) if storage.valid_pack_id(pid) else None
        if pack is None:
            missing.append(pid)
        else:
            packs.append(pack)
    if missing:
        print('内容包不存在：', missing)
        return

    sched = _sched.ContentScheduler(packs, strategy=args.strategy)
    if args.mode:
        sched.mode = args.mode
    print('出场模式: %s   组合策略: %s   loop: %s'
          % (sched.mode, sched.strategy, sched.loop))
    print('%-4s %-18s %-10s %s' % ('序', '名称', '来自包', '播报文案'))
    print('-' * 60)
    # plan() 返回的是预览字典（无 index 字段），序号由这里按输出顺序生成。
    # 早期直接读 ap['index'] 会让 --schedule 命令必崩 KeyError。
    for seq, ap in enumerate(sched.plan(args.count), 1):
        print('%-4s %-18s %-10s %s'
              % (seq, ap['name'], ap['packId'], (ap['speech'] or '')[:24]))


def _run_db(action, overwrite=False):
    """SQLite 维护命令：状态 / 自检 / JSON 导入导出。"""
    from . import db

    if action == 'info':
        info = db.stats()
        print('数据源   :', info['backend'], '· schema v%d' % info['schemaVersion'])
        print('库文件   :', info['dbPath'], '（%d 字节）' % info['sizeBytes'])
        print('完整性   :', info['integrity'])
        print('表行数   :', ', '.join('%s=%d' % kv for kv in info['tables'].items()))
        if info['migratedFrom']:
            print('首次迁移 :', info['migratedAt'], info['migratedFrom'])
        return 0
    if action == 'verify':
        result = db.verify()
        print('完整性   :', '通过' if result['ok'] else '失败')
        for line in result['checks']:
            print('  ·', line)
        for err in result['errors']:
            print('  !', err, file=sys.stderr)
        return 0 if result['ok'] else 1
    if action == 'import':
        result = db.import_json(overwrite=overwrite)
        print('从 data/ JSON 导入：内容包 %d，跳过 %d，设置 %d，媒体 %d'
              % (result['packs'], result['skipped'],
                 result['settings'], result['media']))
        for err in result['errors']:
            print('  !', err, file=sys.stderr)
        return 1 if result['errors'] else 0
    result = db.export_json()
    print('已导出 JSON 镜像：内容包 %d 个，媒体 %d 条，设置 %s'
          % (len(result['packs']), result['media'],
             '有' if result['settings'] else '无'))
    return 0


def _serve_only(url, args):
    print(f'printcast 服务已启动：{url}', flush=True)
    print(f'  主页   {url}web/index.html', flush=True)
    print(f'  英文   {url}web/index-en.html', flush=True)
    print(f'  直播间 {url}web/live.html', flush=True)
    print('  Ctrl+C 停止服务', flush=True)
    target = (url + 'web/live.html') if args.room else (url + 'web/index.html')
    if args.open_browser:
        if open_in_browser(target):
            print(f'已在默认浏览器中打开 {target}', flush=True)
        else:
            print(f'未能自动打开浏览器，请手动访问 {target}', flush=True)
    threading.Event().wait()


def main(argv=None):
    args = parse_args(argv)

    if args.db:
        return _run_db(args.db, args.overwrite)

    if args.seed:
        from . import db, samples
        # 先确保库已建好并完成首次迁移，避免 --seed 与迁移互相覆盖。
        db.ensure_db()
        result = samples.seed_builtin_packs(overwrite=args.overwrite)
        print('原始示例包已写入 SQLite，并同步落盘到 data/packs/：')
        print('  新增 :', result['written'] or '（无）')
        print('  跳过 :', result['skipped'] or '（无）')
        if result['errors']:
            print('  失败 :', result['errors'])
        info = db.stats()
        print('  库内 : packs=%d characters=%d · %s'
              % (info['tables']['packs'], info['tables']['characters'], info['dbPath']))
        return 1 if result['errors'] else 0

    if args.schedule is not None:
        _run_schedule(args)
        return 0

    if args.scene_view:
        from .desktop import run_scene_view
        url, _ = ensure_server(args.port)
        run_scene_view(url.rstrip('/'), args.scene_orient)
        return 0

    if args.live_room:
        from .desktop import run_live_room
        run_live_room(args.live_room)
        return 0

    _prepare_webview_env()
    url, server = ensure_server(args.port)
    from .desktop import DesktopApi, _require_webview
    api = DesktopApi(url)
    try:
        if args.server_only:
            _serve_only(url, args)
        else:
            webview = _require_webview()
            webview.create_window('头像打印机 · 桌面版', url, js_api=api,
                                  width=1380, height=860, min_size=(900, 650),
                                  background_color='#0b0e14')

            def start_requested_room():
                if not args.room:
                    return
                try:
                    print(api.open_live_room(args.room), flush=True)
                    if args.capture:
                        for _ in range(30):
                            if listening(LIVE_DEBUG_PORT):
                                try:
                                    print(api.start_capture(args.room), flush=True)
                                    return
                                except (OSError, RuntimeError):
                                    pass
                            threading.Event().wait(1)
                        print('直播窗口未就绪，请完成登录后点击开始抓取', flush=True)
                except Exception as exc:
                    print(str(exc), flush=True)

            webview.start(start_requested_room, gui=WEBVIEW_GUI, private_mode=False,
                          storage_path=str(ROOT / '.printer-webview-profile'))
    except KeyboardInterrupt:
        pass
    finally:
        api.close()
        if server:
            server.shutdown()
            server.server_close()
        if api.restart_requested:
            restart = [sys.executable, '-m', 'printcast']
            if api._room:
                restart += ['--room', api._room]
            subprocess.Popen(restart, cwd=ROOT)
    return 0
