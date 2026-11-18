from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QTimeEdit, QCheckBox, QComboBox, QGroupBox, QMessageBox
)
from PyQt6.QtCore import QTime, Qt
from ..core.database import Database
from ..core.scheduler import DownloadScheduler
from ..utils.helpers import apply_windows_dark_titlebar

class SchedulerDialog(QDialog):
    def __init__(self, db: Database, scheduler: DownloadScheduler, parent=None):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.setWindowTitle("Scheduler")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(520, 480)
        apply_windows_dark_titlebar(self)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # 1. Queue Sequencing
        grp_queue = QGroupBox("Queue Management")
        q_layout = QHBoxLayout(grp_queue)
        q_layout.addWidget(QLabel("Max simultaneous active downloads:"))
        self.spn_concurrent = QSpinBox()
        self.spn_concurrent.setRange(1, 10)
        self.spn_concurrent.setValue(2)
        q_layout.addWidget(self.spn_concurrent)
        q_layout.addStretch()
        layout.addWidget(grp_queue)

        # 2. Time-Based Download Schedule
        grp_sched = QGroupBox("Download Time Window")
        s_layout = QVBoxLayout(grp_sched)

        self.chk_sched_enable = QCheckBox("Enable automated time window")
        s_layout.addWidget(self.chk_sched_enable)

        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Start Time:"))
        self.time_start = QTimeEdit(QTime(1, 0))
        time_layout.addWidget(self.time_start)

        time_layout.addWidget(QLabel("Stop Time:"))
        self.time_stop = QTimeEdit(QTime(6, 0))
        time_layout.addWidget(self.time_stop)
        time_layout.addStretch()
        s_layout.addLayout(time_layout)
        layout.addWidget(grp_sched)

        # 3. Bandwidth Time-Scheduler
        grp_bandwidth = QGroupBox("Bandwidth Schedule (Off-Peak Speed Profile)")
        b_layout = QVBoxLayout(grp_bandwidth)
        
        self.chk_bw_enable = QCheckBox("Throttle speed during work/day hours")
        b_layout.addWidget(self.chk_bw_enable)

        bw_sub_layout = QHBoxLayout()
        bw_sub_layout.addWidget(QLabel("Speed Limit during window (KB/s):"))
        self.spn_bw_limit = QSpinBox()
        self.spn_bw_limit.setRange(50, 100000)
        self.spn_bw_limit.setValue(500)
        bw_sub_layout.addWidget(self.spn_bw_limit)
        bw_sub_layout.addStretch()
        b_layout.addLayout(bw_sub_layout)
        layout.addWidget(grp_bandwidth)

        # 4. Post-Download Actions
        grp_post = QGroupBox("On All Downloads Complete")
        p_layout = QHBoxLayout(grp_post)
        p_layout.addWidget(QLabel("Action:"))
        self.cmb_action = QComboBox()
        self.cmb_action.addItems([
            "Do Nothing",
            "Shutdown Computer",
            "Sleep (Standby)",
            "Hibernate Computer",
            "Exit Application"
        ])
        p_layout.addWidget(self.cmb_action)

        btn_abort_power = QPushButton("Abort Shutdown")
        btn_abort_power.setCursor(Qt.CursorShape.PointingHandCursor)
        def _abort_action():
            from ..core.post_actions import PostActionManager
            PostActionManager.abort_shutdown()
            QMessageBox.information(self, "Shutdown Aborted", "Canceled any pending scheduled Windows shutdown.")
        btn_abort_power.clicked.connect(_abort_action)
        p_layout.addWidget(btn_abort_power)

        p_layout.addStretch()
        layout.addWidget(grp_post)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Save & Apply")
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #05070b;
                font-weight: 600;
                padding: 7px 18px;
                border: 1px solid #10b981;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #34d399;
                border-color: #34d399;
                color: #020617;
            }
        """)
        btn_save.clicked.connect(self._save_settings)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _load_settings(self):
        max_c = int(self.db.get_setting("max_concurrent_downloads", "2"))
        self.spn_concurrent.setValue(max_c)

        schedules = self.db.get_schedules()
        if schedules:
            s = schedules[0]
            self.chk_sched_enable.setChecked(s.get("enabled", False))
            if s.get("start_time"):
                self.time_start.setTime(QTime.fromString(s["start_time"], "HH:mm"))
            if s.get("stop_time"):
                self.time_stop.setTime(QTime.fromString(s["stop_time"], "HH:mm"))
            if s.get("speed_limit_kbps", 0) > 0:
                self.chk_bw_enable.setChecked(True)
                self.spn_bw_limit.setValue(s["speed_limit_kbps"])

        # Auto shutdown status
        action = self.db.get_setting("auto_complete_action", "Do Nothing")
        idx = self.cmb_action.findText(action)
        if idx >= 0:
            self.cmb_action.setCurrentIndex(idx)

    def _save_settings(self):
        max_c = self.spn_concurrent.value()
        self.scheduler.set_max_concurrent(max_c)

        action_text = self.cmb_action.currentText()
        self.db.set_setting("auto_complete_action", action_text)
        
        action_map = {
            "Do Nothing": "none",
            "Shutdown Computer": "shutdown",
            "Sleep (Standby)": "sleep",
            "Hibernate Computer": "hibernate",
            "Exit Application": "exit"
        }
        self.scheduler.auto_shutdown_action = action_map.get(action_text, "none")
        self.scheduler.auto_shutdown_enabled = (self.scheduler.auto_shutdown_action != "none")

        # Save schedule
        sched_enabled = self.chk_sched_enable.isChecked() or self.chk_bw_enable.isChecked()
        start_str = self.time_start.time().toString("HH:mm")
        stop_str = self.time_stop.time().toString("HH:mm")
        speed_lim = self.spn_bw_limit.value() if self.chk_bw_enable.isChecked() else 0

        self.db.save_schedule("default_sched", "Default Schedule", sched_enabled, start_str, stop_str, speed_lim, self.scheduler.auto_shutdown_action)

        QMessageBox.information(self, "Saved", "Scheduler settings applied successfully.")
        self.accept()