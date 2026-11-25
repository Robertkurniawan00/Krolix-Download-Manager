"""
Windows 11 Fluent System Icons Generator.
Renders razor-sharp vector icons with QPainter and anti-aliasing.
Includes:
- Add, Play, Pause, Stop, Delete
- Scheduler, Limiter, Queue, Grabber, Options, Search
"""

import math
from functools import lru_cache
from PyQt6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen, QBrush,
    QPainterPath
)
from PyQt6.QtCore import Qt, QPointF, QRectF


def _create_canvas(size: int = 32) -> tuple[QPixmap, QPainter]:
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    return pix, p


@lru_cache(maxsize=32)
def create_fluent_add_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Add / Plus (+) vector icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        arm = s * 0.32
        pen_w = max(2.2, s * 0.09)

        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(c - arm, c), QPointF(c + arm, c))
        p.drawLine(QPointF(c, c - arm), QPointF(c, c + arm))
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_play_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Media Play triangle."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        path = QPainterPath()
        left = c - s * 0.22
        right = c + s * 0.28
        top = c - s * 0.32
        bottom = c + s * 0.32

        path.moveTo(left, top)
        path.lineTo(right, c)
        path.lineTo(left, bottom)
        path.closeSubpath()

        p.setBrush(QBrush(QColor(color)))
        p.setPen(QPen(QColor(color), 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_pause_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Media Pause (two rounded vertical bars)."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        bar_w = max(2.5, s * 0.16)
        bar_h = s * 0.60
        gap = s * 0.11
        rad = bar_w / 2.0

        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        rect_l = QRectF(c - gap - bar_w, c - bar_h / 2.0, bar_w, bar_h)
        p.drawRoundedRect(rect_l, rad, rad)
        rect_r = QRectF(c + gap, c - bar_h / 2.0, bar_w, bar_h)
        p.drawRoundedRect(rect_r, rad, rad)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_stop_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Media Stop (rounded square)."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        sq_size = s * 0.50
        rad = max(1.5, s * 0.1)
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(c - sq_size / 2.0, c - sq_size / 2.0, sq_size, sq_size)
        p.drawRoundedRect(rect, rad, rad)
        p.end()
        icon.addPixmap(pix)
    return icon


def create_fluent_delete_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Dismiss / Delete (X)."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        arm = s * 0.25
        pen_w = max(2.0, s * 0.09)

        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(c - arm, c - arm), QPointF(c + arm, c + arm))
        p.drawLine(QPointF(c + arm, c - arm), QPointF(c - arm, c + arm))
        p.end()
        icon.addPixmap(pix)
    return icon


def create_fluent_scheduler_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Calendar / Clock icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        r = s * 0.38
        pen_w = max(1.6, s * 0.08)

        p.setPen(QPen(QColor(color), pen_w))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(c, c), r, r)

        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(c, c), QPointF(c, c - r * 0.62))
        p.drawLine(QPointF(c, c), QPointF(c + r * 0.45, c))
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_limiter_icon(color: str = "#f1f5f9", needle_color: str = None) -> QIcon:
    """Windows 11 Fluent Speedometer / Limiter Gauge."""
    icon = QIcon()
    n_col = needle_color or color
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        r = s * 0.38
        pen_w = max(1.6, s * 0.08)

        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(c - r, c - r, 2 * r, 2 * r)
        p.drawArc(rect, int(-45 * 16), int(270 * 16))

        p.setPen(QPen(QColor(n_col), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(c, c), QPointF(c + r * 0.55, c - r * 0.55))

        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(c, c), pen_w * 1.1, pen_w * 1.1)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_queue_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Playlist / Download Queue icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.6, s * 0.08)

        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        y1 = c - s * 0.28
        y2 = c
        y3 = c + s * 0.28

        x_start = c - s * 0.38
        x_end_short = c + s * 0.05
        x_end_long = c + s * 0.38

        p.drawLine(QPointF(x_start, y1), QPointF(x_end_long, y1))
        p.drawLine(QPointF(x_start, y2), QPointF(x_end_long, y2))
        p.drawLine(QPointF(x_start, y3), QPointF(x_end_short, y3))

        path = QPainterPath()
        px = c + s * 0.18
        py = c + s * 0.28
        ts = s * 0.18
        path.moveTo(px, py - ts * 0.9)
        path.lineTo(px + ts * 1.2, py)
        path.lineTo(px, py + ts * 0.9)
        path.closeSubpath()

        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_grabber_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Video / Media Stream Grabber."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.6, s * 0.08)

        cam_w = s * 0.46
        cam_h = s * 0.36
        cam_x = c - s * 0.38
        cam_y = c - cam_h / 2.0
        rad = max(2.0, s * 0.07)

        p.setPen(QPen(QColor(color), pen_w))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(cam_x, cam_y, cam_w, cam_h), rad, rad)

        path = QPainterPath()
        lx = cam_x + cam_w
        path.moveTo(lx, c - cam_h * 0.25)
        path.lineTo(lx + s * 0.22, c - cam_h * 0.50)
        path.lineTo(lx + s * 0.22, c + cam_h * 0.50)
        path.lineTo(lx, c + cam_h * 0.25)
        path.closeSubpath()

        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_options_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Settings / Gear icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        r_outer = s * 0.38
        r_inner = s * 0.26
        r_hole = s * 0.13
        num_teeth = 6

        path = QPainterPath()
        for i in range(num_teeth * 2):
            angle = i * (math.pi / num_teeth)
            r = r_outer if (i % 2 == 0) else r_inner
            x = c + r * math.cos(angle)
            y = c + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()

        p.setBrush(QBrush(QColor(color)))
        p.setPen(QPen(QColor(color), 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)

        p.setBrush(QBrush(QColor(0, 0, 0, 0)))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.drawEllipse(QPointF(c, c), r_hole, r_hole)
        p.end()
        icon.addPixmap(pix)
    return icon


def create_fluent_broom_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Clean / Clear Completed (Broom) icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.8, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(c + s * 0.26, c - s * 0.30), QPointF(c - s * 0.04, c + s * 0.04))
        path = QPainterPath()
        path.moveTo(c - s * 0.04, c + s * 0.04)
        path.lineTo(c - s * 0.30, c + s * 0.18)
        path.lineTo(c - s * 0.18, c + s * 0.32)
        path.lineTo(c + s * 0.06, c + s * 0.14)
        path.closeSubpath()
        p.setBrush(QBrush(QColor(color)))
        p.drawPath(path)
        p.end()
        icon.addPixmap(pix)
    return icon


