import time
import urllib.request
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QLineEdit, QComboBox,
    QSpinBox, QMessageBox, QWidget, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread

from ..core.database import Database
from ..utils.helpers import apply_windows_dark_titlebar


class ProxyTestWorker(QThread):
    result_ready = pyqtSignal(str, bool, float, str)  # proxy_id, success, latency, msg

    def __init__(self, proxies_to_test):
        super().__init__()
        self.proxies_to_test = proxies_to_test  # list of proxy dicts

    def run(self):
        for p in self.proxies_to_test:
            proxy_id = p.get('id')
            p_type = p.get('type', 'http').lower()
            host = p.get('host', '')
            port = p.get('port', 8080)
            user = p.get('username', '')
            pwd = p.get('password', '')

            # Build proxy URL
            auth = f"{user}:{pwd}@" if user and pwd else ""
            if p_type in ('socks4', 'socks5'):
                proxy_url = f"{p_type}://{auth}{host}:{port}"
            else:
                proxy_url = f"http://{auth}{host}:{port}"
            proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
            opener = urllib.request.build_opener(proxy_handler)

            start_time = time.time()
            try:
                resp = opener.open("http://api.ipify.org", timeout=5)
                resp.read()
                latency = (time.time() - start_time) * 1000
                self.result_ready.emit(proxy_id, True, latency, "OK")
            except Exception as e:
                self.result_ready.emit(proxy_id, False, 0.0, str(e))




