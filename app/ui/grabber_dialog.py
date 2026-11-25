"""
Krolix Download Manager v2.8 - Site Grabber & Crawler Wizard UI
Features:
- 4-Step Wizard:
  1. Target URL, Project Name & Domain Boundaries
  2. Save Directory & Category Routing
  3. Depth Explorer & File Filter Presets (Video, Audio, Images, Docs, Archives, Programs)
  4. Real-time Crawling Table, Probed Sizes, Quick Filtering & Batch Queue Injection
- Fluent Dark Obsidian styling with smooth step transitions
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QCheckBox, QGroupBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QProgressBar, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from ..core.site_grabber import SiteCrawler, GrabbedItem
from ..utils.helpers import apply_windows_dark_titlebar, format_bytes


class GrabberBridge(QObject):
    item_found = pyqtSignal(object)
    progress_updated = pyqtSignal(int, int)
    crawl_finished = pyqtSignal(list)


class GrabberDialog(QDialog):
    """
    Site Grabber 4-Step Wizard Dialog.
    """
    def __init__(self, default_url: str = "", default_save_dir: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Site Grabber Wizard")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(880, 620)
        self.setMinimumSize(780, 520)
        apply_windows_dark_titlebar(self)

        self.default_url = default_url.strip()
        self.default_save_dir = default_save_dir or os.path.join(os.path.expanduser("~"), "Downloads")

        self.crawler: SiteCrawler = None
        self.bridge = GrabberBridge()
        self.bridge.item_found.connect(self._on_item_found)
        self.bridge.progress_updated.connect(self._on_progress_updated)
        self.bridge.crawl_finished.connect(self._on_crawl_finished)

        self.found_items: list[GrabbedItem] = []
        self.results: dict = {}

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # Header Title Bar & Step Indicator
        self.header_frame = QFrame()
        self.header_frame.setObjectName("GrabberHeaderFrame")
        self.header_frame.setStyleSheet("""
            #GrabberHeaderFrame {
                background-color: #161c28;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 12px;
            }
        """)
        h_header = QHBoxLayout(self.header_frame)
        h_header.setContentsMargins(12, 8, 12, 8)

        v_head_info = QVBoxLayout()
        self.lbl_step_title = QLabel("Step 1: Set Start Page and Project Name")
        self.lbl_step_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f1f5f9;")
        self.lbl_step_desc = QLabel("Specify the target website URL and domain boundary rules.")
        self.lbl_step_desc.setStyleSheet("font-size: 12px; color: #94a3b8;")
        v_head_info.addWidget(self.lbl_step_title)
        v_head_info.addWidget(self.lbl_step_desc)
        h_header.addLayout(v_head_info, 1)

        self.lbl_step_num = QLabel("Step 1 of 4")
        self.lbl_step_num.setStyleSheet("font-size: 13px; font-weight: 600; color: #10b981; padding: 4px 10px; background: rgba(16, 185, 129, 0.12); border-radius: 6px;")
        h_header.addWidget(self.lbl_step_num)
        main_layout.addWidget(self.header_frame)

        # Stacked Pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._create_step1_widget())
        self.stack.addWidget(self._create_step2_widget())
        self.stack.addWidget(self._create_step3_widget())
        self.stack.addWidget(self._create_step4_widget())
        main_layout.addWidget(self.stack, 1)

        # Navigation Buttons Bar
        self.nav_frame = QFrame()
        h_nav = QHBoxLayout(self.nav_frame)
        h_nav.setContentsMargins(0, 0, 0, 0)
        h_nav.setSpacing(10)

        self.btn_back = QPushButton("◀ Back")
        self.btn_back.setEnabled(False)
        self.btn_back.clicked.connect(self._go_back)
        self.btn_back.setFixedHeight(36)
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.setObjectName("AccentButton")
        self.btn_next.setDefault(True)
        self.btn_next.clicked.connect(self._go_next)
        self.btn_next.setFixedHeight(36)
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)

        h_nav.addWidget(self.btn_cancel)
        h_nav.addStretch(1)
        h_nav.addWidget(self.btn_back)
        h_nav.addWidget(self.btn_next)
        main_layout.addWidget(self.nav_frame)

    def _create_step1_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(14)

        grp_start = QGroupBox("Target Website Address")
        v_start = QVBoxLayout(grp_start)
        v_start.setSpacing(8)

        v_start.addWidget(QLabel("Start Page (URL):"))
        self.txt_url = QLineEdit(self.default_url or "https://")
        self.txt_url.setPlaceholderText("https://example.com/gallery")
        self.txt_url.setFixedHeight(36)
        v_start.addWidget(self.txt_url)

        h_proj = QHBoxLayout()
        h_proj.addWidget(QLabel("Project Name:"))
        self.txt_project = QLineEdit("My Site Grabber Project")
        self.txt_project.setFixedHeight(32)
        h_proj.addWidget(self.txt_project, 1)
        v_start.addLayout(h_proj)
        layout.addWidget(grp_start)

        grp_bounds = QGroupBox("Domain Boundary & Crawl Scope")
        v_bounds = QVBoxLayout(grp_bounds)
        self.chk_stay_domain = QCheckBox("Stay on the same domain / host (Ignore external domain links)")
        self.chk_stay_domain.setChecked(True)
        v_bounds.addWidget(self.chk_stay_domain)

        self.chk_allow_subdomains = QCheckBox("Include sub-domains of the main website")
        self.chk_allow_subdomains.setChecked(True)
        v_bounds.addWidget(self.chk_allow_subdomains)
        layout.addWidget(grp_bounds)

        layout.addStretch(1)
        return w

    def _create_step2_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(14)

        grp_save = QGroupBox("Save Directory on Local Disk")
        v_save = QVBoxLayout(grp_save)
        v_save.setSpacing(10)

        v_save.addWidget(QLabel("Download destination folder:"))
        h_dir = QHBoxLayout()
        self.txt_save_dir = QLineEdit(self.default_save_dir)
        self.txt_save_dir.setFixedHeight(36)
        btn_browse = QPushButton("Browse...")
        btn_browse.setFixedHeight(36)
        btn_browse.clicked.connect(self._browse_save_dir)
        h_dir.addWidget(self.txt_save_dir, 1)
        h_dir.addWidget(btn_browse)
        v_save.addLayout(h_dir)
        layout.addWidget(grp_save)

        grp_org = QGroupBox("Organization & Folder Structure")
        v_org = QVBoxLayout(grp_org)
        self.chk_subfolders = QCheckBox("Auto-route into category subfolders (Images, Videos, Audio, Documents, etc.)")
        self.chk_subfolders.setChecked(True)
        v_org.addWidget(self.chk_subfolders)

        self.chk_create_proj_folder = QCheckBox("Create a separate project folder inside the download directory")
        self.chk_create_proj_folder.setChecked(True)
        v_org.addWidget(self.chk_create_proj_folder)
        layout.addWidget(grp_org)

        layout.addStretch(1)
        return w

    def _create_step3_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(14)

        # Depth Scope
        grp_depth = QGroupBox("Exploration Depth & Limits")
        v_depth = QVBoxLayout(grp_depth)
        h_depth = QHBoxLayout()
        h_depth.addWidget(QLabel("Exploration Depth:"))
        self.spn_depth = QSpinBox()
        self.spn_depth.setRange(1, 6)
        self.spn_depth.setValue(2)
        self.spn_depth.setSuffix(" levels")
        h_depth.addWidget(self.spn_depth)
        h_depth.addSpacing(20)

        h_depth.addWidget(QLabel("Max Pages to Scan:"))
        self.spn_max_pages = QSpinBox()
        self.spn_max_pages.setRange(5, 1000)
        self.spn_max_pages.setValue(100)
        h_depth.addWidget(self.spn_max_pages)
        h_depth.addStretch(1)
        v_depth.addLayout(h_depth)

        lbl_depth_tip = QLabel("• Depth 1: Only media directly linked on the start page.\n• Depth 2: Media on start page + all links found on start page (Recommended).\n• Depth 3+: Deep multi-level exploration.")
        lbl_depth_tip.setStyleSheet("font-size: 11px; color: #94a3b8;")
        v_depth.addWidget(lbl_depth_tip)
        layout.addWidget(grp_depth)

        # File Filter Types
        grp_filters = QGroupBox("File Categories to Grab")
        v_filters = QVBoxLayout(grp_filters)

        h_chk1 = QHBoxLayout()
        self.chk_cat_images = QCheckBox("Pictures & Images (.jpg, .png, .gif, .webp, .svg)")
        self.chk_cat_images.setChecked(True)
        self.chk_cat_videos = QCheckBox("Videos & Streams (.mp4, .mkv, .webm, .avi, .ts)")
        self.chk_cat_videos.setChecked(True)
        h_chk1.addWidget(self.chk_cat_images)
        h_chk1.addWidget(self.chk_cat_videos)
        v_filters.addLayout(h_chk1)

        h_chk2 = QHBoxLayout()
        self.chk_cat_audio = QCheckBox("Audio & Music (.mp3, .wav, .flac, .m4a, .aac)")
        self.chk_cat_audio.setChecked(True)
        self.chk_cat_docs = QCheckBox("Documents (.pdf, .docx, .xlsx, .txt, .epub)")
        self.chk_cat_docs.setChecked(True)
        h_chk2.addWidget(self.chk_cat_audio)
        h_chk2.addWidget(self.chk_cat_docs)
        v_filters.addLayout(h_chk2)

        h_chk3 = QHBoxLayout()
        self.chk_cat_archives = QCheckBox("Compressed Archives (.zip, .rar, .7z, .tar, .iso)")
        self.chk_cat_archives.setChecked(True)
        self.chk_cat_programs = QCheckBox("Programs & Installers (.exe, .msi, .apk)")
        self.chk_cat_programs.setChecked(False)
        h_chk3.addWidget(self.chk_cat_archives)
        h_chk3.addWidget(self.chk_cat_programs)
        v_filters.addLayout(h_chk3)

        h_cust = QHBoxLayout()
        h_cust.addWidget(QLabel("Custom Extensions (comma-separated):"))
        self.txt_custom_ext = QLineEdit()
        self.txt_custom_ext.setPlaceholderText("torrent, dmg, bin")
        h_cust.addWidget(self.txt_custom_ext, 1)
        v_filters.addLayout(h_cust)

        layout.addWidget(grp_filters)
        layout.addStretch(1)
        return w

    def _create_step4_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        # Control Bar for Step 4
        h_ctrl = QHBoxLayout()
        self.btn_crawl_start = QPushButton("▶ Start Crawling")
        self.btn_crawl_start.setStyleSheet("background-color: #10b981; color: #020617; font-weight: 700; padding: 6px 16px; border-radius: 6px;")
        self.btn_crawl_start.clicked.connect(self._start_crawl)

        self.btn_crawl_stop = QPushButton("■ Stop")
        self.btn_crawl_stop.setEnabled(False)
        self.btn_crawl_stop.clicked.connect(self._stop_crawl)

        self.lbl_crawl_status = QLabel("Ready to start.")
        self.lbl_crawl_status.setStyleSheet("color: #94a3b8; font-weight: 500;")

        h_ctrl.addWidget(self.btn_crawl_start)
        h_ctrl.addWidget(self.btn_crawl_stop)
        h_ctrl.addSpacing(10)
        h_ctrl.addWidget(self.lbl_crawl_status, 1)

        # Quick selection filter buttons
        btn_sel_all = QPushButton("Select All")
        btn_sel_all.clicked.connect(lambda: self._set_all_checked(True))
        btn_unsel_all = QPushButton("Unselect All")
        btn_unsel_all.clicked.connect(lambda: self._set_all_checked(False))
        btn_sel_media = QPushButton("Media Only")
        btn_sel_media.clicked.connect(self._select_media_only)

        for b in [btn_sel_all, btn_unsel_all, btn_sel_media]:
            b.setFixedHeight(28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            h_ctrl.addWidget(b)

        layout.addLayout(h_ctrl)

        # Crawl progress
        self.crawl_prog = QProgressBar()
        self.crawl_prog.setFixedHeight(4)
        self.crawl_prog.setTextVisible(False)
        self.crawl_prog.setRange(0, 100)
        self.crawl_prog.setValue(0)
        layout.addWidget(self.crawl_prog)

        # Table for found items
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "File Name", "Size", "Category", "Address (URL)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 36)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 220)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 90)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 100)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        # Bottom Summary in Step 4
        h_sum = QHBoxLayout()
        self.lbl_selected_count = QLabel("0 files selected (0 B)")
        self.lbl_selected_count.setStyleSheet("font-weight: 600; color: #10b981;")
        h_sum.addWidget(self.lbl_selected_count)
        h_sum.addStretch(1)

        self.chk_start_now = QCheckBox("Start downloading immediately")
        self.chk_start_now.setChecked(True)
        h_sum.addWidget(self.chk_start_now)
        layout.addLayout(h_sum)

        return w

    def _browse_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Save Directory", self.txt_save_dir.text())
        if d:
            self.txt_save_dir.setText(d)

    def _go_next(self):
        curr = self.stack.currentIndex()
        if curr == 0:
            url = self.txt_url.text().strip()
            if not url or not (url.startswith("http://") or url.startswith("https://")):
                QMessageBox.warning(self, "Invalid URL", "Please enter a valid website address starting with http:// or https://")
                return
            self.stack.setCurrentIndex(1)
            self.lbl_step_title.setText("Step 2: Destination Folder and Routing")
            self.lbl_step_desc.setText("Choose where grabbed files will be organized and saved.")
            self.lbl_step_num.setText("Step 2 of 4")
            self.btn_back.setEnabled(True)
        elif curr == 1:
            save_d = self.txt_save_dir.text().strip()
            if not save_d:
                QMessageBox.warning(self, "Invalid Directory", "Please choose a valid destination folder.")
                return
            self.stack.setCurrentIndex(2)
            self.lbl_step_title.setText("Step 3: Exploration Depth and Category Filters")
            self.lbl_step_desc.setText("Select which file types to sniff and how deep to crawl.")
            self.lbl_step_num.setText("Step 3 of 4")
        elif curr == 2:
            self.stack.setCurrentIndex(3)
            self.lbl_step_title.setText("Step 4: Explore Web and Select Files to Download")
            self.lbl_step_desc.setText("Start crawling, preview found media, and inject files into your queue.")
            self.lbl_step_num.setText("Step 4 of 4")
            self.btn_next.setText("Download Selected")
            # Auto start crawling on entering step 4
            self._start_crawl()
        elif curr == 3:
            self._finish_and_export()

    def _go_back(self):
        curr = self.stack.currentIndex()
        if curr > 0:
            self.stack.setCurrentIndex(curr - 1)
            titles = [
                ("Step 1: Set Start Page and Project Name", "Specify the target website URL and domain boundary rules.", "Step 1 of 4"),
                ("Step 2: Destination Folder and Routing", "Choose where grabbed files will be organized and saved.", "Step 2 of 4"),
                ("Step 3: Exploration Depth and Category Filters", "Select which file types to sniff and how deep to crawl.", "Step 3 of 4"),
                ("Step 4: Explore Web and Select Files to Download", "Start crawling, preview found media, and inject files into your queue.", "Step 4 of 4"),
            ]
            t, d, n = titles[curr - 1]
            self.lbl_step_title.setText(t)
            self.lbl_step_desc.setText(d)
            self.lbl_step_num.setText(n)
            self.btn_next.setText("Next" if curr - 1 < 3 else "Download Selected")
            if curr - 1 == 0:
                self.btn_back.setEnabled(False)

    def _start_crawl(self):
        if self.crawler and self.crawler.is_alive():
            return

        categories = []
        if self.chk_cat_images.isChecked(): categories.append("Images")
        if self.chk_cat_videos.isChecked(): categories.append("Videos")
        if self.chk_cat_audio.isChecked(): categories.append("Audio")
        if self.chk_cat_docs.isChecked(): categories.append("Documents")
        if self.chk_cat_archives.isChecked(): categories.append("Compressed")
        if self.chk_cat_programs.isChecked(): categories.append("Programs")

        custom_raw = self.txt_custom_ext.text().strip()
        custom_exts = [x.strip() for x in custom_raw.split(",") if x.strip()] if custom_raw else []

        self.table.setRowCount(0)
        self.found_items.clear()
        self.btn_crawl_start.setEnabled(False)
        self.btn_crawl_stop.setEnabled(True)
        self.lbl_crawl_status.setText("Crawling website...")
        self.crawl_prog.setRange(0, 0) # Pulse/indeterminate

        self.crawler = SiteCrawler(
            start_url=self.txt_url.text().strip(),
            max_depth=self.spn_depth.value(),
            stay_on_domain=self.chk_stay_domain.isChecked(),
            allow_subdomains=self.chk_allow_subdomains.isChecked(),
            categories=categories,
            custom_extensions=custom_exts,
            max_pages=self.spn_max_pages.value(),
            on_item_found=lambda item: self.bridge.item_found.emit(item),
            on_progress=lambda scanned, total: self.bridge.progress_updated.emit(scanned, total),
            on_finished=lambda items: self.bridge.crawl_finished.emit(items)
        )
        self.crawler.start()

    def _stop_crawl(self):
        if self.crawler:
            self.crawler.stop()
            self.lbl_crawl_status.setText("Crawling stopped by user.")
            self.btn_crawl_start.setEnabled(True)
            self.btn_crawl_stop.setEnabled(False)
            self.crawl_prog.setRange(0, 100)
            self.crawl_prog.setValue(100)

    def _on_item_found(self, item: GrabbedItem):
        self.found_items.append(item)
        row = self.table.rowCount()
        self.table.insertRow(row)

        chk = QCheckBox()
        chk.setChecked(item.checked)
        chk.setStyleSheet("margin-left: 8px;")
        chk.toggled.connect(lambda checked, it=item: self._on_item_toggled(it, checked))
        self.table.setCellWidget(row, 0, chk)

        item_fn = QTableWidgetItem(item.filename)
        item_fn.setToolTip(item.filename)
        self.table.setItem(row, 1, item_fn)

        item_sz = QTableWidgetItem(item.filesize_formatted)
        self.table.setItem(row, 2, item_sz)

        item_cat = QTableWidgetItem(item.category)
        self.table.setItem(row, 3, item_cat)

        item_url = QTableWidgetItem(item.url)
        item_url.setToolTip(item.url)
        self.table.setItem(row, 4, item_url)

        self._update_selected_summary()

    def _on_progress_updated(self, scanned: int, total: int):
        self.lbl_crawl_status.setText(f"Crawling... Scanned {scanned} pages. Found {len(self.found_items)} items.")

    def _on_crawl_finished(self, items: list):
        self.lbl_crawl_status.setText(f"Crawling complete. Found {len(items)} files.")
        self.btn_crawl_start.setEnabled(True)
        self.btn_crawl_stop.setEnabled(False)
        self.crawl_prog.setRange(0, 100)
        self.crawl_prog.setValue(100)
        self._update_selected_summary()

    def _on_item_toggled(self, item: GrabbedItem, checked: bool):
        item.checked = checked
        self._update_selected_summary()

    def _set_all_checked(self, checked: bool):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if isinstance(w, QCheckBox):
                w.setChecked(checked)
        for it in self.found_items:
            it.checked = checked
        self._update_selected_summary()

    def _select_media_only(self):
        media_cats = {"Videos", "Audio", "Images"}
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if r < len(self.found_items):
                it = self.found_items[r]
                is_media = it.category in media_cats
                it.checked = is_media
                if isinstance(w, QCheckBox):
                    w.setChecked(is_media)
        self._update_selected_summary()

    def _update_selected_summary(self):
        selected = [it for it in self.found_items if it.checked]
        total_sz = sum(it.filesize for it in selected if it.filesize > 0)
        sz_str = format_bytes(total_sz) if total_sz > 0 else "unknown total size"
        self.lbl_selected_count.setText(f"{len(selected)} of {len(self.found_items)} files selected ({sz_str})")

    def _finish_and_export(self):
        selected = [it for it in self.found_items if it.checked]
        if not selected:
            QMessageBox.warning(self, "No Files Selected", "Please select at least one file to download.")
            return

        save_base = self.txt_save_dir.text().strip()
        if self.chk_create_proj_folder.isChecked():
            proj_name = self.txt_project.text().strip() or "Grabber_Project"
            from ..utils.helpers import sanitize_filename
            save_base = os.path.join(save_base, sanitize_filename(proj_name))
            os.makedirs(save_base, exist_ok=True)

        self.results = {
            "items": selected,
            "save_dir": save_base,
            "start_now": self.chk_start_now.isChecked(),
            "auto_subfolders": self.chk_subfolders.isChecked()
        }

        if self.crawler:
            self.crawler.stop()

        self.accept()

    def _on_cancel_clicked(self):
        if self.crawler:
            self.crawler.stop()
        self.reject()

    def closeEvent(self, event):
        if self.crawler:
            self.crawler.stop()
        super().closeEvent(event)

    def get_results(self) -> dict:
        return self.results