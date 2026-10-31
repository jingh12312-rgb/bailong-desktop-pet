"""Linux desktop integration with explicit Wayland capability boundaries.

X11 (including Xwayland) is preferred for a freely movable Qt desktop pet.
Native Wayland does not expose a portable global window-position/fullscreen API.
"""

import os
import re
import shutil
import subprocess
import sys
import time


_LAST_FULLSCREEN_CHECK = (0.0, False)


def configure_qpa():
    """Choose Qt's XCB backend before any PySide6 module is imported.

    Explicit QT_QPA_PLATFORM always wins. On Wayland, use Xwayland when a
    DISPLAY is available; native Wayland cannot reliably position the pet.
    BAILONG_QPA_MODE=wayland|xcb|auto allows explicit control.
    """
    if not sys.platform.startswith('linux') or os.environ.get('QT_QPA_PLATFORM'):
        return
    mode = os.environ.get('BAILONG_QPA_MODE', 'auto').strip().lower()
    if mode not in ('auto', 'xcb', 'wayland'):
        raise ValueError('BAILONG_QPA_MODE 只能是 auto、xcb 或 wayland')
    if mode == 'xcb' or mode == 'auto' and os.environ.get('WAYLAND_DISPLAY') and os.environ.get('DISPLAY'):
        os.environ['QT_QPA_PLATFORM'] = 'xcb'
    elif mode == 'wayland':
        os.environ['QT_QPA_PLATFORM'] = 'wayland'


def is_native_wayland():
    if not sys.platform.startswith('linux'):
        return False
    backend = os.environ.get('QT_QPA_PLATFORM', '').lower()
    return backend.startswith('wayland') or (not backend and bool(os.environ.get('WAYLAND_DISPLAY')))


def is_wayland_session():
    return os.environ.get('XDG_SESSION_TYPE', '').lower() == 'wayland' or bool(os.environ.get('WAYLAND_DISPLAY'))


def _query_xprop(arguments):
    try:
        proc = subprocess.run(['xprop', *arguments], capture_output=True,
                              text=True, timeout=.35, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ''
    return proc.stdout if proc.returncode == 0 else ''


def x11_active_fullscreen():
    """Check EWMH foreground-window fullscreen state, never enumerate users.

    Native Wayland windows are not visible to xprop (even via Xwayland), so
    this feature is disabled on any Wayland session to avoid false confidence.
    """
    if is_wayland_session() or is_native_wayland() or not os.environ.get('DISPLAY'):
        return False
    if not shutil.which('xprop'):
        return False
    root = _query_xprop(['-root', '_NET_ACTIVE_WINDOW'])
    match = re.search(r'window id\s*#\s*(0x[0-9a-f]+)', root, re.IGNORECASE)
    if not match or int(match.group(1), 16) == 0:
        return False
    properties = _query_xprop(['-id', match.group(1), '_NET_WM_STATE', '_NET_WM_PID'])
    pid = re.search(r'_NET_WM_PID\(CARDINAL\)\s*=\s*(\d+)', properties)
    if pid and int(pid.group(1)) == os.getpid():
        return False
    return '_NET_WM_STATE_FULLSCREEN' in properties


def linux_fullscreen():
    """Throttle external X11 queries so the Qt paint loop stays responsive."""
    global _LAST_FULLSCREEN_CHECK
    now = time.monotonic()
    when, value = _LAST_FULLSCREEN_CHECK
    if now - when < 1.0:
        return value
    value = x11_active_fullscreen()
    _LAST_FULLSCREEN_CHECK = (now, value)
    return value


def platform_notes():
    if is_wayland_session():
        return 'Wayland：已优先选择 Xwayland（若可用）；原生 Wayland 的任意拖动、置顶及自动全屏检测受合成器限制。'
    return 'X11：支持标准 EWMH 前台全屏检测（需安装 xprop）。'


def fullscreen_capability():
    if is_wayland_session() or is_native_wayland():
        return False,'Wayland 会话不能通过标准 X11 接口读取所有应用的全屏状态。请手动隐藏桌宠。'
    if not os.environ.get('DISPLAY') or not shutil.which('xprop'):
        return False,'X11 自动全屏隐藏需要 DISPLAY 和 xprop。'
    return True,''


def diagnostics(root):
    import importlib.util
    from pathlib import Path
    from video_frames import ffmpeg_path
    assets=Path(root)/'outputs/白龙桌宠素材'
    report={'platform':sys.platform,'python':sys.version.split()[0],
            'desktop_session':os.environ.get('XDG_SESSION_TYPE','unknown'),
            'has_display':bool(os.environ.get('DISPLAY')),
            'has_wayland_display':bool(os.environ.get('WAYLAND_DISPLAY')),
            'qt_backend_override':os.environ.get('QT_QPA_PLATFORM'),
            'dependencies':{name:importlib.util.find_spec(name) is not None for name in ('PIL','psutil','PySide6')},
            'ffmpeg':False,'ffmpeg_libvpx_vp9_decoder':False,
            'assets_manifest':(assets/'素材清单.json').is_file(),
            'assets_required':0,'assets_present':0,'missing_assets':[],
            'fullscreen_supported':fullscreen_capability()[0],
            'warnings':[platform_notes()]}
    try:
        executable=ffmpeg_path();report['ffmpeg']=executable
        proc=subprocess.run([executable,'-hide_banner','-decoders'],capture_output=True,text=True,timeout=10)
        report['ffmpeg_libvpx_vp9_decoder']=proc.returncode==0 and 'libvpx-vp9' in proc.stdout
    except (OSError,RuntimeError,subprocess.TimeoutExpired) as error:report['warnings'].append(str(error))
    if report['assets_manifest']:
        import json
        try:
            data=json.loads((assets/'素材清单.json').read_text(encoding='utf-8'))
            items=[data['idle']]+data.get('additionalIdleAnimations',[])+data['variants']
            items += [x for x in data.get('workAnimations',[])+data.get('movementAnimations',[]) if x]
            items += [data[k] for k in ('dragAnimation','landingAnimation','quotaAnimation') if data.get(k)]
            names={item.get('playbackFile') or item['file'].replace('.webm','.webp') for item in items}
            names.update(item['returnTransition']['file'] for item in items if item.get('returnTransition'))
            report['assets_required']=len(names)
            report['missing_assets']=sorted(n for n in names if not (assets/n).is_file())
            report['assets_present']=len(names)-len(report['missing_assets'])
        except (OSError,KeyError,ValueError,TypeError) as error:report['warnings'].append('素材清单无效：'+str(error))
    report['ready_for_gui_test']=bool(all(report['dependencies'].values()) and report['ffmpeg_libvpx_vp9_decoder'] and report['assets_required'] and not report['missing_assets'] and (report['has_display'] or report['has_wayland_display']))
    return report
