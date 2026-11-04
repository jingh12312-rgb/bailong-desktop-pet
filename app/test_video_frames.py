from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import video_frames


class DecoderPathTests(unittest.TestCase):
    def test_mac_ignores_windows_decoder_and_uses_bundled_native_decoder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / 'tools'
            tools.mkdir()
            for name in ('ffmpeg.exe', 'ffmpeg'):
                executable = tools / name
                executable.touch()
                executable.chmod(0o755)
            with patch.object(sys, 'platform', 'darwin'), patch(
                    'video_frames.resource_root', return_value=root):
                self.assertEqual(video_frames.ffmpeg_path(), str(tools / 'ffmpeg'))

    def test_frozen_mac_reports_missing_native_decoder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tools').mkdir()
            (root / 'tools/ffmpeg.exe').touch()
            with patch.object(sys, 'platform', 'darwin'), patch.object(
                    sys, 'frozen', True, create=True), patch(
                    'video_frames.resource_root', return_value=root), patch(
                    'video_frames.shutil.which', return_value=None):
                with self.assertRaises(RuntimeError):
                    video_frames.ffmpeg_path()


if __name__ == '__main__':
    unittest.main()
