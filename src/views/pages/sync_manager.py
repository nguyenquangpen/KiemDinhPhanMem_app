import sys
import asyncio
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QComboBox,
    QTextEdit,
    QGroupBox,
    QMessageBox,
)
from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QFont
from asset import tokens
from models.database import DataManager
from services.logging_config import get_logger
from views.components import ui_kit

logger = get_logger("sync_manager")

class SyncWorker(QThread):
    finished = Signal(bool)

    def __init__(self, data_manager: DataManager, mode="push"):
        super().__init__()
        self.db = data_manager
        self.mode = mode

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            if self.mode == "push":
                success = loop.run_until_complete(self.db.push_local_changes())
            else:
                success = loop.run_until_complete(self.db.pull_remote_data())
                
            loop.close()
            self.finished.emit(success)
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            self.finished.emit(False)

class SyncUI(QDialog):
    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self.db = data_manager
        self.setWindowTitle("Local-first Sync Settings")
        self.resize(520, 420)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        self.sync_enabled = False
        self.auto_sync = False
        self.save_sync = False
        self.current_interval_index = 0

        self.debounce_timer = QTimer()
        self.debounce_timer.setInterval(5000)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._execute_sync_worker)

        self.periodic_timer = QTimer()
        self.periodic_timer.timeout.connect(self._execute_sync_worker)

        self._build_ui()
        self._update_sync_state()
        self._load_settings_from_db()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(ui_kit.label("Local-first sync", "CardTitle"))
        layout.addWidget(
            ui_kit.label("Your work is saved on this machine first and synced to the server in the background.", "MutedText", wrap=True)
        )

        # ---- 1. Global sync toggle & Top Status ----
        top_layout = QHBoxLayout()
        self.sync_toggle = QCheckBox("Enable sync")
        self.sync_toggle.toggled.connect(self._on_toggle_sync)
        top_layout.addWidget(self.sync_toggle)

        self.top_status_label = ui_kit.badge("Status: Unknown", "none")
        top_layout.addWidget(self.top_status_label)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        # ---- Sync settings ----
        self.sync_group = QGroupBox("Synchronization settings")
        sync_layout = QVBoxLayout(self.sync_group)

        # A. Auto sync
        self.auto_sync_checkbox = QCheckBox("Auto sync")
        self.auto_sync_checkbox.clicked.connect(self._on_click_auto_sync)
        sync_layout.addWidget(self.auto_sync_checkbox)

        time_layout = QHBoxLayout()

        self.interval_checkbox = QCheckBox("Sync periodically:")
        self.interval_checkbox.clicked.connect(self._on_click_interval_checkbox)
        time_layout.addWidget(self.interval_checkbox)

        self.time_sync_combo = QComboBox()
        self.time_sync_combo.addItem("Every 5 minutes", 5 * 60 * 1000)
        self.time_sync_combo.addItem("Every 15 minutes", 15 * 60 * 1000)
        self.time_sync_combo.addItem("Every 30 minutes", 30 * 60 * 1000)
        self.time_sync_combo.addItem("Every 1 hour", 60 * 60 * 1000)
        self.time_sync_combo.setEnabled(False)
        self.time_sync_combo.activated.connect(self._on_change_time_sync)
        time_layout.addWidget(self.time_sync_combo)
        sync_layout.addLayout(time_layout)

        button_layout = QHBoxLayout()
        self.pull_button = ui_kit.button("Force pull from cloud", "neutral", "download")
        self.pull_button.clicked.connect(self._on_force_pull)
        self.save_button = ui_kit.button("Save", "primary", "save")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._on_save_now)
        button_layout.addStretch(1)
        button_layout.addWidget(self.pull_button)
        button_layout.addWidget(self.save_button)
        sync_layout.addLayout(button_layout)

        layout.addWidget(self.sync_group)

        self.status_label = ui_kit.label("Idle", "MutedText")
        layout.addWidget(self.status_label)

        # ---- Status Log ----
        log_group = QGroupBox("Activity log")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(150)
        self.log_view.setFont(QFont(tokens.FONT_MONO, 9))
        log_layout.addWidget(self.log_view)
        layout.addWidget(log_group)
    
    def _load_settings_from_db(self):
        """load sync settings from DB and update UI accordingly"""
        try:
            loop = asyncio.new_event_loop()
            config = loop.run_until_complete(self.db.get_sync_config())
            loop.close()

            if config:
                self.sync_toggle.blockSignals(True)
                self.sync_toggle.setChecked(config.get("enabled", False))
                self.sync_enabled = self.sync_toggle.isChecked()
                self.auto_sync_checkbox.setChecked(config.get("auto_sync", False))
                self.interval_checkbox.setChecked(config.get("interval_sync", False))
                self.sync_toggle.blockSignals(False)

                index = self.time_sync_combo.findData(config.get("interval_ms", 0))
                if index >= 0:
                    self.time_sync_combo.setCurrentIndex(index)
                
                if self.sync_toggle.isChecked():
                    self._update_sync_state()
                    self._execute_sync_worker()
        except Exception as e:
            logger.error(f"Failed to load sync settings: {e}")

    def _add_log(self, message, level="INFO"):
        """Hàm ghi log có màu sắc và thời gian"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = tokens.TEXT
        if level == "SUCCESS": color = tokens.PRIMARY_TEXT
        elif level == "ERROR": color = tokens.DANGER_TEXT
        elif level == "PROCESS": color = tokens.SECONDARY_TEXT
        log_entry = f"<span style='color: {tokens.TEXT_MUTED};'>[{timestamp}]</span> <b style='color: {color};'>[{level}]</b> {message}"
        self.log_view.append(log_entry)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def _show_confirmation(self, text):
        reply = QMessageBox.question(
            self,
            "Confirm Change",
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _mark_unsaved_changes(self):
        """Enable the save button when there are unsaved changes in the settings"""
        if self.sync_enabled:
            self.save_button.setEnabled(True)
            # self.pull_button.setEnabled(False)

    def _on_click_auto_sync(self):
        """Handle when click Auto sync checkbox"""
        if self.auto_sync_checkbox.isCheckable():
            self.interval_checkbox.setChecked(False)
            self.time_sync_combo.setEnabled(False)
        self._mark_unsaved_changes()

    def _on_click_interval_checkbox(self):
        """handle when click interval time checkbox"""
        is_checked = self.interval_checkbox.isChecked()
        self.time_sync_combo.setEnabled(is_checked)
        if is_checked:
            self.auto_sync_checkbox.blockSignals(True)
            self.auto_sync_checkbox.setChecked(False)
            self.auto_sync_checkbox.blockSignals(False)
        self._mark_unsaved_changes()

    def _on_change_time_sync(self, index):
        self.current_interval_index = index
        self._mark_unsaved_changes()

    def _on_toggle_sync(self, state):
        """Turn on sync switch"""
        self.sync_enabled = state
        self._update_sync_state()
        if not self.sync_enabled:
            self.auto_sync_checkbox.setChecked(False)
            self.interval_checkbox.setChecked(False)
            self.time_sync_combo.setEnabled(False)
            self.save_button.setEnabled(False)
            self._cleanup_connections()
            self.log_view.append("Background sync disabled.")
        else:
            self._mark_unsaved_changes()

    def _update_sync_state(self):
        self.sync_group.setEnabled(self.sync_enabled)

    def _cleanup_connections(self):
        """Stop the timer and cut the signal from the DB"""
        self.debounce_timer.stop()
        self.periodic_timer.stop()
        try:
            self.db.signals.sync_needed.disconnect(
                self._on_db_change_detected
            )
        except Exception:
            pass

    def _on_worker_finished(self, success):
        result_text = "success" if success else "failed"
        self.status_label.setText(f"Sync activate {result_text}")
        if success:
            ui_kit.set_badge(self.top_status_label, "Status: Synced", "ok")
        else:
            ui_kit.set_badge(self.top_status_label, "Status: Pending/Error", "ng")

    def _on_db_change_detected(self):
        """calling when DB generate signal sync"""
        ui_kit.set_badge(self.top_status_label, "Status: Change detected, waiting 5s...", "run")
        self.debounce_timer.start()

    def _execute_sync_worker(self):
        self._add_log("Starting synchronization...", "PROCESS")
        self.status_label.setText("Syncing...")
        ui_kit.set_badge(self.top_status_label, "Status: Syncing...", "info")
        self.worker = SyncWorker(self.db)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_save_now(self):
        if not self.sync_enabled:
            return
        self._cleanup_connections()
        self.save_button.setEnabled(False)

        config_data = {
            "enabled": self.sync_enabled,
            "auto_sync": self.auto_sync_checkbox.isChecked(),
            "interval_sync": self.interval_checkbox.isChecked(),
            "interval_ms": self.time_sync_combo.currentData(),
        }
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.db.save_sync_config(config_data))
            loop.close()
        except Exception as e:
            logger.error(f"Failed to save sync settings: {e}")
            self.save_button.setEnabled(True)
            return

        if self.auto_sync_checkbox.isChecked():
            self.status_label.setText("Mode: Auto Sync (Active)")
            self.db.signals.sync_needed.connect(self._on_db_change_detected)
        elif self.interval_checkbox.isChecked():
            ms = self.time_sync_combo.currentData()
            interval_text = self.time_sync_combo.currentText()
            self.status_label.setText(f"Mode: Periodic ({interval_text})")
            self.periodic_timer.start(ms)
            self.log_view.append(f"Enabled: Periodic sync {interval_text}.")
        self._execute_sync_worker()
    
    def _on_force_pull(self):
        self._add_log("Starting Force Pull from Cloud...", "PROCESS")
        self.worker = SyncWorker(self.db, mode="pull")
        self.worker.finished.connect(lambda s: self._on_sync_finished(s, "Pull"))
        self.worker.start()
    
    def _on_sync_finished(self, success, mode="push"):
        if success:
            self._add_log(f"{mode} operation completed successfully.", "SUCCESS")
            ui_kit.set_badge(self.top_status_label, f"Status: {mode} Done", "ok")
        else:
            self._add_log(f"{mode} operation failed. Please check your connection.", "ERROR")
            ui_kit.set_badge(self.top_status_label, f"Status: {mode} Error", "ng")