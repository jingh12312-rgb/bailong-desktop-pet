"""Align ordinary sprite draws without quantizing rotating dock transitions."""
from PySide6.QtCore import QRectF


def aligned_rect(target, ratio):
    """Round position and extent to physical pixels, keeping the sprite size."""
    ratio = max(1.0, float(ratio))
    return QRectF(round(target.x() * ratio) / ratio,
                  round(target.y() * ratio) / ratio,
                  max(1, round(target.width() * ratio)) / ratio,
                  max(1, round(target.height() * ratio)) / ratio)