def create_fluent_redownload_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Redownload / Reload circular arrow."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        r = s * 0.34
        pen_w = max(1.8, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        rect = QRectF(c - r, c - r, 2 * r, 2 * r)
        p.drawArc(rect, int(35 * 16), int(275 * 16))
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        head = QPainterPath()
        hx = c + r * math.cos(math.radians(35))
        hy = c - r * math.sin(math.radians(35))
        head.moveTo(hx - s * 0.12, hy - s * 0.10)
        head.lineTo(hx + s * 0.08, hy)
        head.lineTo(hx - s * 0.10, hy + s * 0.10)
        head.closeSubpath()
        p.drawPath(head)
        p.end()
        icon.addPixmap(pix)
    return icon


def create_fluent_stop_queue_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Stop Queue icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.6, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        y1 = c - s * 0.28
        y2 = c
        y3 = c + s * 0.28
        p.drawLine(QPointF(c - s * 0.38, y1), QPointF(c + s * 0.38, y1))
        p.drawLine(QPointF(c - s * 0.38, y2), QPointF(c + s * 0.38, y2))
        p.drawLine(QPointF(c - s * 0.38, y3), QPointF(c + s * 0.05, y3))
        bar_w = max(2.0, s * 0.09)
        bar_h = s * 0.28
        bx = c + s * 0.22
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bx, y3 - bar_h / 2.0, bar_w, bar_h), 1, 1)
        p.drawRoundedRect(QRectF(bx + bar_w * 1.5, y3 - bar_h / 2.0, bar_w, bar_h), 1, 1)
        p.end()
        icon.addPixmap(pix)
    return icon


