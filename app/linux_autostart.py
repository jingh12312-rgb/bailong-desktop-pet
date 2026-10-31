"""Per-user Linux autostart via XDG or systemd --user (never system-wide)."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import psutil
import shutil
import subprocess
import sys
import time
from datetime import datetime

NAME = 'bailong-pet-monitor'
DEFAULT_PROCESSES = ('chatgpt', 'chatgpt-desktop', 'codex-desktop',
                     'codex-gui', 'openai-codex')


def _xdg_dir(variable, default):
    value = os.environ.get(variable, '')
    path = Path(value).expanduser() if value else None
    return path if path is not None and path.is_absolute() else Path.home() / default


def configuration_dir():
    return _xdg_dir('XDG_CONFIG_HOME', '.config') / 'BailongPet'


def xdg_entry():
    return _xdg_dir('XDG_CONFIG_HOME', '.config') / 'autostart' / f'{NAME}.desktop'


def systemd_entry():
    return _xdg_dir('XDG_CONFIG_HOME', '.config') / 'systemd/user' / f'{NAME}.service'


def _state_dir():
    from platform_support import state_root
    return state_root() / 'app'


def _state_file():
    return _state_dir() / '自启动状态.json'


def _preferences_file():
    return configuration_dir() / 'autostart.json'


def _setting():
    try:
        data = json.loads(_preferences_file().read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, OSError, ValueError):
        return {}


def launch_trigger():
    return os.environ.get('BAILONG_AUTOSTART_TRIGGER') or _setting().get('trigger', 'codex')


def command():
    if getattr(sys, 'frozen', False):
        return [str(Path(sys.executable).absolute()), '--autostart']
    return [str(Path(sys.executable).absolute()), str(Path(__file__).resolve().with_name('autostart.py'))]


def _quote_arg(arg):
    """Safely quote one argument under Desktop Entry Exec/systemd ExecStart grammar."""
    arg = str(arg)
    if not arg or any(c in arg for c in '\r\n\x00'):
        raise ValueError('无效的自动启动命令参数')
    # The % character is a field code in .desktop files; %% is a literal %.
    quoted='"' + arg.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`').replace('%', '%%') + '"'
    # Desktop values are unescaped once before Exec argument quoting is parsed.
    return quoted.replace('\\','\\\\')


def _quote_systemd_arg(arg):
    arg = str(arg)
    if any(c in arg for c in '\r\n\x00'):
        raise ValueError('无效的 systemd 命令参数')
    # In unit files, a literal percent sign must be escaped as %%.
    return '"' + arg.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$','$$') + '"'


def _desktop_text():
    args = ' '.join(_quote_arg(arg) for arg in command())
    return ('[Desktop Entry]\nType=Application\nVersion=1.0\n'
            'Name=BailongPet Codex watcher\n'
            'Comment=Start BailongPet when Codex desktop opens\n'
            f'Exec={args}\nTerminal=false\nNoDisplay=true\n'
            'X-GNOME-Autostart-enabled=true\n')


def _service_text():
    args = ' '.join(_quote_systemd_arg(arg) for arg in command())
    return ('[Unit]\nDescription=BailongPet desktop autostart monitor\n'
            'After=graphical-session.target\nPartOf=graphical-session.target\n'
            '[Service]\nType=simple\n'
            f'ExecStart={args}\nRestart=on-failure\nRestartSec=3\n'
            '[Install]\nWantedBy=graphical-session.target\n')


def _systemctl(*args, check=True):
    try:
        return subprocess.run(['systemctl', '--user', *args], check=check,
                              capture_output=True, text=True, timeout=12)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('systemd --user 不可用。请改用 XDG 自启动；详情：' + str(exc)) from exc


def _stop_systemd():
    if systemd_entry().exists():
        _systemctl('disable', '--now', f'{NAME}.service', check=False)
        systemd_entry().unlink(missing_ok=True)
        _systemctl('daemon-reload', check=False)


def _stop_monitor():
    """Stop only the exact monitor that was recorded by this installation."""
    try:
        state = json.loads(_state_file().read_text(encoding='utf-8'))
        pid = state.get('pid')
        if not isinstance(pid, int) or pid <= 0:
            return
        created=state.get('createTime')
        if not isinstance(created,(float,int)):return
        proc = psutil.Process(pid)
        if abs(proc.create_time()-created)>.01:return
        args = proc.cmdline()
        expected = command()
        if (args[:len(expected)] == expected or
                len(args) >= 2 and args[0] == expected[0] and args[1:] == ['--autostart']):
            proc.terminate()
            try:proc.wait(timeout=2)
            except psutil.TimeoutExpired:raise RuntimeError('监视器尚未退出，请稍后复查。')
    except (OSError, ValueError, KeyError, psutil.Error):
        return


def enabled():
    return xdg_entry().is_file() or systemd_entry().is_file()


def enable(backend='xdg', trigger='codex', process_names=None):
    if not sys.platform.startswith('linux'):
        raise RuntimeError('此功能仅用于 Linux')
    if backend not in ('xdg', 'systemd'):
        raise ValueError('backend 只能是 xdg 或 systemd')
    if trigger not in ('codex', 'session'):
        raise ValueError('trigger 只能是 codex 或 session')
    directory = configuration_dir()
    directory.mkdir(parents=True, exist_ok=True)
    settings = _setting()
    settings['trigger'] = trigger
    if process_names is not None:
        if not isinstance(process_names, str) or len(process_names) > 500:
            raise ValueError('进程名称列表无效或过长')
        settings['process_names'] = process_names
    _preferences_file().write_text(json.dumps(settings, indent=2), encoding='utf-8')
    if backend == 'xdg':
        _stop_systemd()
        entry = xdg_entry()
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(_desktop_text(), encoding='utf-8')
    else:
        if not shutil.which('systemctl'):
            raise RuntimeError('未安装 systemctl，建议使用 XDG 自启动')
        _stop_monitor()  # Release the singleton lock before activating the service.
        entry = systemd_entry()
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(_service_text(), encoding='utf-8')
        try:
            # Import the current desktop session environment where supported.
            keys = [k for k in ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_SESSION_TYPE',
                                'XDG_CURRENT_DESKTOP', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS')
                    if os.environ.get(k)]
            if keys:
                _systemctl('import-environment', *keys)
            _systemctl('daemon-reload')
            _systemctl('enable', '--now', f'{NAME}.service')
        except Exception:
            entry.unlink(missing_ok=True)
            _systemctl('daemon-reload', check=False)
            raise
        xdg_entry().unlink(missing_ok=True)
    return entry


def disable():
    xdg_entry().unlink(missing_ok=True)
    _stop_systemd()
    _stop_monitor()
    _preferences_file().unlink(missing_ok=True)


def gpt_is_open():
    """Find an interactive desktop application, not arbitrary Codex CLI calls.

    Set BAILONG_TRIGGER_PROCESS to a comma-separated list to support other
    desktop wrappers; comparisons are exact basenames, not substring matches.
    """
    names = os.environ.get('BAILONG_TRIGGER_PROCESS') or _setting().get('process_names')
    allowed = {n.strip().lower() for n in names.split(',') if n.strip()} if isinstance(names, str) and names else set(DEFAULT_PROCESSES)
    for process in psutil.process_iter(['name', 'exe', 'cmdline']):
        try:
            info = process.info
            candidates = [info.get('name'), Path(info.get('exe') or '').name]
            cmdline = info.get('cmdline') or []
            if any(arg.startswith('--type=') for arg in cmdline):continue
            if cmdline:
                candidates.append(Path(cmdline[0]).name)
            if any(n and n.lower() in allowed for n in candidates):
                return True
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
            continue
    return False


def _save_state(state):
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def monitor(poll_seconds=2):
    """One monitor per user, wake once on absent->present transition."""
    directory = _state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / 'monitor.lock'
    with lock.open('a+b') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        from autostart import launch_pet
        state = {'pid': os.getpid(), 'createTime':psutil.Process().create_time(),
                 'started': datetime.now().isoformat(timespec='seconds')}
        previous = False
        trigger = launch_trigger()
        while True:
            # launch_pet returns a PID. Reap only that known child, not another app.
            if state.get('petPid'):
                try:os.waitpid(state['petPid'],os.WNOHANG)
                except ChildProcessError:pass
            current = trigger == 'session' or gpt_is_open()
            if current and not previous:
                try:
                    pid = launch_pet()
                    state.update(petPid=pid, lastLaunch=datetime.now().isoformat(timespec='seconds'))
                    state.pop('error', None)
                except Exception as exc:
                    state['error'] = str(exc)
            if current != previous or 'gptOpen' not in state:
                state['gptOpen'] = current
                _save_state(state)
            previous = current
            time.sleep(poll_seconds)


def main(argv=None):
    p = argparse.ArgumentParser(description='BailongPet per-user Linux desktop autostart')
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--enable', action='store_true')
    group.add_argument('--disable', action='store_true')
    group.add_argument('--status', action='store_true')
    group.add_argument('--monitor', action='store_true')
    p.add_argument('--backend', choices=('xdg', 'systemd'), default='xdg')
    p.add_argument('--trigger', choices=('codex', 'session'), default='codex')
    p.add_argument('--process-names', default=None, help='逗号分隔的 Linux 桌面进程名，持久保存')
    args = p.parse_args(argv)
    if args.enable:
        path = enable(args.backend, args.trigger, args.process_names)
        print(f'已启用 {args.backend} 自启动：{path}（触发方式：{args.trigger}）')
    elif args.disable:
        disable()
        print('已关闭当前用户的桌宠自动启动')
    elif args.status:
        print(json.dumps({'enabled': enabled(), 'backend': ('systemd' if systemd_entry().exists() else 'xdg' if xdg_entry().exists() else None),
                          'trigger': launch_trigger()}, ensure_ascii=False))
    else:
        return monitor()
    return 0


if __name__ == '__main__':
    sys.exit(main())
