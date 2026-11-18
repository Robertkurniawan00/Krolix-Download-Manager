"""
Krolix Download Manager v2.8 - Download Complete Dialog
Native File Integration:
- Title: "Download complete"
- Native File Type Icon (48x48 via QFileIconProvider)
- Metadata: "Download complete" header, "File:", "Size:", and "Save to:"
- Checkbox: "Don't show this dialog again"
- Buttons: [ Open ] [ Open with ] [ Open folder ] [ Close ]
- Krolix Drag & Drop Box: Enables dragging the downloaded file directly into other applications
- Dual Theme Support: Pixel-perfect Fluent Dark and Fluent Light integration
"""

import os
import subprocess
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QCheckBox, QFileIconProvider, QMessageBox, QApplication
)
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QDrag
from PyQt6.QtCore import Qt, QFileInfo, QUrl, QMimeData, QPoint, QRectF
from ..core.models import DownloadTask
from ..core.archive_extractor import ArchiveExtractor
from ..utils.helpers import format_bytes, apply_windows_dark_titlebar


class KrolixDragDropBox(QFrame):
    """
    Krolix Drag & Drop Target Widget.
    Allows the user to drag the downloaded file directly out of the dialog
    and drop it into another application (e.g. Media Player, Telegram, Discord, Premiere, Explorer).
    """
    def __init__(self, file_path: str, icon_pixmap: QPixmap = None, is_dark: bool = True, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.icon_pixmap = icon_pixmap
        self.is_dark = is_dark
        self._drag_start_pos = None

        self.setFixedSize(38, 38)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag and drop this icon to copy the downloaded file to another program or folder")

        bg = "#27272a" if is_dark else "#e5e7eb"
        border = "#3f3f46" if is_dark else "#cbd5e1"
        hover_bg = "#3f3f46" if is_dark else "#d1d5db"
        hover_border = "#2563eb" if is_dark else "#2563eb"

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 5px;
            }}
            QFrame:hover {{
                background-color: {hover_bg};
                border-color: {hover_border};
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self._drag_start_pos:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
        if not self.file_path or not os.path.exists(self.file_path):
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        url = QUrl.fromLocalFile(os.path.abspath(self.file_path))
        mime_data.setUrls([url])
        drag.setMimeData(mime_data)

        if self.icon_pixmap and not self.icon_pixmap.isNull():
            scaled = self.icon_pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            drag.setPixmap(scaled)
            drag.setHotSpot(QPoint(16, 16))

        drag.exec(Qt.DropAction.CopyAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Draw document icon with folded corner & export arrow
        pen_color = QColor("#94a3b8" if self.is_dark else "#4b5563")
        accent_color = QColor("#2563eb" if self.is_dark else "#2563eb")

        # Document outline
        painter.setPen(QPen(pen_color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        doc_x = 9
        doc_y = 7
        doc_w = 16
        doc_h = 22

        # Draw sheet
        painter.drawRoundedRect(QRectF(doc_x, doc_y, doc_w, doc_h), 2, 2)

        # Mini lines inside sheet
        painter.setPen(QPen(pen_color, 1.2))
        painter.drawLine(doc_x + 3, doc_y + 6, doc_x + doc_w - 4, doc_y + 6)
        painter.drawLine(doc_x + 3, doc_y + 11, doc_x + doc_w - 4, doc_y + 11)
        painter.drawLine(doc_x + 3, doc_y + 16, doc_x + doc_w - 7, doc_y + 16)

        # Small bottom-right drag arrow
        painter.setPen(QPen(accent_color, 1.8))
        painter.drawLine(23, 27, 30, 27)
        painter.drawLine(27, 23, 30, 27)
        painter.drawLine(27, 31, 30, 27)


class DownloadCompleteDialog(QDialog):
    """
    Krolix Download Manager Complete Dialog.
    Native file integration and quick drag-drop workflow.
    """
    def __init__(self, task: DownloadTask, db=None, parent=None):
        super().__init__(parent)
        self.task = task
        self.db = db

        self.setWindowTitle("Download complete")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setFixedWidth(510)
        self.setFixedHeight(210)

        # Determine theme mode
        self.is_dark = True
        theme_name = "mica_dark"
        accent_key = "blue"
        if self.db:
            theme_name = self.db.get_setting("ui_theme", "mica_dark")
            accent_key = self.db.get_setting("ui_accent", "blue")
            self.is_dark = (theme_name != "fluent_light")

        if self.is_dark:
            apply_windows_dark_titlebar(self)

        self._setup_palette_and_styles(theme_name, accent_key)
        self._init_ui()

    def _setup_palette_and_styles(self, theme_name: str, accent_key: str):
        # Clean native desktop color palettes (no AI-slop neon cyans)
        if self.is_dark:
            self.col_bg = "#18181b"
            self.col_card = "#202023"
            self.col_border = "#333338"
            self.col_text_header = "#f8fafc"
            self.col_text_label = "#9ca3af"
            self.col_text_val = "#f1f5f9"
            self.col_text_size = "#e2e8f0"
            self.col_btn_bg = "#27272a"
            self.col_btn_hover = "#3f3f46"
            self.col_btn_border = "#3f3f46"
            self.col_btn_text = "#e2e8f0"
            self.col_btn_hover_text = "#ffffff"
        else:
            self.col_bg = "#f3f4f6"
            self.col_card = "#ffffff"
            self.col_border = "#d1d5db"
            self.col_text_header = "#111827"
            self.col_text_label = "#6b7280"
            self.col_text_val = "#111827"
            self.col_text_size = "#1f2937"
            self.col_btn_bg = "#ffffff"
            self.col_btn_hover = "#f9fafb"
            self.col_btn_border = "#d1d5db"
            self.col_btn_text = "#374151"
            self.col_btn_hover_text = "#111827"

        # Sober native accents
        accent_map = {
            "chrome": ("#94a3b8", "#cbd5e1", "#64748b"),
            "titanium": ("#64748b", "#94a3b8", "#475569"),
            "blue": ("#2563eb", "#3b82f6", "#1d4ed8"),
            "cyan": ("#0284c7", "#0369a1", "#075985"),
            "emerald": ("#10b981", "#34d399", "#059669"),
            "violet": ("#7c3aed", "#8b5cf6", "#6d28d9"),
            "amber": ("#d97706", "#f59e0b", "#b45309"),
            "rose": ("#e11d48", "#f43f5e", "#be123c"),
            "sky_blue": ("#0284c7", "#2563eb", "#1d4ed8")
        }
        self.acc_pri, self.acc_hover, self.acc_dark = accent_map.get(accent_key, ("#94a3b8", "#cbd5e1", "#64748b"))

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {self.col_bg};
                border: 1px solid {self.col_border};
            }}
            QLabel {{
                font-family: 'Segoe UI Variable Text', 'Segoe UI', Tahoma, sans-serif;
            }}
        """)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # =========================================================================
        # 1. Top Section: 48x48 File Icon + Info Card (Download complete, File, Size, Save to)
        # =========================================================================
        top_row = QHBoxLayout()
        top_row.setSpacing(14)
        top_row.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 48x48 File Icon
        actual_path = self.task.save_path if (self.task.save_path and os.path.exists(self.task.save_path)) else ""
        self.icon_pixmap = None

        if actual_path:
            provider = QFileIconProvider()
            sh_icon = provider.icon(QFileInfo(actual_path))
            if not sh_icon.isNull():
                self.icon_pixmap = sh_icon.pixmap(48, 48)
                self.setWindowIcon(sh_icon)
        elif self.task.filename:
            provider = QFileIconProvider()
            dummy_info = QFileInfo(self.task.filename)
            sh_icon = provider.icon(dummy_info)
            if not sh_icon.isNull():
                self.icon_pixmap = sh_icon.pixmap(48, 48)
                self.setWindowIcon(sh_icon)

        if not self.icon_pixmap or self.icon_pixmap.isNull():
            logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "logo_48.png"))
            if os.path.exists(logo_path):
                self.icon_pixmap = QPixmap(logo_path).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.setWindowIcon(QIcon(logo_path))

        lbl_file_icon = QLabel()
        lbl_file_icon.setFixedSize(48, 48)
        lbl_file_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.icon_pixmap and not self.icon_pixmap.isNull():
            lbl_file_icon.setPixmap(self.icon_pixmap)
        else:
            from .fluent_icons import FluentIconFactory
            lbl_file_icon.setPixmap(FluentIconFactory.create_folder_icon(color="#94a3b8", size=40).pixmap(40, 40))

        top_row.addWidget(lbl_file_icon, 0, Qt.AlignmentFlag.AlignTop)

        # Text Metadata Area
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        info_layout.setContentsMargins(0, 0, 0, 0)

        # 1.1 Header: "Download complete"
        lbl_hdr = QLabel("Download complete")
        lbl_hdr.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {self.col_text_header};")
        info_layout.addWidget(lbl_hdr)

        # 1.2 File Name Row
        row_file = QHBoxLayout()
        row_file.setSpacing(6)
        lbl_file_tag = QLabel("File:")
        lbl_file_tag.setFixedWidth(52)
        lbl_file_tag.setStyleSheet(f"font-size: 11px; color: {self.col_text_label}; font-weight: 500;")
        
        lbl_filename = QLabel(self.task.filename)
        lbl_filename.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {self.col_text_val};")
        lbl_filename.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl_filename.setToolTip(self.task.save_path or self.task.filename)
        row_file.addWidget(lbl_file_tag)
        row_file.addWidget(lbl_filename, 1)
        info_layout.addLayout(row_file)

        # 1.3 Size Row
        row_size = QHBoxLayout()
        row_size.setSpacing(6)
        lbl_size_tag = QLabel("Size:")
        lbl_size_tag.setFixedWidth(52)
        lbl_size_tag.setStyleSheet(f"font-size: 11px; color: {self.col_text_label}; font-weight: 500;")

        filesize = os.path.getsize(self.task.save_path) if (actual_path and os.path.isfile(actual_path)) else self.task.downloaded_bytes
        if filesize > 0:
            size_formatted = format_bytes(filesize)
        else:
            size_formatted = "Complete"
        
        lbl_size_val = QLabel(size_formatted)
        lbl_size_val.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {self.col_text_size};")
        row_size.addWidget(lbl_size_tag)
        row_size.addWidget(lbl_size_val, 1)
        info_layout.addLayout(row_size)

        # 1.4 Save to Row (Clickable to open folder directly)
        row_save = QHBoxLayout()
        row_save.setSpacing(6)
        lbl_save_tag = QLabel("Save to:")
        lbl_save_tag.setFixedWidth(52)
        lbl_save_tag.setStyleSheet(f"font-size: 11px; color: {self.col_text_label}; font-weight: 500;")

        save_folder = os.path.dirname(self.task.save_path) if self.task.save_path else os.path.expanduser("~/Downloads")
        lbl_save_val = QLabel(save_folder)
        lbl_save_val.setStyleSheet(f"font-size: 11px; color: {self.col_text_val};")
        lbl_save_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl_save_val.setCursor(Qt.CursorShape.PointingHandCursor)
        lbl_save_val.setToolTip(f"Click to open folder:\n{save_folder}")
        lbl_save_val.mousePressEvent = lambda e: self._open_folder()
        row_save.addWidget(lbl_save_tag)
        row_save.addWidget(lbl_save_val, 1)
        info_layout.addLayout(row_save)

        top_row.addLayout(info_layout, 1)
        main_layout.addLayout(top_row)

        # =========================================================================
        # 2. Checkbox: "Don't show this dialog again"
        # =========================================================================
        self.chk_dont_show = QCheckBox("Don't show this dialog again")
        is_disabled = False
        if self.db:
            is_disabled = (self.db.get_setting("show_complete_dialog", "true") == "false")
        self.chk_dont_show.setChecked(is_disabled)

        chk_bg = "#27272a" if self.is_dark else "#ffffff"
        chk_border = "#3f3f46" if self.is_dark else "#9ca3af"
        self.chk_dont_show.setStyleSheet(f"""
            QCheckBox {{
                color: {self.col_text_label};
                font-size: 11px;
                spacing: 6px;
            }}
            QCheckBox:hover {{
                color: {self.col_text_val};
            }}
            QCheckBox::indicator {{
                width: 13px;
                height: 13px;
                border: 1px solid {chk_border};
                border-radius: 2px;
                background-color: {chk_bg};
            }}
            QCheckBox::indicator:checked {{
                background-color: {self.acc_pri};
                border-color: {self.acc_pri};
            }}
        """)
        self.chk_dont_show.toggled.connect(self._on_dont_show_toggled)
        main_layout.addWidget(self.chk_dont_show)

        # Subtle separator before button bar
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {self.col_border}; background-color: {self.col_border}; border: none; height: 1px;")
        main_layout.addWidget(sep)

        # =========================================================================
        # 3. Action Buttons Row: [ Open ] [ Open with ] [ Open folder ] [ Close ]  [ Drag & Drop ]
        # =========================================================================
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_common_style = f"""
            QPushButton {{
                background-color: {self.col_btn_bg};
                color: {self.col_btn_text};
                border: 1px solid {self.col_btn_border};
                border-radius: 4px;
                padding: 5px 14px;
                font-size: 11px;
                min-height: 16px;
            }}
            QPushButton:hover {{
                background-color: {self.col_btn_hover};
                color: {self.col_btn_hover_text};
                border-color: {self.acc_pri};
            }}
            QPushButton:pressed {{
                background-color: {self.col_border};
            }}
        """

        # 3.1 Open Button (Primary / Default)
        self.btn_open = QPushButton("Open")
        self.btn_open.setDefault(True)
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.acc_pri};
                color: #ffffff;
                border: 1px solid {self.acc_pri};
                border-radius: 4px;
                padding: 5px 18px;
                font-weight: 600;
                font-size: 11px;
                min-height: 16px;
            }}
            QPushButton:hover {{
                background-color: {self.acc_hover};
                border-color: {self.acc_hover};
            }}
            QPushButton:pressed {{
                background-color: {self.acc_dark};
            }}
        """)
        self.btn_open.clicked.connect(self._open_file)
        btn_row.addWidget(self.btn_open)

        # 3.2 Open with... Button
        self.btn_open_with = QPushButton("Open with")
        self.btn_open_with.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_with.setStyleSheet(btn_common_style)
        self.btn_open_with.clicked.connect(self._open_with)
        btn_row.addWidget(self.btn_open_with)

        # 3.3 Open folder Button
        self.btn_folder = QPushButton("Open folder")
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.setStyleSheet(btn_common_style)
        self.btn_folder.clicked.connect(self._open_folder)
        btn_row.addWidget(self.btn_folder)

        # 3.4 Contextual Extract Button (for archives)
        if self.task.save_path and ArchiveExtractor.is_archive(self.task.save_path):
            self.btn_extract = QPushButton("Extract")
            self.btn_extract.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_extract.setStyleSheet(btn_common_style)
            self.btn_extract.clicked.connect(self._extract_archive)
            btn_row.addWidget(self.btn_extract)

        # 3.5 Close Button
        self.btn_close = QPushButton("Close")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet(btn_common_style)
        self.btn_close.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_close)

        btn_row.addStretch()

        # Drag & Drop Box
        drag_target_path = actual_path if actual_path else (self.task.save_path or "")
        self.drag_box = KrolixDragDropBox(
            file_path=drag_target_path,
            icon_pixmap=self.icon_pixmap,
            is_dark=self.is_dark,
            parent=self
        )
        btn_row.addWidget(self.drag_box)

        main_layout.addLayout(btn_row)

    def _open_file(self):
        target_path = self.task.save_path
        self.accept()
        if target_path and os.path.exists(target_path):
            try:
                os.startfile(target_path)
            except Exception as e:
                QMessageBox.warning(None, "Error Opening File", f"Could not open file:\n{e}")
        else:
            QMessageBox.information(None, "File Missing", "The downloaded file could not be found on disk.")

    def _open_with(self):
        target_path = self.task.save_path
        self.accept()
        if target_path and os.path.exists(target_path):
            abs_p = os.path.abspath(target_path)
            try:
                subprocess.Popen(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", abs_p])
            except Exception:
                try:
                    os.startfile(abs_p)
                except Exception as e:
                    QMessageBox.warning(None, "Error Opening File", f"Could not launch Open With dialog:\n{e}")
        else:
            QMessageBox.information(None, "File Missing", "The downloaded file could not be found on disk.")

    def _open_folder(self):
        target_path = self.task.save_path
        self.accept()
        if target_path and os.path.exists(target_path):
            try:
                subprocess.Popen(["explorer", f"/select,{os.path.abspath(target_path)}"])
            except Exception:
                try:
                    os.startfile(os.path.dirname(target_path))
                except Exception:
                    pass
        elif target_path:
            folder = os.path.dirname(target_path)
            if os.path.exists(folder):
                os.startfile(folder)

    def _extract_archive(self):
        if self.task.save_path and os.path.exists(self.task.save_path):
            success, res = ArchiveExtractor.extract(self.task.save_path)
            if success:
                QMessageBox.information(self, "Extraction Complete", f"Successfully extracted to:\n{res}")
                if os.path.exists(res):
                    os.startfile(res)
            else:
                QMessageBox.warning(self, "Extraction Failed", f"Error extracting archive:\n{res}")
        self.accept()

    def _on_dont_show_toggled(self, checked: bool):
        """
        Completion Logic:
        When checked ("Don't show this dialog again"), show_complete_dialog = "false"
        When unchecked, show_complete_dialog = "true"
        """
        if self.db:
            val = "false" if checked else "true"
            self.db.set_setting("show_complete_dialog", val)


KrolixDragDropBox = KrolixDragDropBox
