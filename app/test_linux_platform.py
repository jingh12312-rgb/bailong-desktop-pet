"""Unit tests run without PySide6, animations, network or a running desktop."""

import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

if not sys.platform.startswith('linux'):
    raise unittest.SkipTest('Linux-only portability tests')

sys.path.insert(0, str(Path(__file__).resolve().parent))

import linux_autostart as a
import linux_support as s


class LinuxSupportTests(unittest.TestCase):
    def test_wayland_xwayland_prefers_xcb(self):
        with patch.dict(os.environ, {'WAYLAND_DISPLAY':'wayland-0', 'DISPLAY':':1', 'BAILONG_QPA_MODE':'auto'}, clear=True):
            s.configure_qpa()
            self.assertEqual(os.environ.get('QT_QPA_PLATFORM'), 'xcb')

    def test_native_wayland_option(self):
        with patch.dict(os.environ, {'WAYLAND_DISPLAY':'wayland-0', 'BAILONG_QPA_MODE':'wayland'}, clear=True):
            s.configure_qpa()
            self.assertEqual(os.environ.get('QT_QPA_PLATFORM'), 'wayland')

    def test_respect_existing_qt_option(self):
        with patch.dict(os.environ, {'WAYLAND_DISPLAY':'wayland-0', 'DISPLAY':':1', 'QT_QPA_PLATFORM':'offscreen'}, clear=True):
            s.configure_qpa()
            self.assertEqual(os.environ.get('QT_QPA_PLATFORM'), 'offscreen')

    def test_bad_backend_rejected(self):
        with patch.dict(os.environ, {'BAILONG_QPA_MODE':'unsafe-mode'}, clear=True):
            with self.assertRaises(ValueError):
                s.configure_qpa()

    def test_no_cross_app_fullscreen_detection_wayland(self):
        with patch.dict(os.environ, {'WAYLAND_DISPLAY':'wayland-0', 'DISPLAY':':1'}, clear=True):
            with patch.object(s, '_query_xprop') as run:
                self.assertFalse(s.x11_active_fullscreen())
                run.assert_not_called()

    def test_x11_ewmh_fullscreen(self):
        x = ('_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3e0000c',
             '_NET_WM_STATE(ATOM) = _NET_WM_STATE_FULLSCREEN\n_NET_WM_PID(CARDINAL) = 123456789')
        with patch.dict(os.environ, {'XDG_SESSION_TYPE':'x11','DISPLAY':':0'}, clear=True), \
             patch.object(s.shutil, 'which', return_value='/usr/bin/xprop'), \
             patch.object(s, '_query_xprop', side_effect=x):
            self.assertTrue(s.x11_active_fullscreen())

    def test_own_fullscreen_window_is_not_foreign(self):
        x = ('_NET_ACTIVE_WINDOW(WINDOW): window id # 0x42001',
             f'_NET_WM_STATE(ATOM) = _NET_WM_STATE_FULLSCREEN\n_NET_WM_PID(CARDINAL) = {os.getpid()}')
        with patch.dict(os.environ, {'XDG_SESSION_TYPE':'x11','DISPLAY':':0'}, clear=True), \
             patch.object(s.shutil, 'which', return_value='/usr/bin/xprop'), \
             patch.object(s, '_query_xprop', side_effect=x):
            self.assertFalse(s.x11_active_fullscreen())

    def test_missing_xprop_or_display_is_safe(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(s.x11_active_fullscreen())

    def test_fullscreen_cache(self):
        s._LAST_FULLSCREEN_CHECK = (0.0, False)
        with patch.object(s, 'x11_active_fullscreen', return_value=True) as call:
            self.assertTrue(s.linux_fullscreen())
            self.assertTrue(s.linux_fullscreen())
            self.assertEqual(call.call_count, 1)


class AutostartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'HOME': self.tmp.name,
                            'XDG_CONFIG_HOME': str(Path(self.tmp.name)/'config'),
                            'XDG_STATE_HOME': str(Path(self.tmp.name)/'state')}, clear=True)
        self.env.start(); self.addCleanup(self.env.stop)
        # Path.home() reads os.environ HOME; container uses the normal os.path.expanduser.
        self.state_patch = patch.object(a, '_state_dir', return_value=Path(self.tmp.name)/'state/BailongPet/app')
        self.state_patch.start(); self.addCleanup(self.state_patch.stop)

    def test_xdg_generated_without_shell_injection(self):
        with patch.object(a, 'command', return_value=['/home/a b/venv/bin/python','/home/a b/app/autostart.py']):
            text = a._desktop_text()
            self.assertIn('Exec="/home/a b/venv/bin/python" "/home/a b/app/autostart.py"',text)
            self.assertNotIn('sh -c', text)
            self.assertIn('NoDisplay=true', text)

    def test_xdg_quote_dangerous_filename(self):
        value=a._quote_arg('/home/user/dir $PATH;%test"file')
        self.assertIn('\\$PATH', value)
        self.assertIn('%%test', value)
        self.assertIn('\\"file', value)

    def test_xdg_install_disable_no_root_access(self):
        with patch.object(a, '_stop_systemd') as stop, patch.object(a, '_stop_monitor'):
            entry=a.enable('xdg','session')
            self.assertTrue(entry.exists())
            self.assertTrue(str(entry).startswith(self.tmp.name))
            self.assertTrue(a.enabled())
            self.assertEqual(a.launch_trigger(), 'session')
            a.disable()
            self.assertFalse(a.enabled())
            self.assertFalse(a._preferences_file().exists())

    def test_invalid_trigger_rejected(self):
        with self.assertRaises(ValueError): a.enable('xdg','unsafe')

    def test_code_cli_is_not_considered_desktop_by_default(self):
        proc=MagicMock();proc.info={'name':'codex','exe':'/usr/bin/codex', 'cmdline':['codex','app-server']}
        with patch.object(a.psutil, 'process_iter', return_value=[proc]):
            self.assertFalse(a.gpt_is_open())

    def test_process_names_can_be_persisted_for_next_login(self):
        with patch.object(a, '_stop_systemd'):
            a.enable('xdg', 'codex', 'chatgpt-qt, special-pet')
        proc=MagicMock();proc.info={'name':'special-pet','exe':'/opt/special-pet','cmdline':['/opt/special-pet']}
        with patch.object(a.psutil, 'process_iter', return_value=[proc]):
            self.assertTrue(a.gpt_is_open())

    def test_user_process_names_can_be_configured(self):
        proc=MagicMock();proc.info={'name':'my-app','exe':'/opt/my-app', 'cmdline':['/opt/my-app']}
        with patch.dict(os.environ, {'BAILONG_TRIGGER_PROCESS':'my-app, another-app'}), \
             patch.object(a.psutil, 'process_iter', return_value=[proc]):
            self.assertTrue(a.gpt_is_open())

    def test_monitor_acquires_lock_and_records_state(self):
        launch = MagicMock(return_value=1234)
        with patch.object(a, 'launch_trigger', return_value='codex'), \
             patch.object(a, 'gpt_is_open', return_value=True), \
             patch.dict(sys.modules, {'autostart': types.SimpleNamespace(launch_pet=launch)}), \
             patch.object(a.time, 'sleep', side_effect=StopIteration):
            with self.assertRaises(StopIteration): a.monitor()
            self.assertTrue(launch.called)
            state=json.loads(a._state_file().read_text())
            self.assertEqual(state['petPid'], 1234)
            self.assertTrue(state['gptOpen'])

    def test_bad_saved_pid_does_not_kill(self):
        a._state_file().parent.mkdir(parents=True, exist_ok=True)
        a._state_file().write_text(json.dumps({'pid':os.getpid()}))
        with patch.object(a.psutil, 'Process') as proc:
            proc.return_value.cmdline.return_value=['/bin/bash','other_script']
            a._stop_monitor()
            proc.return_value.terminate.assert_not_called()

    def test_command_preserves_virtualenv_python_symlink(self):
        with patch.object(a.sys,'executable','/home/space pet/.venv/bin/python'), \
             patch.object(a.sys,'frozen',False,create=True):
            self.assertEqual(a.command()[0], '/home/space pet/.venv/bin/python')

    def test_systemd_backend_writes_user_service_and_removes_xdg(self):
        with patch.object(a, '_stop_systemd'), patch.object(a, '_stop_monitor') as stop, \
             patch.object(a.shutil, 'which', return_value='/usr/bin/systemctl'), \
             patch.object(a, '_systemctl', return_value=MagicMock()):
            a.enable('xdg', 'codex')
            self.assertTrue(a.xdg_entry().exists())
            a.enable('systemd', 'session')
            self.assertTrue(a.systemd_entry().exists())
            self.assertFalse(a.xdg_entry().exists())
            self.assertTrue(stop.called)
            self.assertEqual(a.launch_trigger(), 'session')

    def test_systemd_error_removes_invalid_service_file(self):
        with patch.object(a, '_stop_monitor'), \
             patch.object(a.shutil, 'which', return_value='/usr/bin/systemctl'), \
             patch.object(a, '_systemctl', side_effect=[RuntimeError('systemctl unreachable'), MagicMock()]):
            with self.assertRaises(RuntimeError):
                a.enable('systemd', 'session')
            self.assertFalse(a.systemd_entry().exists())

    def test_second_monitor_respects_singleton_lock(self):
        import fcntl
        state_dir=a._state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)
        with (state_dir/'monitor.lock').open('a+b') as file:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(a, 'gpt_is_open') as detect:
                self.assertEqual(a.monitor(), 0)
                detect.assert_not_called()

    def test_session_launch_does_not_need_desktop_process(self):
        launch=MagicMock(return_value=456)
        with patch.object(a, 'launch_trigger', return_value='session'), \
             patch.object(a, 'gpt_is_open') as detect, \
             patch.dict(sys.modules, {'autostart': types.SimpleNamespace(launch_pet=launch)}), \
             patch.object(a.time, 'sleep', side_effect=StopIteration):
            with self.assertRaises(StopIteration): a.monitor()
            detect.assert_not_called()
            launch.assert_called_once()

    def test_systemd_spec_has_graphical_target(self):
        text=a._service_text()
        self.assertIn('WantedBy=graphical-session.target',text)
        self.assertIn('After=graphical-session.target',text)
        self.assertNotIn('/etc/systemd/',text)


if __name__ == '__main__':
    unittest.main()
