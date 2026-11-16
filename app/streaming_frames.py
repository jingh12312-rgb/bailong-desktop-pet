"""Keep a warm first frame while decoding only a small playback window."""
from contextlib import closing

from PySide6.QtGui import QImage, QPixmap

from video_frames import frame_count, rgba_frames


def pixmap_from_rgba(raw, size):
    image = QImage(raw, size, size, size * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(image)


class StreamingFrames:
    """Index-compatible animation with stable length and GUI-owned pixmaps.

    Only the first frame and the most recently displayed frame stay as pixmaps.
    FrameBuffer owns the single worker and its bounded raw RGBA lookahead.
    """

    def __init__(self, path, size, buffer):
        self.path = path
        self.size = size
        self.buffer = buffer
        self.key = str(path.resolve())
        self.count = frame_count(path)
        self.failure = None
        with closing(rgba_frames(path, size)) as frames:
            self.first = pixmap_from_rgba(next(frames), size)
        self.reset()

    def __len__(self):
        return self.count

    def reset(self):
        self.last = self.first
        self.last_index = 0

    def activate(self):
        self.reset()
        path, size = self.path, self.size
        factory = (lambda register: iter(())) if self.failure else (
            lambda register: rgba_frames(path, size, on_process=register))
        self.buffer.activate(self.key, factory)

    def freeze(self, error):
        """Retain a safe image and cancel a failed stream without retry loops."""
        self.failure = str(error)
        self.reset()
        self.buffer.activate(self.key, lambda register: iter(()))

    def refresh(self, index):
        if self.failure:
            return False
        raw = self.buffer.get(self.key, index)
        if index == 0:
            changed = self.last_index != 0
            self.reset()
            return changed
        if raw is None or self.last_index == index:
            return False
        self.last = pixmap_from_rgba(raw, self.size)
        self.last_index = index
        return True

    def __getitem__(self, index):
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError(index)
        # First-frame users (tray icon and docking bounds) must not switch the
        # shared decoder away from the animation currently playing.
        if index == 0:
            return self.first
        self.refresh(index)
        return self.last
