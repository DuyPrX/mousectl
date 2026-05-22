from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QCheckBox, QLabel, QSpinBox)
from PySide6.QtCore import Qt
from ui.style import T
from ui.widgets import StatCard, FanCurveWidget, status_label, set_status
from core.fan import fan_daemon
import core.sysfs as sysfs

class FanTab(QWidget):
    def __init__(self, config, save_cb, parent=None):
        super().__init__(parent)
        self.config     = config
        self.save_cb    = save_cb
        self._fixed_duty: int | None = config.get('fan_lock_duty')  # fixed duty %, None = not locked
        self._curve_active: bool = config.get('fan_curve_active', False)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Live stats row
        stats = QHBoxLayout()
        stats.setSpacing(8)
        self.card_rpm  = StatCard('Fan Speed',  'RPM', T['accent'])
        self.card_duty = StatCard('PWM Duty',   '%',   T['accent2'])
        self.card_temp = StatCard('CPU Temp',   '°C',  T['warn'])
        self.card_daemon = StatCard('Daemon',   '',    T['green'])
        
        for c in [self.card_rpm, self.card_duty, self.card_temp, self.card_daemon]:
            c.setMaximumHeight(80)
            stats.addWidget(c)
        main_layout.addLayout(stats)

        # Curve editor box
        box = QGroupBox("INTERACTIVE FAN CURVE")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(10, 15, 10, 10)
        
        self.curve_editor = FanCurveWidget()
        pts = config.get('fan_curve', [(30,30),(45,40),(60,55),(70,70),(80,85),(90,100)])
        self.curve_editor.set_points(pts)
        # curve_changed fires on every drag pixel — only update preview, not daemon/disk
        self.curve_editor.curve_changed.connect(self._on_curve_preview)
        # curve_committed fires on mouse release — update daemon and save
        self.curve_editor.curve_committed.connect(self._on_curve_committed)
        box_layout.addWidget(self.curve_editor)
        
        # Preset buttons
        presets_layout = QHBoxLayout()
        presets_layout.setSpacing(6)
        for name, preset in [('🌙 Silent', 'silent'), ('⚖ Balanced', 'balanced'), ('🔥 Performance', 'performance')]:
            b = QPushButton(name)
            b.setStyleSheet("font-size:10px; padding:4px 8px;")
            b.clicked.connect(lambda _, pr=preset: self.curve_editor.set_preset(pr))
            presets_layout.addWidget(b)
        presets_layout.addStretch()
        box_layout.addLayout(presets_layout)
        
        main_layout.addWidget(box)

        # Controls
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        
        self.btn_apply = QPushButton('▶  ACTIVATE')
        self.btn_apply.setObjectName('primary')
        self.btn_apply.setMinimumWidth(110)

        self.btn_stop = QPushButton('■  AUTO')
        self.btn_stop.setObjectName('danger')

        # Fixed duty controls
        self.spin_duty = QSpinBox()
        self.spin_duty.setRange(20, 100)
        self.spin_duty.setValue(self._fixed_duty if self._fixed_duty is not None else 80)
        self.spin_duty.setSuffix(' %')
        self.spin_duty.setAlignment(Qt.AlignCenter)
        self.spin_duty.setMinimumWidth(72)
        self.spin_duty.setToolTip('Fixed fan duty cycle to lock at')
        self.spin_duty.setStyleSheet(
            f"QSpinBox {{ background:{T['surface2']}; border:1px solid {T['border']}; "
            f"border-radius:6px; color:{T['warn']}; min-height:30px; "
            f"font-size:13px; font-weight:bold; padding:0 4px; }}"
        )

        self.btn_lock = QPushButton('📌  Lock')
        self.btn_lock.setToolTip('Hold fan at the chosen duty % (persists until auto or curve activation)')

        self.active_check = QCheckBox('Boot')
        self.active_check.setChecked(self._curve_active)
        self.active_check.toggled.connect(self._on_boot_toggled)

        self.btn_apply.clicked.connect(self._activate)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_lock.clicked.connect(self._lock_fan)

        ctrl.addWidget(self.btn_apply)
        ctrl.addWidget(self.btn_stop)
        ctrl.addWidget(self.spin_duty)
        ctrl.addWidget(self.btn_lock)
        ctrl.addWidget(self.active_check)
        ctrl.addStretch()
        main_layout.addLayout(ctrl)

        self.status = status_label()
        main_layout.addWidget(self.status)
        main_layout.addStretch()

        self._update_daemon_card()
        
        # Start local thread on startup if active in config and background service is NOT running
        from core.sysfs import is_fan_service_active
        if self._curve_active and self._fixed_duty is None:
            if is_fan_service_active():
                set_status(self.status, 'Curve active via background service', 'ok')
            else:
                if not fan_daemon.isRunning():
                    fan_daemon.curve = pts
                    fan_daemon.start()
                set_status(self.status, 'Curve active via local UI thread', 'ok')
        elif self._fixed_duty is not None:
            set_status(self.status, f'📌 Fan locked at {self._fixed_duty}% — click AUTO to restore', 'warn')

        self._update_button_states()

    def update_telemetry(self, data: dict, temp: float, fan: int = 0):
        self.card_rpm.set_value(fan)
        self.card_temp.set_value(temp, 1)
        col = T['green'] if temp < 55 else T['warn'] if temp < 75 else T['danger']
        self.card_temp.set_color(col)

        # Real hardware fan duty from telemetry
        real_duty = data.get('fan_duty', 0)
        service_active = data.get('fan_service_active', False)

        if self._fixed_duty is not None:
            self.card_duty.set_value(real_duty)
            self.card_duty.set_color(T['warn'])
        elif service_active or fan_daemon.isRunning():
            self.card_duty.set_value(real_duty)
            self.card_duty.set_color(T['accent2'])
        else:
            self.card_duty.set_value('AUTO')
            self.card_duty.set_color(T['muted2'])

        # Update daemon card automatically in real-time using background data
        if self._fixed_duty is not None:
            self.card_daemon.set_value(f'{self._fixed_duty}%')
            self.card_daemon.set_color(T['warn'])
        elif service_active:
            self.card_daemon.set_value('SERVICE')
            self.card_daemon.set_color(T['green'])
        elif fan_daemon.isRunning():
            self.card_daemon.set_value('ACTIVE (UI)')
            self.card_daemon.set_color(T['green'])
        else:
            self.card_daemon.set_value('OFF')
            self.card_daemon.set_color(T['muted2'])

    def _update_daemon_card(self):
        from core.sysfs import is_fan_service_active
        if self._fixed_duty is not None:
            self.card_daemon.set_value(f'{self._fixed_duty}%')
            self.card_daemon.set_color(T['warn'])
        elif is_fan_service_active():
            self.card_daemon.set_value('SERVICE')
            self.card_daemon.set_color(T['green'])
        elif fan_daemon.isRunning():
            self.card_daemon.set_value('ACTIVE (UI)')
            self.card_daemon.set_color(T['green'])
        else:
            self.card_daemon.set_value('OFF')
            self.card_daemon.set_color(T['muted2'])

    def _on_curve_preview(self, pts):
        """Fires on every drag pixel — only update config dict, no disk write or daemon update."""
        self.config['fan_curve'] = pts

    def _on_curve_committed(self, pts):
        """Fires on mouse release — safe to update daemon and save."""
        self.config['fan_curve'] = pts
        from core.sysfs import is_fan_service_active
        if fan_daemon.isRunning():
            fan_daemon.curve = pts
            set_status(self.status, 'Curve updated live', 'ok')
        elif is_fan_service_active():
            set_status(self.status, 'Curve updated (syncing with background service...)', 'ok')
        self.save_cb()

    def _update_button_states(self):
        # 1. Custom Curve (btn_apply)
        if self._curve_active and self._fixed_duty is None:
            self.btn_apply.setStyleSheet(
                f"QPushButton {{ background: {T['accent']}; color: {T['bg']}; border: 1px solid {T['accent']}; "
                f"font-weight: bold; font-size: 11px; padding: 7px 16px; border-radius: 6px; }}"
            )
        else:
            self.btn_apply.setStyleSheet(
                f"QPushButton {{ background: {T['surface2']}; color: {T['muted2']}; border: 1px solid {T['border']}; "
                f"font-weight: bold; font-size: 11px; padding: 7px 16px; border-radius: 6px; }}"
                f"QPushButton:hover {{ background: {T['border']}; color: {T['text']}; border-color: {T['accent']}; }}"
            )

        # 2. Auto EC Control (btn_stop)
        if not self._curve_active and self._fixed_duty is None:
            self.btn_stop.setStyleSheet(
                f"QPushButton {{ background: {T['danger']}; color: {T['bg']}; border: 1px solid {T['danger']}; "
                f"font-weight: bold; font-size: 11px; padding: 7px 16px; border-radius: 6px; }}"
            )
        else:
            self.btn_stop.setStyleSheet(
                f"QPushButton {{ background: {T['surface2']}; color: {T['muted2']}; border: 1px solid {T['border']}; "
                f"font-weight: bold; font-size: 11px; padding: 7px 16px; border-radius: 6px; }}"
                f"QPushButton:hover {{ background: {T['border']}; color: {T['text']}; border-color: {T['danger']}; }}"
            )

        # 3. Fixed Speed Lock (btn_lock)
        if self._fixed_duty is not None:
            self.btn_lock.setStyleSheet(
                f"QPushButton {{ background: {T['warn']}; color: {T['bg']}; border: 1px solid {T['warn']}; "
                f"font-weight: bold; font-size: 11px; padding: 7px 16px; border-radius: 6px; }}"
            )
        else:
            self.btn_lock.setStyleSheet(
                f"QPushButton {{ background: {T['surface2']}; color: {T['muted2']}; border: 1px solid {T['border']}; "
                f"font-weight: bold; font-size: 11px; padding: 7px 16px; border-radius: 6px; }}"
                f"QPushButton:hover {{ background: {T['border']}; color: {T['text']}; border-color: {T['warn']}; }}"
            )

    def _set_active_check_silent(self, checked: bool):
        self.active_check.blockSignals(True)
        self.active_check.setChecked(checked)
        self.active_check.blockSignals(False)

    def _on_boot_toggled(self, checked: bool):
        if checked:
            self._activate()
        else:
            self._stop()

    def _activate(self):
        self._fixed_duty = None
        self._curve_active = True
        pts = self.curve_editor.points
        fan_daemon.curve = pts
        
        from core.sysfs import is_fan_service_active
        if is_fan_service_active():
            # If the background service is running, stop any legacy UI thread to prevent conflict
            if fan_daemon.isRunning():
                fan_daemon.stop()
            set_status(self.status, 'Curve active via background service', 'ok')
        else:
            # Fallback to local UI thread
            if not fan_daemon.isRunning():
                fan_daemon.start()
            set_status(self.status, 'Curve active via local UI thread', 'ok')
            
        self._set_active_check_silent(True)
        self._update_button_states()
        self._update_daemon_card()
        self._save_prefs()

    def _stop(self):
        self._fixed_duty = None
        self._curve_active = False
        fan_daemon.stop()
        self._set_active_check_silent(False)
        self._update_button_states()
        self._update_daemon_card()
        set_status(self.status, 'Auto-mode (BIOS)', 'warn')
        self._save_prefs()


    def _lock_fan(self):
        """Lock fan at the chosen fixed duty %. Stops daemon so it can't override."""
        pct = self.spin_duty.value()
        self._curve_active = False
        if fan_daemon.isRunning():
            fan_daemon.stop()
        ok = sysfs.set_fan_speed(pct)
        self._fixed_duty = pct if ok else None
        self._set_active_check_silent(False)
        self._update_button_states()
        self._update_daemon_card()
        if ok:
            set_status(self.status, f'📌 Fan locked at {pct}% — click AUTO to restore', 'warn')
        else:
            set_status(self.status, 'Lock failed — check hwmon access', 'err')
        self._save_prefs()

    def _save_prefs(self):
        self.config['fan_curve_active'] = self._curve_active
        self.config['fan_curve'] = self.curve_editor.points
        self.config['fan_lock_duty'] = self._fixed_duty
        self.save_cb()
