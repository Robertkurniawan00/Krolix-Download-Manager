"""
Krolix Download Manager - Real-Time Bandwidth Speed Graph
Renders smooth anti-aliased gradient area chart of network throughput over time.
Supports dynamic accent colors, smooth bezier spline curves, and live HUD metrics.
"""

from collections import deque
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath, QFont
from ..utils.helpers import format_speed


class SpeedGraphWidget(QWidget):
    def __init__(self, max_points: int = 60, parent=None):
        super().__init__(parent)
        self.max_points = max_points
        self.history = deque([0.0] * max_points, maxlen=max_points)
        self.current_speed = 0.0
        self.peak_speed = 0.0
        self.accent_color = QColor(148, 163, 184)  # Chrome silver default
        self.accent_end = QColor(100, 116, 139)    # Dark steel titanium
        self.setFixedHeight(72)
        self.setMinimumWidth(240)

    def set_accent_color(self, primary_hex: str, end_hex: str = ""):
        try:
            self.accent_color = QColor(primary_hex)
            self.accent_end = QColor(end_hex) if end_hex else self.accent_color
            self.update()
        except Exception:
            pass

    def add_speed(self, speed_bps: float):
        self.current_speed = speed_bps
        if speed_bps > self.peak_speed:
            self.peak_speed = speed_bps
        self.history.append(speed_bps)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background card with smooth rounded corners
        bg_color = QColor(0, 0, 0, 240)
        border_color = QColor(28, 28, 28, 255)

        card_path = QPainterPath()
        card_path.addRoundedRect(0.5, 0.5, w - 1.0, h - 1.0, 8.0, 8.0)
        painter.fillPath(card_path, bg_color)
        painter.setPen(QPen(border_color, 1.0))
        painter.drawPath(card_path)

        # Scale calculation (minimum 100 KB/s scale)
        max_val = max(max(self.history), 1024 * 100)

        # Draw subtle grid lines (25%, 50%, 75%)
        grid_pen = QPen(QColor(255, 255, 255, 14), 1, Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        for pct in (0.33, 0.66):
            gy = int(h * pct)
            painter.drawLine(10, gy, w - 10, gy)

        # Build smooth curved path using Catmull-Rom or cubic bezier segments
        step = (w - 20) / max(1, self.max_points - 1)
        points = []

        chart_bottom = h - 10
        chart_top = 26
        chart_h = chart_bottom - chart_top

        for i, val in enumerate(self.history):
            x = 10 + i * step
            ratio = min(1.0, max(0.0, val / max_val))
            y = chart_bottom - (ratio * chart_h)
            points.append(QPointF(x, y))

        if len(points) >= 2:
            path = QPainterPath()
            path.moveTo(points[0])

            # Smooth curve through control points
            for i in range(len(points) - 1):
                p0 = points[i]
                p1 = points[i + 1]
                mid_x = (p0.x() + p1.x()) / 2.0
                path.cubicTo(QPointF(mid_x, p0.y()), QPointF(mid_x, p1.y()), p1)

            # Gradient fill under the curve
            fill_path = QPainterPath(path)
            fill_path.lineTo(points[-1].x(), chart_bottom)
            fill_path.lineTo(points[0].x(), chart_bottom)
            fill_path.closeSubpath()

            grad = QLinearGradient(0, chart_top, 0, chart_bottom)
            fill_col_top = QColor(self.accent_color.red(), self.accent_color.green(), self.accent_color.blue(), 90)
            fill_col_bot = QColor(self.accent_end.red(), self.accent_end.green(), self.accent_end.blue(), 5)
            grad.setColorAt(0.0, fill_col_top)
            grad.setColorAt(1.0, fill_col_bot)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawPath(fill_path)

            # Stroke line with accent color
            stroke_pen = QPen(self.accent_color, 2.0)
            stroke_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroke_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(stroke_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

            # Small glowing point on the latest reading
            latest = points[-1]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 230)))
            painter.drawEllipse(latest, 3.5, 3.5)

        # Top HUD metrics bar
        painter.setFont(QFont("Segoe UI Variable Text", 9, QFont.Weight.Bold))
        painter.setPen(QColor(241, 245, 249))

        cur_str = format_speed(self.current_speed)
        painter.drawText(12, 18, f"Speed: {cur_str}")

        # Peak indicator & Grid scale on right
        painter.setFont(QFont("Segoe UI Variable Text", 8, QFont.Weight.Normal))
        painter.setPen(QColor(148, 163, 184))
        peak_str = f"Peak: {format_speed(self.peak_speed)}"
        painter.drawText(w - 190, 18, peak_str)

        scale_str = f"Max: {format_speed(max_val)}"
        painter.drawText(w - 90, 18, scale_str)
