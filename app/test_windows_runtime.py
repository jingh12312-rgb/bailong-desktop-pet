import unittest
from unittest.mock import patch
import windows_runtime


class IntegrityTests(unittest.TestCase):
    def test_low_and_untrusted_tokens_are_rejected(self):
        with patch.object(windows_runtime.sys, 'platform', 'win32'):
            for rid in (0, 0x1000):
                with self.subTest(rid=rid), patch.object(windows_runtime, 'integrity_rid', return_value=rid):
                    with self.assertRaisesRegex(RuntimeError, 'Low'):
                        windows_runtime.require_desktop_integrity()

    def test_normal_user_and_admin_tokens_are_accepted(self):
        with patch.object(windows_runtime.sys, 'platform', 'win32'):
            for rid in (0x2000, 0x2100, 0x3000, 0x4000):
                with self.subTest(rid=rid), patch.object(windows_runtime, 'integrity_rid', return_value=rid):
                    windows_runtime.require_desktop_integrity()

    def test_non_windows_does_not_query_windows_token(self):
        with patch.object(windows_runtime.sys, 'platform', 'darwin'), patch.object(windows_runtime, 'integrity_rid') as read:
            windows_runtime.require_desktop_integrity()
            read.assert_not_called()

    def test_token_query_failure_is_not_mistaken_for_normal_integrity(self):
        with patch.object(windows_runtime.sys, 'platform', 'win32'), patch.object(windows_runtime, 'integrity_rid', side_effect=OSError('token unavailable')):
            with self.assertRaises(OSError):
                windows_runtime.require_desktop_integrity()

    @unittest.skipUnless(windows_runtime.sys.platform == 'win32', 'Windows entry point')
    def test_low_startup_stops_before_autostart_or_quota_services(self):
        import pet
        import autostart
        with patch.object(windows_runtime, 'integrity_rid', return_value=0x1000), \
                patch.object(pet.sys, 'argv', ['pet.py', '--autostart']), \
                patch('ctypes.windll.user32.MessageBoxW') as message, \
                patch.object(autostart, 'main') as monitor, \
                patch.object(pet, 'Pet') as widget:
            self.assertEqual(pet.main(), 1)
            message.assert_called_once()
            monitor.assert_not_called()
            widget.assert_not_called()


if __name__ == '__main__':
    unittest.main()
