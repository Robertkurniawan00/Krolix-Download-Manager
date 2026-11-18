from PyQt6.QtWidgets import QWidget, QStyledItemDelegate, QStyle, QStyleOptionViewItem
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont
from PyQt6.QtCore import Qt, QRect, QModelIndex, QRectF
from typing import List
from ..core.models import SegmentModel


class SegmentVisualizer(QWidget):
    """Visualizes multi-connection parallel segments with Fluent Dark polish."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.segments: List[SegmentModel] = []
        self.accent_color = QColor("#cbd5e1")
        self.setFixedHeight(26)
        self.setMinimumWidth(300)

    def set_accent_color(self, hex_code: str):
        try:
            self.accent_color = QColor(hex_code)
            self.update()
        except Exception:
            pass

    def set_segments(self, segments: List[SegmentModel]):
        self.segments = segments
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = self.width()
        height = self.height()

        # Rounded Background Container
        bg_color = QColor("#000000")
        border_color = QColor("#1c1c1c")

        painter.setPen(QPen(border_color, 1))
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(QRectF(0.5, 0.5, width - 1, height - 1), 4.0, 4.0)

        if not self.segments:
            painter.setFont(QFont("Segoe UI Variable Text", 8))
            painter.setPen(QColor("#64748b"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for connection...")
            return

        total_file_bytes = sum(s.total_bytes for s in self.segments)
        if total_file_bytes <= 0:
            total_file_bytes = len(self.segments)

        curr_x = 2.0
        available_width = float(width - 4)

        for i, seg in enumerate(self.segments):
            seg_ratio = (seg.total_bytes / total_file_bytes) if total_file_bytes > 0 else (1.0 / len(self.segments))
            seg_width = seg_ratio * available_width
            x_pos = curr_x
            w_pos = max(2.0, seg_width)

            # Segment track
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#0d0d0d")))
            painter.drawRect(QRectF(x_pos, 2, w_pos, height - 4))

            # Downloaded portion in segment
            prog = seg.progress
            if prog > 0:
                fill_w = max(1.0, w_pos * prog)
                fill_col = self.accent_color if seg.status != "Completed" else QColor("#10b981")
                painter.setBrush(QBrush(fill_col))
                painter.drawRect(QRectF(x_pos, 2, fill_w, height - 4))

            # Segment divider line
            painter.setPen(QPen(QColor("#000000"), 1))
            painter.drawLine(int(x_pos + w_pos), 2, int(x_pos + w_pos), height - 2)

            curr_x += seg_width


class FileNameDelegate(QStyledItemDelegate):
    """
    Renders File Name with:
    - Active left accent indicator pill matching user accent theme
    - Monospace frosted glass file type badge (ISO, MP4, TAR, EXE, ZIP, etc.)
    - File Name (Slate-100 font-bold, elided cleanly)
    - Domain and status subtext (Slate-500)
    """
    accent_color = QColor("#cbd5e1") # Default Chrome Platinum

    BADGE_COLORS = {
        # Video - Sleek Platinum Chrome
        "MP4": (QColor(255, 255, 255, 14), QColor(255, 255, 255, 30), QColor("#cbd5e1")),
        "MKV": (QColor(255, 255, 255, 14), QColor(255, 255, 255, 30), QColor("#cbd5e1")),
        "AVI": (QColor(255, 255, 255, 14), QColor(255, 255, 255, 30), QColor("#cbd5e1")),
        "WEBM": (QColor(255, 255, 255, 14), QColor(255, 255, 255, 30), QColor("#cbd5e1")),
        # Disc / Disk images - Bright Platinum
        "ISO": (QColor(255, 255, 255, 16), QColor(255, 255, 255, 32), QColor("#e2e8f0")),
        "IMG": (QColor(255, 255, 255, 16), QColor(255, 255, 255, 32), QColor("#e2e8f0")),
        # Archives - Muted Titanium
        "ZIP": (QColor(255, 255, 255, 10), QColor(255, 255, 255, 22), QColor("#94a3b8")),
        "TAR": (QColor(255, 255, 255, 10), QColor(255, 255, 255, 22), QColor("#94a3b8")),
        "GZ": (QColor(255, 255, 255, 10), QColor(255, 255, 255, 22), QColor("#94a3b8")),
        "RAR": (QColor(255, 255, 255, 10), QColor(255, 255, 255, 22), QColor("#94a3b8")),
        "7Z": (QColor(255, 255, 255, 10), QColor(255, 255, 255, 22), QColor("#94a3b8")),
        # Executables - Metallic Steel
        "EXE": (QColor(255, 255, 255, 14), QColor(255, 255, 255, 30), QColor("#cbd5e1")),
        "MSI": (QColor(255, 255, 255, 14), QColor(255, 255, 255, 30), QColor("#cbd5e1")),
        "APK": (QColor(255, 255, 255, 14), QColor(255, 255, 255, 30), QColor("#cbd5e1")),
        # Documents - Slate Chrome
        "PDF": (QColor(255, 255, 255, 10), QColor(255, 255, 255, 22), QColor("#94a3b8")),
        "DOC": (QColor(255, 255, 255, 10), QColor(255, 255, 255, 22), QColor("#94a3b8")),
        "DOCX": (QColor(255, 255, 255, 10), QColor(255, 255, 255, 22), QColor("#94a3b8")),
    }

    @classmethod
    def set_accent_color(cls, hex_code: str):
        try:
            cls.accent_color = QColor(hex_code)
        except Exception:
            pass

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect

        # Retrieve meta data
        meta = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(meta, dict):
            painter.restore()
            super().paint(painter, option, index)
            return

        is_active = meta.get("is_active", False)
        filename = meta.get("filename", "")
        ext = meta.get("ext", "FILE").upper()
        domain = meta.get("domain", "")

        # Signature Windows 11 left accent indicator pill on selected row
        if option.state & QStyle.StateFlag.State_Selected:
            accent_rect = QRectF(rect.left() + 2.0, rect.top() + 6, 3.5, rect.height() - 12)
            painter.setBrush(QBrush(QColor("#cbd5e1")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(accent_rect, 1.75, 1.75)

        # Extension Badge (Frosted Glass Pill)
        bg_col, border_col, txt_col = self.BADGE_COLORS.get(ext, (QColor(148, 163, 184, 25), QColor(148, 163, 184, 65), QColor("#cbd5e1")))
        badge_w = 40
        badge_h = 22
        badge_x = rect.left() + 12
        badge_y = rect.top() + (rect.height() - badge_h) // 2

        badge_rect = QRectF(badge_x, badge_y, badge_w, badge_h)
        painter.setPen(QPen(border_col, 1))
        painter.setBrush(QBrush(bg_col))
        painter.drawRoundedRect(badge_rect, 5.0, 5.0)

        badge_font = QFont("Segoe UI Variable Display", 8)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.setPen(txt_col)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, ext[:4])

        # Filename Text
        content_x = badge_x + badge_w + 10
        content_w = rect.right() - content_x - 10

        name_rect = QRect(content_x, rect.top() + 7, content_w, 18)
        name_font = QFont("Segoe UI Variable Display", 9)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(QColor("#f8fafc"))
        elided_name = painter.fontMetrics().elidedText(filename, Qt.TextElideMode.ElideRight, content_w)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_name)

        # Domain / Subtext
        domain_rect = QRect(content_x, rect.top() + 27, content_w, 16)
        domain_font = QFont("Segoe UI Variable Text", 8)
        painter.setFont(domain_font)
        painter.setPen(QColor("#64748b"))
        elided_domain = painter.fontMetrics().elidedText(domain, Qt.TextElideMode.ElideRight, content_w)
        painter.drawText(domain_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_domain)

        painter.restore()


class ProgressSegmentsDelegate(QStyledItemDelegate):
    """
    Renders Progress & Streams column:
    - Top: Percentage and Stream count
    - Bottom: Sleek Windows 11 Fluent rounded progress bar with dynamic accent glow
    """
    accent_color = QColor("#94a3b8") # Default Chrome Silver

    @classmethod
    def set_accent_color(cls, hex_code: str):
        try:
            cls.accent_color = QColor(hex_code)
        except Exception:
            pass

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect

        # Retrieve data
        meta = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(meta, dict):
            painter.restore()
            super().paint(painter, option, index)
            return

        progress = float(meta.get("progress", 0.0))
        streams_txt = str(meta.get("streams_text", ""))
        status = str(meta.get("status", "")).lower()

        pad_x = 10
        content_w = rect.width() - (pad_x * 2)

        # Top Text: Progress % and Streams
        top_rect = QRect(rect.left() + pad_x, rect.top() + 6, content_w, 18)
        font_pct = QFont("Segoe UI Variable Display", 9)
        font_pct.setBold(True)
        painter.setFont(font_pct)

        pct_str = f"{progress:.1f}%"
        if progress >= 100:
            pct_color = QColor("#86efac") # Soft metallic mint when complete
        elif status in ["error", "failed"]:
            pct_color = QColor("#fda4af") # Soft muted rose on error
        elif status in ["paused", "stopped"]:
            pct_color = QColor("#94a3b8") # Soft slate silver when paused (calm, no bright orange)
        else:
            pct_color = QColor("#f8fafc") # Crisp white when downloading

        painter.setPen(pct_color)
        painter.drawText(top_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, pct_str)

        font_sub = QFont("Segoe UI Variable Text", 8)
        painter.setFont(font_sub)
        painter.setPen(QColor("#94a3b8"))
        painter.drawText(top_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, streams_txt)

        # Bottom Progress Bar
        bar_h = 5.0
        bar_y = rect.top() + 29.0
        bar_bg_rect = QRectF(rect.left() + pad_x, bar_y, content_w, bar_h)

        # Background track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#121212")))
        painter.drawRoundedRect(bar_bg_rect, 2.5, 2.5)

        # Progress fill
        if progress > 0:
            fill_w = max(4.0, min(float(content_w), float(content_w) * (progress / 100.0)))
            fill_rect = QRectF(rect.left() + pad_x, bar_y, fill_w, bar_h)

            if progress >= 100:
                fill_color = QColor("#10b981") # Crisp emerald green
            elif status in ["error", "failed"]:
                fill_color = QColor("#ef4444") # Crisp crimson red
            elif status in ["paused", "stopped"]:
                fill_color = QColor("#71717a") # Soft zinc steel when paused
            else:
                fill_color = self.accent_color if (self.accent_color and self.accent_color.isValid()) else QColor("#10b981")

            painter.setBrush(QBrush(fill_color))
            painter.drawRoundedRect(fill_rect, 2.5, 2.5)

        painter.restore()
