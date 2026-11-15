import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import subprocess
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication
from streaming_frames import StreamingFrames
from video_frames import frame_count

app = QApplication.instance() or QApplication([])


class FakeBuffer:
    def __init__(self):
        self.active_key = None
        self.raw = {}

    def activate(self, key, factory):
        self.active_key = key

    def get(self, key, index):
        return self.raw.get(index) if key == self.active_key else None


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.buffer = FakeBuffer()
        self.addCleanup(patch.stopall)
        patch('streaming_frames.frame_count', return_value=5).start()
        def decode(*args, **kwargs):
            for _ in range(5):
                yield bytes([0, 255, 0, 128]) * 4
        patch('streaming_frames.rgba_frames', side_effect=decode).start()

    def frames(self, name='test.webm'):
        return StreamingFrames(Path(name), 2, self.buffer)

    def test_warm_frame_retains_alpha_and_length_stays_stable(self):
        frames = self.frames()
        self.assertEqual(len(frames), 5)
        self.assertEqual(frames[0].toImage().pixelColor(0, 0).alpha(), 128)
        frames.activate()
        self.assertIs(frames[3], frames.first)
        self.buffer.raw[3] = bytes([255, 0, 0, 255]) * 4
        self.assertTrue(frames.refresh(3))
        self.assertEqual(frames[3].toImage().pixelColor(0, 0).red(), 255)
        self.assertEqual(len(frames), 5)
        frames.activate()
        self.assertIs(frames.last, frames.first)
        with self.assertRaises(IndexError):
            frames[5]

    def test_tray_first_frame_does_not_change_active_decoder(self):
        idle = self.frames('idle.webm')
        action = self.frames('action.webm')
        action.activate()
        self.assertIs(idle[0], idle.first)
        self.assertEqual(self.buffer.active_key, action.key)

    def test_late_frame_repaints_without_advancing_logical_index(self):
        from pet import Pet
        frames = self.frames()
        frames.activate()
        pet = SimpleNamespace(dock_edge=None, current={'durationMs':10000},
                              started=time.monotonic()-2.1, mode='idle', frames=frames,
                              transition=None, index=1, update_frame=Mock())
        Pet.animate(pet)
        pet.update_frame.assert_not_called()
        self.buffer.raw[1] = bytes([255, 0, 0, 255]) * 4
        Pet.animate(pet)
        pet.update_frame.assert_called_once()
        self.assertEqual(pet.index, 1)

    def test_decoder_failure_is_not_hidden_by_last_frame(self):
        frames = self.frames()
        with patch.object(self.buffer, 'get', side_effect=RuntimeError('decode failed')):
            with self.assertRaisesRegex(RuntimeError, 'decode failed'):
                frames.refresh(1)


class MetadataTests(unittest.TestCase):
    def test_last_progress_count_is_used(self):
        result = subprocess.CompletedProcess([], 0, b'frame=1\nprogress=continue\nframe=145\nprogress=end\n', b'')
        with patch('video_frames.ffmpeg_path', return_value='ffmpeg'), patch('video_frames.subprocess.run', return_value=result):
            self.assertEqual(frame_count('clip.webm'), 145)

    def test_bad_or_failed_video_is_rejected(self):
        for result in [subprocess.CompletedProcess([], 0, b'frame=0\n', b''),
                       subprocess.CompletedProcess([], 1, b'frame=4\n', b'invalid video')]:
            with patch('video_frames.ffmpeg_path', return_value='ffmpeg'), patch('video_frames.subprocess.run', return_value=result):
                with self.assertRaises(RuntimeError):
                    frame_count('clip.webm')


if __name__ == '__main__':
    unittest.main()
