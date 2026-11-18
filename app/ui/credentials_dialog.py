"""
Krolix Download Manager - Site Credentials Manager Dialog
Allows users to save and manage HTTP/FTP authentication logins for protected websites.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QMessageBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from ..core.database import Database
from ..utils.helpers import apply_windows_dark_titlebar


class CredentialsDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Site Logins & Credentials")
        self.resize(560, 380)
        apply_windows_dark_titlebar(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header info
        lbl_info = QLabel("Manage saved HTTP / FTP site credentials for automated authentication:")
        lbl_info.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(lbl_info)

        # Table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Domain / URL", "Username", "Password"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_add = QPushButton("+ Add Site")
        self.btn_add.clicked.connect(self._add_credential)
        btn_layout.addWidget(self.btn_add)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self._delete_credential)
        btn_layout.addWidget(self.btn_delete)

        btn_layout.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        self._load_credentials()

    def _load_credentials(self):
        self.table.setRowCount(0)
        try:
            creds = self.db.get_all_credentials()
            for r, c in enumerate(creds):
                self.table.insertRow(r)
                domain_item = QTableWidgetItem(c.get("domain", ""))
                user_item = QTableWidgetItem(c.get("username", ""))
                pwd_item = QTableWidgetItem("••••••••")
                pwd_item.setData(Qt.ItemDataRole.UserRole, c.get("password", ""))

                self.table.setItem(r, 0, domain_item)
                self.table.setItem(r, 1, user_item)
                self.table.setItem(r, 2, pwd_item)
        except Exception as e:
            print(f"[!] Error loading credentials: {e}")

    def _add_credential(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Site Login")
        dlg.resize(360, 200)
        apply_windows_dark_titlebar(dlg)

        vbox = QVBoxLayout(dlg)
        vbox.setSpacing(10)

        vbox.addWidget(QLabel("Domain / Host (e.g. example.com):"))
        txt_domain = QLineEdit()
        txt_domain.setPlaceholderText("example.com")
        vbox.addWidget(txt_domain)

        vbox.addWidget(QLabel("Username / Email:"))
        txt_user = QLineEdit()
        vbox.addWidget(txt_user)

        vbox.addWidget(QLabel("Password:"))
        txt_pwd = QLineEdit()
        txt_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        vbox.addWidget(txt_pwd)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        vbox.addWidget(btn_box)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            dom = txt_domain.text().strip()
            user = txt_user.text().strip()
            pwd = txt_pwd.text()
            if dom:
                self.db.save_credential(dom, user, pwd)
                self._load_credentials()

    def _delete_credential(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if not item:
            return
        dom = item.text()
        res = QMessageBox.question(
            self,
            "Delete Credential",
            f"Are you sure you want to remove saved credentials for '{dom}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.db.delete_credential(dom)
            self._load_credentials()
