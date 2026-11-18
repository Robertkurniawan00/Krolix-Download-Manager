"""
Krolix Download Manager - File Conflict Resolution Dialog
Styled with Windows 11 Obsidian / Emerald Fluent Dark theme.
Prompts the user when a destination file already exists on disk.
"""

import os
import time
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt
from ..utils.helpers import format_bytes, apply_windows_dark_titlebar, get_app_icon


class FileConflictDialog(QDialog):
    ACTION_CANCEL = "cancel"
    ACTION_OVERWRITE = "overwrite"
    ACTION_RENAME = "rename"

    def __init__(self, filename: str, target_path: str, parent=None):
        super().__init__(parent)
        self.filename = filename
        self.target_path = target_path
        self.chosen_action = self.ACTION_CANCEL

        self.setWindowTitle("File Conflict - Krolix Download Manager")
        self.setFixedSize(480, 260)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        apply_windows_dark_titlebar(self)
        win_icon = get_app_icon()
        if win_icon and not win_icon.isNull():
            self.setWindowIcon(win_icon)

        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0c1017;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
            QLabel {
                color: #cbd5e1;
                font-family: 'Segoe UI', 'Inter', sans-serif;
                font-size: 12px;
            }
            QPushButton {
                font-family: 'Segoe UI', 'Inter', sans-serif;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 16px;
                border-radius: 6px;
            }
            QRadioButton {
                color: #e2e8f0;
                font-size: 12px;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
            QRadioButton::indicator:checked {
                background-color: #10b981;
                border: 2px solid #059669;
                border-radius: 8px;
            }
            QRadioButton::indicator:unchecked {
                background-color: #1e293b;
                border: 1px solid #475569;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # Header Info Row
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel("!")
        icon_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #f59e0b; padding: 2px 8px; border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 14px; background: rgba(245, 158, 11, 0.1);")
        header_row.addWidget(icon_lbl)

        info_col = QVBoxLayout()
        info_col.setSpacing(3)
        title_lbl = QLabel("<b>A file with the same name already exists:</b>")
        title_lbl.setStyleSheet("color: #f1f5f9; font-size: 13px;")
        fn_lbl = QLabel(f"<code style='color: #e2e8f0; font-family: Consolas;'>{self.filename}</code>")
        fn_lbl.setWordWrap(True)
        info_col.addWidget(title_lbl)
        info_col.addWidget(fn_lbl)

        header_row.addLayout(info_col, 1)
        layout.addLayout(header_row)

        # Existing File Metadata Card
        file_card = QFrame()
        file_card.setStyleSheet("""
            QFrame {
                background-color: #111827;
                border: 1px solid #1f2937;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        card_lay = QVBoxLayout(file_card)
        card_lay.setContentsMargins(10, 6, 10, 6)
        card_lay.setSpacing(4)

        existing_size = -1
        existing_mtime = ""
        try:
            if os.path.exists(self.target_path):
                existing_size = os.path.getsize(self.target_path)
                mtime_epoch = os.path.getmtime(self.target_path)
                existing_mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime_epoch))
        except Exception:
            pass

        size_text = format_bytes(existing_size) if existing_size >= 0 else "Unknown"
        mtime_text = existing_mtime if existing_mtime else "Unknown"

        card_meta = QLabel(
            f"<span style='color: #94a3b8;'>Existing file size:</span> <b>{size_text}</b> &nbsp;|&nbsp; "
            f"<span style='color: #94a3b8;'>Modified:</span> <b>{mtime_text}</b>"
        )
        card_meta.setStyleSheet("font-size: 11px; color: #cbd5e1;")
        card_lay.addWidget(card_meta)

        layout.addWidget(file_card)

        # Action Radio Options
        self.btn_group = QButtonGroup(self)
        self.radio_rename = QRadioButton("Auto-rename (create a unique numbered file)")
        self.radio_overwrite = QRadioButton("Overwrite existing file")
        self.radio_cancel = QRadioButton("Cancel this download")

        self.radio_rename.setChecked(True)
        self.btn_group.addButton(self.radio_rename)
        self.btn_group.addButton(self.radio_overwrite)
        self.btn_group.addButton(self.radio_cancel)

        options_col = QVBoxLayout()
        options_col.setSpacing(6)
        options_col.addWidget(self.radio_rename)
        options_col.addWidget(self.radio_overwrite)
        options_col.addWidget(self.radio_cancel)
        layout.addLayout(options_col)

        layout.addStretch()

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #ffffff;
            }
        """)
        cancel_btn.clicked.connect(self._on_cancel)

        ok_btn = QPushButton("Continue")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                border: 1px solid #059669;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        ok_btn.clicked.connect(self._on_confirm)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _on_confirm(self):
        if self.radio_overwrite.isChecked():
            self.chosen_action = self.ACTION_OVERWRITE
            self.accept()
        elif self.radio_rename.isChecked():
            self.chosen_action = self.ACTION_RENAME
            self.accept()
        else:
            self.chosen_action = self.ACTION_CANCEL
            self.reject()

    def _on_cancel(self):
        self.chosen_action = self.ACTION_CANCEL
        self.reject()
