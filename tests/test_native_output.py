"""Native WebView output integration check（手动运行，不参与 pytest 收集）。

用法（需先关闭正式程序，且已安装桌面依赖）：
    python tests/test_native_output.py            # 主窗口检查
    python tests/test_native_output.py --viewer    # 场景小窗检查（由主进程拉起）

这是需要真实 GPU 与 WebView2/WebKit 窗口的端到端检查，普通 `pytest` 不会执行它：
模块顶层无副作用，只有 `__main__` 才启动窗口。
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from printcast.config import ROOT, WEBVIEW_GUI
from printcast.server import ensure_server


def main():
    try:
        import webview
    except ImportError:
        print('需要桌面依赖：pip install -e ".[desktop]"', file=sys.stderr)
        return 2

    os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = (
        '--disable-backgrounding-occluded-windows --disable-renderer-backgrounding '
        '--disable-background-timer-throttling')

    out = ROOT / '.output-test'
    out.mkdir(exist_ok=True)
    viewer = '--viewer' in sys.argv
    url = 'http://127.0.0.1:8080/web/' + ('live-view.html' if viewer else 'index.html')
    server = None
    if not viewer:
        for name in ('viewer.json', 'portrait.json', 'resize.request', 'main.json', 'viewer-error.json'):
            (out / name).unlink(missing_ok=True)
        url_root, server = ensure_server()
        url = url_root + 'web/' + ('live-view.html' if viewer else 'index.html')

    window = webview.create_window(
        'Output integration ' + ('viewer' if viewer else 'main'),
        url, width=1000, height=750)
    results = []
    failed = False

    def evaluate(code):
        return window.evaluate_js(code)

    def wait(code, timeout=35):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            try:
                result = evaluate(code)
                if result:
                    return result
            except Exception:
                pass
            time.sleep(.3)
        raise AssertionError('Timed out: ' + code)

    def run():
        nonlocal failed
        child = None
        try:
            wait("document.readyState==='complete'")
            evaluate("['wheel','pointerdown','pointermove','pointerup','keydown','click'].forEach("
                     "type=>document.addEventListener(type,e=>{if(e.isTrusted){"
                     "e.stopImmediatePropagation();e.preventDefault()}},{capture:true,passive:false}))")
            if viewer:
                state = wait("(()=>{const v=document.querySelector('video');return "
                             "v.readyState>=2&&v.videoWidth?{w:v.videoWidth,h:v.videoHeight}:null})()", 50)
                time.sleep(3)
                image = evaluate("(()=>{const v=document.querySelector('video'),"
                                 "c=document.createElement('canvas');c.width=v.videoWidth;"
                                 "c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);"
                                 "return c.toDataURL('image/png')})()")
                (out / 'frame.png').write_bytes(base64.b64decode(image.split(',')[1]))
                before = evaluate("document.querySelector('video').getVideoPlaybackQuality().totalVideoFrames")
                evaluate("document.querySelector('#interaction').dispatchEvent(new WheelEvent("
                         "'wheel',{deltaY:320,bubbles:true,cancelable:true,clientX:400,clientY:300}))")
                time.sleep(5)
                after = evaluate("document.querySelector('video').getVideoPlaybackQuality().totalVideoFrames")
                state.update(frames=after - before,
                             canvasCount=evaluate("document.querySelectorAll('canvas').length"))
                assert after > before, 'Video frozen'
                (out / 'viewer.json').write_text(json.dumps(state))
                until = time.monotonic() + 30
                while not (out / 'resize.request').exists() and time.monotonic() < until:
                    time.sleep(.2)
                wait("document.querySelector('video').videoWidth===1080&&"
                     "document.querySelector('video').videoHeight===1920")
                before = evaluate("document.querySelector('video').getVideoPlaybackQuality().totalVideoFrames")
                time.sleep(5)
                after = evaluate("document.querySelector('video').getVideoPlaybackQuality().totalVideoFrames")
                assert after > before, 'Portrait video froze'
                (out / 'portrait.json').write_text(json.dumps(
                    {'width': 1080, 'height': 1920, 'framesOverFiveSeconds': after - before}))
                time.sleep(15)
            else:
                wait("typeof window.printerDiagnostics==='function'")
                time.sleep(3)
                original = evaluate('window.printerDiagnostics()')
                for aa in ['off', 'msaa2', 'msaa4', 'msaa8', 'ssaa15', 'ssaa2']:
                    evaluate("(()=>{const s=document.querySelector('#antialias-mode');s.value=" +
                             json.dumps(aa) + ";s.dispatchEvent(new Event('change'))})()")
                    time.sleep(.5)
                    state = evaluate('window.printerDiagnostics()')
                    assert all(abs(a - b) < 1e-7 for a, b in zip(state['camera'], original['camera'])), \
                        {'original': original, 'new': state}
                    assert state['output'] == [1280, 720], state
                    assert state['internal'][0] <= 2560, state
                    results.append(state)
                evaluate("(()=>{const s=document.querySelector('#visual-preset');"
                         "s.value='high';s.dispatchEvent(new Event('change'))})()")
                child = subprocess.Popen([sys.executable, __file__, '--viewer'], cwd=ROOT)
                wait("window.printerDiagnostics().connected==='connected'", 50)
                time.sleep(12)
                assert (out / 'viewer.json').exists(), 'Viewer did not produce report'
                assert evaluate("getComputedStyle(document.querySelector('#stage')).display") == 'none'
                assert evaluate('window.printerDiagnostics().camera') != original['camera'], \
                    'Wheel did not move camera'
                results.append({'stream': json.loads((out / 'viewer.json').read_text()),
                                'main': evaluate('window.printerDiagnostics()')})
                evaluate("(()=>{const s=document.querySelector('#output-resolution');"
                         "s.value='portrait-1080p';s.dispatchEvent(new Event('change'));"
                         "const fps=document.querySelector('#target-fps');fps.value='30';"
                         "fps.dispatchEvent(new Event('change'))})()")
                (out / 'resize.request').write_text('portrait')
                until = time.monotonic() + 25
                while not (out / 'portrait.json').exists() and time.monotonic() < until:
                    time.sleep(.3)
                assert (out / 'portrait.json').exists(), 'Portrait resize did not reach receiver'
                results.append({'portrait': json.loads((out / 'portrait.json').read_text()),
                                'main': evaluate('window.printerDiagnostics()')})
                assert evaluate('window.printerDiagnostics().output') == [1080, 1920]
                errors = evaluate('window.__pageErrors||[]')
                assert not errors, errors
                child.terminate()
                child.wait(timeout=10)
                child = None
                wait("getComputedStyle(document.querySelector('#stage')).display!=='none'", 20)
                results.append({'restored': True})
            (out / ('viewer-done.json' if viewer else 'main.json')).write_text(
                json.dumps({'ok': True, 'results': results}, ensure_ascii=False, indent=2),
                encoding='utf-8')
        except Exception as exc:
            failed = True
            (out / ('viewer-error.json' if viewer else 'main.json')).write_text(
                json.dumps({'ok': False, 'error': str(exc), 'results': results},
                           ensure_ascii=False, indent=2), encoding='utf-8')
        finally:
            if child:
                child.terminate()
            window.destroy()

    webview.start(run, gui=WEBVIEW_GUI, private_mode=False,
                  storage_path=tempfile.mkdtemp(prefix='printer-output-' + ('viewer' if viewer else 'main')))
    if server:
        server.shutdown()
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
