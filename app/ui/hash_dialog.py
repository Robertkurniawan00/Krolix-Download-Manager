"""
Krolix Download Manager - Hash Integrity Verification Dialog
Allows computing and comparing MD5, SHA-1, and SHA-256 checksums of downloaded files.
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QProgressBar, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt
from ..core.hasher import HashWorker

class HashDialog(QDialog):
    def __init__(self, file_path: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Verifikasi Integritas Berkas (Checksum / Hash) - Zero Assistant")
        self.resize(580, 420)
        self.file_path = file_path
        self.worker = None
        self.calculated_hashes = {}
        self.init_ui()

        if self.file_path and os.path.isfile(self.file_path):
            self.file_input.setText(self.file_path)
            self._start_hashing()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        layout.addWidget(QLabel("<b>Pilih Berkas yang Akan Diverifikasi:</b>"))
        file_row = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Pilih atau masukkan path berkas...")
        browse_btn = QPushButton("Pilih Berkas...")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self.file_input, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Siap menghitung hash...")
        self.status_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.status_lbl)

        # Hash Results
        layout.addWidget(QLabel("<b>Hasil Checksum / Hash:</b>"))

        # MD5
        layout.addWidget(QLabel("MD5:"))
        md5_row = QHBoxLayout()
        self.md5_input = QLineEdit()
        self.md5_input.setReadOnly(True)
        copy_md5 = QPushButton("Salin")
        copy_md5.clicked.connect(lambda: self._copy_to_clip(self.md5_input.text()))
        md5_row.addWidget(self.md5_input, 1)
        md5_row.addWidget(copy_md5)
        layout.addLayout(md5_row)

        # SHA-1
        layout.addWidget(QLabel("SHA-1:"))
        sha1_row = QHBoxLayout()
        self.sha1_input = QLineEdit()
        self.sha1_input.setReadOnly(True)
        copy_sha1 = QPushButton("Salin")
        copy_sha1.clicked.connect(lambda: self._copy_to_clip(self.sha1_input.text()))
        sha1_row.addWidget(self.sha1_input, 1)
        sha1_row.addWidget(copy_sha1)
        layout.addLayout(sha1_row)

        # SHA-256
        layout.addWidget(QLabel("SHA-256:"))
        sha256_row = QHBoxLayout()
        self.sha256_input = QLineEdit()
        self.sha256_input.setReadOnly(True)
        copy_sha256 = QPushButton("Salin")
        copy_sha256.clicked.connect(lambda: self._copy_to_clip(self.sha256_input.text()))
        sha256_row.addWidget(self.sha256_input, 1)
        sha256_row.addWidget(copy_sha256)
        layout.addLayout(sha256_row)

        # Hash comparison checker
        layout.addWidget(QLabel("<b>Bandingkan dengan Hash Asli (Checksum Checker):</b>"))
        self.compare_input = QLineEdit()
        self.compare_input.setPlaceholderText("Tempel checksum yang diberikan oleh situs penyedia unduhan...")
        self.compare_input.textChanged.connect(self._check_match)
        layout.addWidget(self.compare_input)

        self.match_lbl = QLabel("")
        self.match_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.match_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.calc_btn = QPushButton("Hitung Ulang")
        self.calc_btn.clicked.connect(self._start_hashing)
        btn_row.addWidget(self.calc_btn)

        close_btn = QPushButton("Tutup")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _browse_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Pilih Berkas untuk Hash")
        if f:
            self.file_input.setText(f)
            self._start_hashing()

    def _start_hashing(self):
        fpath = self.file_input.text().strip()
        if not fpath or not os.path.isfile(fpath):
            self.status_lbl.setText("Berkas tidak valid.")
            return

        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()

        self.progress_bar.setValue(0)
        self.status_lbl.setText("Menghitung MD5, SHA-1, dan SHA-256...")
        self.md5_input.clear()
        self.sha1_input.clear()
        self.sha256_input.clear()
        self.match_lbl.setText("")

        self.worker = HashWorker(fpath)
        self.worker.progress_updated.connect(self._on_progress)
        self.worker.hash_completed.connect(self._on_completed)
        self.worker.hash_failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            pct = int((current / total) * 100)
            self.progress_bar.setValue(pct)

    def _on_completed(self, results: dict):
        self.calculated_hashes = results
        self.progress_bar.setValue(100)
        self.md5_input.setText(results.get('md5', ''))
        self.sha1_input.setText(results.get('sha1', ''))
        self.sha256_input.setText(results.get('sha256', ''))
        self.status_lbl.setText(f"Kalkulasi selesai sempurna ({results.get('size', 0):,} bytes)")
        self._check_match()

    def _on_failed(self, err: str):
        self.status_lbl.setText(f"Gagal: {err}")

    def _copy_to_clip(self, text: str):
        if text:
            QApplication.clipboard().setText(text)
            self.status_lbl.setText("Checksum berhasil disalin ke papan klip.")

    def _check_match(self):
        expected = self.compare_input.text().strip().lower()
        if not expected or not self.calculated_hashes:
            self.match_lbl.setText("")
            self.compare_input.setStyleSheet("")
            return

        md5 = self.calculated_hashes.get('md5', '').lower()
        sha1 = self.calculated_hashes.get('sha1', '').lower()
        sha256 = self.calculated_hashes.get('sha256', '').lower()

        if expected in (md5, sha1, sha256):
            self.match_lbl.setText("CHECKSUM COCOK: Berkas 100% asli & integritas terjamin.")
            self.match_lbl.setStyleSheet("color: #22c55e; font-weight: bold;")
            self.compare_input.setStyleSheet("border: 1px solid #22c55e;")
        else:
            self.match_lbl.setText("CHECKSUM TIDAK COCOK: Kemungkinan berkas rusak atau dimodifikasi.")
            self.match_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
            self.compare_input.setStyleSheet("border: 1px solid #ef4444;")
