import unittest,sys,os
from pathlib import Path
from unittest.mock import patch
import platform_support as p

class PlatformTests(unittest.TestCase):
    def test_mac_bundle_resources(self):
        with patch.object(sys,'platform','darwin'),patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable','/Applications/BailongPet.app/Contents/MacOS/BailongPet'):
            self.assertEqual(p.resource_root(),Path(sys.executable).resolve().parents[1]/'Resources')
    def test_mac_user_data_outside_bundle(self):
        with patch.object(sys,'platform','darwin'),patch.dict(os.environ,{'BAILONG_DATA_DIR':''}):
            self.assertEqual(p.user_data(),Path.home()/'Library/Application Support/BailongPet')
    def test_mac_launch_does_not_use_windows_flags(self):
        import autostart
        with patch.object(sys,'platform','darwin'),patch('autostart.subprocess.Popen') as launch:
            autostart.launch_pet();self.assertNotIn('creationflags',launch.call_args.kwargs)

if __name__=='__main__':unittest.main()