def create_fluent_batch_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Batch / Stacked Layers Download icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.6, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(c - s * 0.24, c - s * 0.34, s * 0.50, s * 0.38), 2, 2)
        p.drawRoundedRect(QRectF(c - s * 0.34, c - s * 0.14, s * 0.50, s * 0.38), 2, 2)
        p.end()
        icon.addPixmap(pix)
    return icon


def create_fluent_hash_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Shield / Checksum Verifier icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.6, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(c, c - s * 0.34)
        path.lineTo(c + s * 0.30, c - s * 0.24)
        path.quadTo(QPointF(c + s * 0.24, c + s * 0.30), QPointF(c, c + s * 0.38))
        path.quadTo(QPointF(c - s * 0.24, c + s * 0.30), QPointF(c - s * 0.30, c + s * 0.05))
        path.lineTo(c - s * 0.30, c - s * 0.24)
        path.closeSubpath()
        p.drawPath(path)
        # Checkmark inside
        p.setPen(QPen(QColor(color), pen_w * 1.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(c - s * 0.14, c + s * 0.02), QPointF(c - s * 0.02, c + s * 0.14))
        path.quadTo(QPointF(c - s * 0.24, c + s * 0.30), QPointF(c - s * 0.30, c + s * 0.05))
        path.lineTo(c - s * 0.30, c - s * 0.24)
        path.closeSubpath()
        p.drawPath(path)
        # Checkmark inside
        p.setPen(QPen(QColor(color), pen_w * 1.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(c - s * 0.14, c + s * 0.02), QPointF(c - s * 0.02, c + s * 0.14))
        p.drawLine(QPointF(c - s * 0.02, c + s * 0.14), QPointF(c + s * 0.16, c - s * 0.10))
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_graph_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Speed Analytics Graph icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.6, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(c - s * 0.34, c - s * 0.30), QPointF(c - s * 0.34, c + s * 0.30))
        p.drawLine(QPointF(c - s * 0.34, c + s * 0.30), QPointF(c + s * 0.34, c + s * 0.30))
        path = QPainterPath()
        path.moveTo(c - s * 0.28, c + s * 0.14)
        path.lineTo(c - s * 0.08, c - s * 0.06)
        path.lineTo(c + s * 0.10, c + s * 0.08)
        path.lineTo(c + s * 0.30, c - s * 0.24)
        p.drawPath(path)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_torrent_icon(color: str = "#10b981") -> QIcon:
    """Windows 11 Fluent Magnet / Torrent Swarm icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.8, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Draw U-shaped magnet
        path = QPainterPath()
        path.moveTo(c - s * 0.26, c - s * 0.28)
        path.lineTo(c - s * 0.26, c + s * 0.06)
        path.quadTo(QPointF(c - s * 0.26, c + s * 0.32), QPointF(c, c + s * 0.32))
        path.quadTo(QPointF(c + s * 0.26, c + s * 0.32), QPointF(c + s * 0.26, c + s * 0.06))
        path.lineTo(c + s * 0.26, c - s * 0.28)
        p.drawPath(path)

        # Center energy spark / beam
        p.setPen(QPen(QColor(color), pen_w * 0.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(c, c - s * 0.22), QPointF(c, c + s * 0.08))
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_seeder_icon(color: str = "#10b981") -> QIcon:
    """Windows 11 Fluent BitTorrent Seeder icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.8, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Cloud outline with upward arrow
        path = QPainterPath()
        path.moveTo(c - s * 0.30, c + s * 0.16)
        path.lineTo(c + s * 0.30, c + s * 0.16)
        path.quadTo(QPointF(c + s * 0.38, c + s * 0.16), QPointF(c + s * 0.35, c))
        path.quadTo(QPointF(c + s * 0.28, c - s * 0.24), QPointF(c + s * 0.05, c - s * 0.24))
        path.quadTo(QPointF(c - s * 0.12, c - s * 0.30), QPointF(c - s * 0.26, c - s * 0.14))
        path.quadTo(QPointF(c - s * 0.40, c - s * 0.06), QPointF(c - s * 0.30, c + s * 0.16))
        p.drawPath(path)

        # Upward arrow inside cloud (upload booster)
        p.setPen(QPen(QColor(color), pen_w * 1.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(c, c + s * 0.12), QPointF(c, c - s * 0.08))
        p.drawLine(QPointF(c - s * 0.10, c + s * 0.02), QPointF(c, c - s * 0.08))
        p.drawLine(QPointF(c + s * 0.10, c + s * 0.02), QPointF(c, c - s * 0.08))

        p.end()
        icon.addPixmap(pix)
    return icon


# Backward compatibility alias
create_fluent_spoofer_icon = create_fluent_seeder_icon


@lru_cache(maxsize=32)
def create_fluent_ytdlp_icon(color: str = "#ef4444") -> QIcon:
    """Windows 11 Fluent YouTube & Social Video download icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.8, s * 0.08)

        # Video frame / rounded screen
        screen_rect = QRectF(c - s * 0.38, c - s * 0.28, s * 0.76, s * 0.56)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(screen_rect, s * 0.12, s * 0.12)

        # Centered play triangle
        p_path = QPainterPath()
        p_left = c - s * 0.10
        p_right = c + s * 0.14
        p_top = c - s * 0.14
        p_bottom = c + s * 0.14
        p_path.moveTo(p_left, p_top)
        p_path.lineTo(p_right, c)
        p_path.lineTo(p_left, p_bottom)
        p_path.closeSubpath()

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(color)))
        p.drawPath(p_path)

        p.end()
        icon.addPixmap(pix)
    return icon




@lru_cache(maxsize=32)
def create_fluent_dht_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Distributed Hash Table / Decentralized Swarm network icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.5, s * 0.07)

        p_center = QPointF(c, c)
        p_top = QPointF(c, c - s * 0.30)
        p_right = QPointF(c + s * 0.30, c + s * 0.06)
        p_bottom = QPointF(c - s * 0.18, c + s * 0.28)
        p_left = QPointF(c - s * 0.30, c - s * 0.08)
        nodes = [p_top, p_right, p_bottom, p_left]

        p.setPen(QPen(QColor(color), pen_w * 0.85, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for n in nodes:
            p.drawLine(p_center, n)
        p.drawLine(p_top, p_right)
        p.drawLine(p_right, p_bottom)
        p.drawLine(p_bottom, p_left)
        p.drawLine(p_left, p_top)

        r = max(2.0, s * 0.07)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(color)))
        p.drawEllipse(p_center, r * 1.3, r * 1.3)
        for n in nodes:
            p.drawEllipse(n, r, r)

        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_folder_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Folder icon."""
    icon = QIcon()
    for s in [16, 24, 32]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.2, s * 0.08)
        path = QPainterPath()
        # Folder back and tab
        path.moveTo(s * 0.15, s * 0.28)
        path.lineTo(s * 0.42, s * 0.28)
        path.lineTo(s * 0.52, s * 0.38)
        path.lineTo(s * 0.85, s * 0.38)
        path.lineTo(s * 0.85, s * 0.78)
        path.lineTo(s * 0.15, s * 0.78)
        path.closeSubpath()
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QBrush(QColor(color).lighter(120)))
        p.drawPath(path)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_all_downloads_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent In-tray / All Downloads icon."""
    icon = QIcon()
    for s in [16, 24, 32]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.2, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Tray outline
        tray = QPainterPath()
        tray.moveTo(s * 0.15, s * 0.48)
        tray.lineTo(s * 0.15, s * 0.80)
        tray.lineTo(s * 0.85, s * 0.80)
        tray.lineTo(s * 0.85, s * 0.48)
        p.drawPath(tray)
        # Downward arrow
        arrow = QPainterPath()
        arrow.moveTo(c, s * 0.18)
        arrow.lineTo(c, s * 0.58)
        arrow.moveTo(c - s * 0.18, s * 0.40)
        arrow.lineTo(c, s * 0.58)
        arrow.lineTo(c + s * 0.18, s * 0.40)
        p.drawPath(arrow)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_compressed_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Archive / Zip box icon."""
    icon = QIcon()
    for s in [16, 24, 32]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.2, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.60), s * 0.10, s * 0.10)
        # Zipper track in middle
        p.drawLine(QPointF(c, s * 0.20), QPointF(c, s * 0.60))
        p.drawLine(QPointF(c - s * 0.08, s * 0.30), QPointF(c + s * 0.08, s * 0.30))
        p.drawLine(QPointF(c - s * 0.08, s * 0.45), QPointF(c + s * 0.08, s * 0.45))
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_documents_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Document file icon."""
    icon = QIcon()
    for s in [16, 24, 32]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.2, s * 0.08)
        path = QPainterPath()
        path.moveTo(s * 0.22, s * 0.15)
        path.lineTo(s * 0.58, s * 0.15)
        path.lineTo(s * 0.78, s * 0.35)
        path.lineTo(s * 0.78, s * 0.85)
        path.lineTo(s * 0.22, s * 0.85)
        path.closeSubpath()
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        # Folded flap line
        p.drawLine(QPointF(s * 0.58, s * 0.15), QPointF(s * 0.58, s * 0.35))
        p.drawLine(QPointF(s * 0.58, s * 0.35), QPointF(s * 0.78, s * 0.35))
        # Text lines
        p.drawLine(QPointF(s * 0.34, s * 0.52), QPointF(s * 0.66, s * 0.52))
        p.drawLine(QPointF(s * 0.34, s * 0.66), QPointF(s * 0.56, s * 0.66))
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_music_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Musical Note icon."""
    icon = QIcon()
    for s in [16, 24, 32]:
        pix, p = _create_canvas(s)
        pen_w = max(1.2, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        # Note stem and beam
        p.drawLine(QPointF(s * 0.38, s * 0.68), QPointF(s * 0.38, s * 0.25))
        p.drawLine(QPointF(s * 0.38, s * 0.25), QPointF(s * 0.72, s * 0.18))
        p.drawLine(QPointF(s * 0.72, s * 0.18), QPointF(s * 0.72, s * 0.58))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(color)))
        p.drawEllipse(QPointF(s * 0.30, s * 0.72), s * 0.12, s * 0.09)
        p.drawEllipse(QPointF(s * 0.64, s * 0.62), s * 0.12, s * 0.09)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_programs_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Application Window / Software icon."""
    icon = QIcon()
    for s in [16, 24, 32]:
        pix, p = _create_canvas(s)
        pen_w = max(1.2, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.16, s * 0.20, s * 0.68, s * 0.60), s * 0.08, s * 0.08)
        p.drawLine(QPointF(s * 0.16, s * 0.38), QPointF(s * 0.84, s * 0.38))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(color)))
        p.drawEllipse(QPointF(s * 0.26, s * 0.29), s * 0.04, s * 0.04)
        p.drawEllipse(QPointF(s * 0.36, s * 0.29), s * 0.04, s * 0.04)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_video_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Film Reel / Video icon."""
    icon = QIcon()
    for s in [16, 24, 32]:
        pix, p = _create_canvas(s)
        pen_w = max(1.2, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.16, s * 0.22, s * 0.68, s * 0.56), s * 0.08, s * 0.08)
        # Play glyph inside
        c = s / 2.0
        p_path = QPainterPath()
        p_path.moveTo(c - s * 0.08, c - s * 0.12)
        p_path.lineTo(c + s * 0.12, c)
        p_path.lineTo(c - s * 0.08, c + s * 0.12)
        p_path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(color)))
        p.drawPath(p_path)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_clock_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Clock / Unfinished status icon."""
    icon = QIcon()
    for s in [16, 24, 32]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.2, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(c, c), s * 0.35, s * 0.35)
        # Clock hands
        p.drawLine(QPointF(c, c), QPointF(c, c - s * 0.20))
        p.drawLine(QPointF(c, c), QPointF(c + s * 0.16, c))
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_check_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Checkmark / Finished status icon."""
    icon = QIcon()
    for s in [16, 24, 32]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.5, s * 0.09)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(s * 0.24, s * 0.52)
        path.lineTo(s * 0.44, s * 0.72)
        path.lineTo(s * 0.76, s * 0.32)
        p.drawPath(path)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_magnet_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Magnet icon."""
    icon = QIcon()
    for s in [16, 24, 32]:
        pix, p = _create_canvas(s)
        pen_w = max(1.8, s * 0.12)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(s * 0.30, s * 0.25)
        path.lineTo(s * 0.30, s * 0.55)
        path.arcTo(QRectF(s * 0.30, s * 0.35, s * 0.40, s * 0.40), 180, 180)
        path.lineTo(s * 0.70, s * 0.25)
        p.drawPath(path)
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_search_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Magnifying Glass icon."""
    icon = QIcon()
    for s in [16, 24, 32]:
        pix, p = _create_canvas(s)
        pen_w = max(1.3, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(s * 0.42, s * 0.42), s * 0.25, s * 0.25)
        p.drawLine(QPointF(s * 0.60, s * 0.60), QPointF(s * 0.82, s * 0.82))
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_refresh_link_icon(color: str = "#94a3b8") -> QIcon:
    """Windows 11 Fluent Refresh Link / Address icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.5, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)

        r = s * 0.32
        p.drawArc(QRectF(c - r, c - r, r * 2, r * 2), int(45 * 16), int(270 * 16))

        arrow = QPainterPath()
        ax = c + r * 0.707
        ay = c - r * 0.707
        arrow.moveTo(ax - s * 0.08, ay - s * 0.12)
        arrow.lineTo(ax + s * 0.06, ay)
        arrow.lineTo(ax - s * 0.12, ay + s * 0.06)
        p.strokePath(arrow, QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

        p.drawEllipse(QPointF(c, c), s * 0.10, s * 0.10)
        p.end()
        icon.addPixmap(pix)
    return icon





@lru_cache(maxsize=32)
def create_fluent_shield_icon(color: str = "#10b981") -> QIcon:
    """Windows 11 Fluent Security Shield / License Icon."""
    return create_fluent_hash_icon(color)


@lru_cache(maxsize=32)
def create_fluent_key_icon(color: str = "#f1f5f9") -> QIcon:
    """Windows 11 Fluent Product License Key Icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.5, s * 0.08)
        p.setPen(QPen(QColor(color), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = s * 0.16
        p.drawEllipse(QPointF(c - s * 0.14, c - s * 0.14), r, r)
        p.drawLine(QPointF(c - s * 0.02, c - s * 0.02), QPointF(c + s * 0.28, c + s * 0.28))
        p.drawLine(QPointF(c + s * 0.16, c + s * 0.16), QPointF(c + s * 0.24, c + s * 0.08))
        p.drawLine(QPointF(c + s * 0.24, c + s * 0.24), QPointF(c + s * 0.30, c + s * 0.18))
        p.end()
        icon.addPixmap(pix)
    return icon


@lru_cache(maxsize=32)
def create_fluent_live_icon(color: str = "#f43f5e") -> QIcon:
    """Windows 11 Fluent Live Stream Broadcast / Auto-Record Radar Icon."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        c = s / 2.0
        pen_w = max(1.4, s * 0.075)
        col = QColor(color)

        # Center solid live dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(c, c), s * 0.12, s * 0.12)

        # Left and right broadcast wave arcs
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(col, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for mult in (0.24, 0.38):
            r = s * mult
            rect = QRectF(c - r, c - r, r * 2, r * 2)
            p.drawArc(rect, 135 * 16, 90 * 16)
            p.drawArc(rect, -45 * 16, 90 * 16)

        p.end()
        icon.addPixmap(pix)
    return icon


def create_fluent_more_horizontal_icon(color: str = "#a1a1aa") -> QIcon:
    """macOS 3-dot overflow / more options icon (horizontal ellipsis)."""
    icon = QIcon()
    for s in [16, 24, 32, 48, 64]:
        pix, p = _create_canvas(s)
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        c_y = s / 2.0
        r = max(1.2, s * 0.085)
        spacing = s * 0.26
        c_x = s / 2.0
        p.drawEllipse(QRectF(c_x - spacing - r, c_y - r, r * 2, r * 2))
        p.drawEllipse(QRectF(c_x - r, c_y - r, r * 2, r * 2))
        p.drawEllipse(QRectF(c_x + spacing - r, c_y - r, r * 2, r * 2))
        p.end()
        icon.addPixmap(pix)
    return icon
