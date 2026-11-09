"""Render regression checks without requiring the distributed animation pack."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication
from animation_render import aligned_rect
from pet import Pet

app = QApplication.instance() or QApplication([])


class RenderTests(unittest.TestCase):
    def test_position_and_size_are_on_physical_pixels(self):
        target = QRectF(-1.35, 2.28, 257.263, 257.263)
        for ratio in (1, 1.25, 1.5, 2):
            result = aligned_rect(target, ratio)
            for before, after in zip((target.x(), target.y(), target.width(), target.height()),
                                     (result.x(), result.y(), result.width(), result.height())):
                self.assertAlmostEqual(after * ratio, round(after * ratio))
                self.assertLessEqual(abs(before - after) * ratio, .500001)

    def test_fractional_action_preserves_sharp_lines_and_mirrors(self):
        frame = QPixmap(257, 257)
        frame.fill(Qt.GlobalColor.transparent)
        painter = QPainter(frame)
        painter.fillRect(81, 60, 1, 130, Qt.GlobalColor.white)
        painter.end()
        for mirrored in (False, True):
            context = SimpleNamespace(dock_edge=None, dock_exit=None,
                movement_mirrored=mirrored, current={'renderScale': 257/256,
                'renderOffset': [.0013, .0045]}, frames=[frame], index=0)
            image = QImage(256, 256, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            Pet.draw_frame(context, painter, QRectF(0, 0, 256, 256))
            painter.end()
            alphas = [image.pixelColor(x, 100).alpha() for x in range(256)]
            # Qt's reflected smooth path can round opaque alpha to 254.
            self.assertGreaterEqual(max(alphas), 254)
            self.assertEqual(sum(alpha > 0 for alpha in alphas), 1)

    def test_decode_uses_action_size_without_changing_base(self):
        from collections import OrderedDict
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'action.webm'
            context = SimpleNamespace(frame_size=256, pinned_frames={}, cache=OrderedDict(),
                                      asset_path=lambda item: path)
            item = {'id': 'fractional', 'renderScale': 1.0049342105263157}
            with patch('video_frames.rgba_frames', return_value=iter([bytes(257*257*4)])) as decode:
                frames = Pet.load(context, item)
            decode.assert_called_once_with(path, 257)
            self.assertEqual(frames[0].width(), 257)
            self.assertEqual(context.frame_size, 256)
            self.assertIs(Pet.load(context, item), frames)
            context.cache.clear()
            with patch('video_frames.rgba_frames', side_effect=RuntimeError('decode failed')):
                with self.assertRaises(RuntimeError):
                    Pet.load(context, item)
            self.assertEqual(context.frame_size, 256)


if __name__ == '__main__':
    unittest.main()