class ProxyManagerDialog(QDialog):
    proxy_selected = pyqtSignal(dict)

    def __init__(self, db_or_parent=None, parent=None):
        from PyQt6.QtWidgets import QWidget
        if isinstance(db_or_parent, QWidget):
            super().__init__(db_or_parent)
            self.db = Database.get_instance()
        else:
            super().__init__(parent)
            self.db = db_or_parent or Database.get_instance()

        self.setWindowTitle("Manajer Proxy")
        self.resize(800, 500)
        self.setMinimumSize(700, 450)
        
        apply_windows_dark_titlebar(self)
        self.proxies = []
        self._test_worker = None
        self._editing_proxy_id = None

        self._setup_style()
        self._init_ui()
        self._load_proxies()

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0b0f17;
                color: #e2e8f0;
                font-family: 'Segoe UI Variable Display', 'Segoe UI', -apple-system, sans-serif;
            }
            QTableWidget {
                background-color: #0f1522;
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 8px;
                gridline-color: rgba(255, 255, 255, 0.04);
                color: #e2e8f0;
                font-size: 13px;
                selection-background-color: rgba(255, 255, 255, 0.08);
                selection-color: #ffffff;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            QHeaderView::section {
                background-color: #151b28;
                color: #94a3b8;
                font-weight: 600;
                padding: 6px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            QFrame#InlineForm {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #151b28, stop:1 #0f1522);
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 8px;
                padding: 10px;
            }
            QLineEdit, QSpinBox, QComboBox {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                color: #ffffff;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border: 1px solid #475569;
                background-color: rgba(255, 255, 255, 0.08);
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                color: #cbd5e1;
                font-size: 12px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QPushButton#PrimaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2b3648, stop:1 #1e2635);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 8px;
                color: #f8fafc;
                font-weight: 600;
            }
            QPushButton#PrimaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #37455c, stop:1 #273347);
                border: 1px solid rgba(255, 255, 255, 0.25);
            }
            QPushButton#DangerBtn {
                background-color: rgba(244, 63, 94, 0.08);
                border: 1px solid rgba(244, 63, 94, 0.2);
                color: #fda4af;
            }
            QPushButton#DangerBtn:hover {
                background-color: rgba(244, 63, 94, 0.16);
            }
        """)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # 1. Action Buttons Top
        top_bar = QHBoxLayout()
        self.btn_add = QPushButton("+ Tambah")
        self.btn_add.clicked.connect(self._on_add_clicked)
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        self.btn_delete = QPushButton("Hapus")
        self.btn_delete.setObjectName("DangerBtn")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_test = QPushButton("Test")
        self.btn_test.clicked.connect(self._on_test_clicked)
        self.btn_test_all = QPushButton("Test Semua")
        self.btn_test_all.clicked.connect(self._on_test_all_clicked)

        top_bar.addWidget(self.btn_add)
        top_bar.addWidget(self.btn_edit)
        top_bar.addWidget(self.btn_delete)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_test)
        top_bar.addWidget(self.btn_test_all)
        root.addLayout(top_bar)

        # 2. Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Nama", "Tipe", "Host:Port", "Autentikasi", "Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        root.addWidget(self.table, 1)

        # 3. Inline Form (Hidden by default)
        self.form_frame = QFrame()
        self.form_frame.setObjectName("InlineForm")
        self.form_frame.setVisible(False)
        form_layout = QVBoxLayout(self.form_frame)
        form_layout.setContentsMargins(10, 10, 10, 10)
        
        row1 = QHBoxLayout()
        self.inp_name = QLineEdit()
        self.inp_name.setPlaceholderText("Nama")
        self.inp_type = QComboBox()
        self.inp_type.addItems(["HTTP", "HTTPS", "SOCKS4", "SOCKS5"])
        self.inp_host = QLineEdit()
        self.inp_host.setPlaceholderText("Host / IP")
        self.inp_port = QSpinBox()
        self.inp_port.setRange(1, 65535)
        self.inp_port.setValue(8080)
        row1.addWidget(QLabel("Nama:"))
        row1.addWidget(self.inp_name, 1)
        row1.addWidget(QLabel("Tipe:"))
        row1.addWidget(self.inp_type)
        row1.addWidget(QLabel("Host:"))
        row1.addWidget(self.inp_host, 1)
        row1.addWidget(QLabel("Port:"))
        row1.addWidget(self.inp_port)
        form_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.inp_user = QLineEdit()
        self.inp_user.setPlaceholderText("Username (opsional)")
        self.inp_pass = QLineEdit()
        self.inp_pass.setPlaceholderText("Password (opsional)")
        self.inp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.btn_save = QPushButton("Simpan")
        self.btn_save.setObjectName("PrimaryBtn")
        self.btn_save.clicked.connect(self._on_save_clicked)
        self.btn_cancel = QPushButton("Batal")
        self.btn_cancel.clicked.connect(lambda: self.form_frame.setVisible(False))

        row2.addWidget(QLabel("Auth:"))
        row2.addWidget(self.inp_user, 1)
        row2.addWidget(self.inp_pass, 1)
        row2.addStretch()
        row2.addWidget(self.btn_cancel)
        row2.addWidget(self.btn_save)
        form_layout.addLayout(row2)
        
        root.addWidget(self.form_frame)

        # 4. Bottom Action Row
        bottom_bar = QHBoxLayout()
        self.btn_global = QPushButton("Jadikan Global")
        self.btn_global.clicked.connect(self._on_global_clicked)
        self.btn_apply = QPushButton("Terapkan ke Task")
        self.btn_apply.setObjectName("PrimaryBtn")
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        self.btn_close = QPushButton("Tutup")
        self.btn_close.clicked.connect(self.accept)

        bottom_bar.addWidget(self.btn_global)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.btn_apply)
        bottom_bar.addWidget(self.btn_close)
        root.addLayout(bottom_bar)

    def _load_proxies(self):
        try:
            self.proxies = self.db.get_proxies()
        except AttributeError:
            self.proxies = [] # fallback if db method not available
            
        self.table.setRowCount(len(self.proxies))
        for row, p in enumerate(self.proxies):
            self._update_table_row(row, p)

    def _update_table_row(self, row, proxy, status_text=None):
        # Nama
        name_item = QTableWidgetItem(proxy.get("name", "Unnamed"))
        name_item.setData(Qt.ItemDataRole.UserRole, proxy)
        self.table.setItem(row, 0, name_item)

        # Tipe
        self.table.setItem(row, 1, QTableWidgetItem(proxy.get("type", "HTTP")))

        # Host:Port
        self.table.setItem(row, 2, QTableWidgetItem(f"{proxy.get('host', '')}:{proxy.get('port', '')}"))

        # Auth
        has_auth = bool(proxy.get("username") or proxy.get("password"))
        self.table.setItem(row, 3, QTableWidgetItem("Ya" if has_auth else "Tidak"))

        # Status
        if status_text is None:
            status_text = "-"
        st_item = QTableWidgetItem(status_text)
        self.table.setItem(row, 4, st_item)

    def _on_add_clicked(self):
        self._editing_proxy_id = None
        self.inp_name.clear()
        self.inp_type.setCurrentIndex(0)
        self.inp_host.clear()
        self.inp_port.setValue(8080)
        self.inp_user.clear()
        self.inp_pass.clear()
        self.form_frame.setVisible(True)

    def _on_edit_clicked(self):
        row = self.table.currentRow()
        if row < 0:
            return
        
        proxy = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self._editing_proxy_id = proxy.get("id")
        self.inp_name.setText(proxy.get("name", ""))
        self.inp_type.setCurrentText(proxy.get("type", "HTTP"))
        self.inp_host.setText(proxy.get("host", ""))
        self.inp_port.setValue(int(proxy.get("port", 8080)))
        self.inp_user.setText(proxy.get("username", ""))
        self.inp_pass.setText(proxy.get("password", ""))
        self.form_frame.setVisible(True)

    def _on_save_clicked(self):
        import uuid
        name = self.inp_name.text().strip()
        host = self.inp_host.text().strip()
        if not name or not host:
            QMessageBox.warning(self, "Error", "Nama dan Host harus diisi.")
            return
            
        proxy_id = self._editing_proxy_id or str(uuid.uuid4())
        
        proxy_dict = {
            "id": proxy_id,
            "name": name,
            "type": self.inp_type.currentText(),
            "host": host,
            "port": self.inp_port.value(),
            "username": self.inp_user.text(),
            "password": self.inp_pass.text()
        }
        
        try:
            self.db.save_proxy(proxy_dict)
        except AttributeError:
            pass # fallback if not fully implemented
            
        self.form_frame.setVisible(False)
        self._load_proxies()

    def _on_delete_clicked(self):
        row = self.table.currentRow()
        if row < 0:
            return
        proxy = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(self, "Hapus Proxy", f"Yakin hapus proxy '{proxy.get('name')}'?")
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.db.delete_proxy(proxy.get("id"))
            except AttributeError:
                pass
            self._load_proxies()

    def _on_test_clicked(self):
        row = self.table.currentRow()
        if row < 0:
            return
        proxy = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self._run_tests([proxy])

    def _on_test_all_clicked(self):
        if not self.proxies:
            return
        self._run_tests(self.proxies)

    def _run_tests(self, proxies_list):
        for p in proxies_list:
            # Set to pending
            self._update_proxy_status(p.get("id"), "Menguji...")
            
        self._test_worker = ProxyTestWorker(proxies_list)
        self._test_worker.result_ready.connect(self._on_test_result)
        self._test_worker.start()

    def _on_test_result(self, proxy_id, success, latency, msg):
        status_text = f"OK ({latency:.0f}ms)" if success else "Gagal"
        self._update_proxy_status(proxy_id, status_text)

    def _update_proxy_status(self, proxy_id, status_text):
        for row in range(self.table.rowCount()):
            proxy = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if proxy.get("id") == proxy_id:
                self.table.setItem(row, 4, QTableWidgetItem(status_text))
                break

    def _on_global_clicked(self):
        row = self.table.currentRow()
        if row < 0:
            return
        proxy = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        try:
            self.db.set_global_proxy(proxy.get("id"))
            QMessageBox.information(self, "Sukses", f"Proxy '{proxy.get('name')}' diset sebagai global.")
        except AttributeError:
            pass

    def _on_apply_clicked(self):
        row = self.table.currentRow()
        if row < 0:
            return
        proxy = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.proxy_selected.emit(proxy)
        self.accept()
