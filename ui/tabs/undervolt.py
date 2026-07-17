from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLabel, QSlider, QPushButton, QCheckBox, QGridLayout)
from PySide6.QtCore import Qt, QTimer
from ui.style import T
from ui.widgets import status_label, set_status
from core.undervolt import set_undervolt, read_undervolt

class UndervoltTab(QWidget):
    def __init__(self, config, save_cb, parent=None):
        super().__init__(parent)
        self.config = config
        self.save_cb = save_cb
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Info header (compact)
        info = QLabel('⚡ Undervolting reduces heat/power. Start at -50mV. Stress test after apply.')
        info.setWordWrap(True)
        info.setStyleSheet(f'color:{T["muted2"]};font-size:10px;border:1px solid {T["border"]};'
                           f'border-radius:6px;padding:6px;background:{T["surface2"]};')
        main_layout.addWidget(info)

        # Current readings group
        curr_group = QGroupBox('CURRENT READINGS')
        curr_layout = QHBoxLayout(curr_group)
        curr_layout.setContentsMargins(10, 15, 10, 10)
        self.current_labels = {}
        for name in ('Core', 'Cache', 'GPU', 'Uncore', 'AnalogIO'):
            sub = QVBoxLayout()
            t = QLabel(name.upper())
            t.setStyleSheet(f'color:{T["muted2"]};font-size:8px;letter-spacing:1px;')
            v = QLabel('—')
            v.setStyleSheet(f'color:{T["accent"]};font-size:13px;font-weight:bold;')
            sub.addWidget(t)
            sub.addWidget(v)
            curr_layout.addLayout(sub)
            self.current_labels[name.lower()] = v
        curr_layout.addStretch()
        main_layout.addWidget(curr_group)

        # Sliders group
        sliders_group = QGroupBox('SET UNDERVOLT (mV)')
        sg_layout = QGridLayout(sliders_group)
        sg_layout.setSpacing(6)
        sg_layout.setContentsMargins(10, 15, 10, 10)
        
        self.sliders = {}
        self.slider_labels = {}
        
        planes = [
            ('core',     'CPU Core',   T['accent2']),
            ('cache',    'CPU Cache',  T['accent']),
            ('gpu',      'Intel GPU',  T['green']),
            ('uncore',   'System Agent',T['warn']),
            ('analogio', 'Analog I/O', T['muted2']),
        ]
        
        for i, (key, label, color) in enumerate(planes):
            val = config.get('undervolt', {}).get(key, 0.0)
            
            lbl = QLabel(label)
            lbl.setMinimumWidth(80)
            lbl.setStyleSheet("font-size:11px;")
            
            slider = QSlider(Qt.Horizontal)
            slider.setRange(-250, 0)
            slider.setValue(int(val))
            slider.setStyleSheet(f'QSlider::sub-page:horizontal{{background:{color};border-radius:2px;}}')
            
            val_lbl = QLabel(f'{int(val)} mV')
            val_lbl.setStyleSheet(f'color:{color};font-weight:bold;min-width:50px;font-size:11px;')
            val_lbl.setAlignment(Qt.AlignRight)
            
            # Use dedicated slider changed slot to support link lockstep
            def make_slot(k):
                return lambda v: self._on_slider_changed(k, v)
            slider.valueChanged.connect(make_slot(key))
            
            sg_layout.addWidget(lbl, i, 0)
            sg_layout.addWidget(slider, i, 1)
            sg_layout.addWidget(val_lbl, i, 2)
            
            self.sliders[key] = slider
            self.slider_labels[key] = val_lbl
            
        main_layout.addWidget(sliders_group)

        # Controls
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        btn_read = QPushButton('↺ READ')
        btn_apply = QPushButton('⚡ APPLY')
        btn_apply.setObjectName('primary')
        btn_reset = QPushButton('RESET')
        
        self.boot_check = QCheckBox('Apply on App Start')
        self.boot_check.setChecked(config.get('undervolt', {}).get('apply_on_boot', False))
        self.boot_check.setToolTip('Automatically apply saved undervolt settings when the mousectl app is launched, rather than at system boot. This protects your system from boot loops if settings are unstable.')
        
        self.boot_check_link = QCheckBox('Link Core/Cache')
        self.boot_check_link.setChecked(True)
        self.boot_check_link.setToolTip('Synchronize Core and Cache undervolts (strongly recommended by Intel)')
        self.boot_check_link.toggled.connect(self._on_link_toggled)
        
        btn_read.clicked.connect(self._read_current)
        btn_apply.clicked.connect(self._apply)
        btn_reset.clicked.connect(self._reset)
        self.boot_check.toggled.connect(self._save_prefs)
        
        ctrl.addWidget(btn_read)
        ctrl.addWidget(btn_apply)
        ctrl.addWidget(btn_reset)
        ctrl.addWidget(self.boot_check)
        ctrl.addWidget(self.boot_check_link)
        ctrl.addStretch()
        main_layout.addLayout(ctrl)


        self.status = status_label()
        main_layout.addWidget(self.status)
        main_layout.addStretch()

        # Initial read
        QTimer.singleShot(500, self._read_current)

    def refresh_widgets(self):
        uv_cfg = self.config.get('undervolt', {})
        for plane, slider in self.sliders.items():
            val = uv_cfg.get(plane, 0.0)
            slider.blockSignals(True)
            slider.setValue(int(val))
            slider.blockSignals(False)
            self.slider_labels[plane].setText(f"{int(val)} mV")

        self.boot_check.blockSignals(True)
        self.boot_check.setChecked(uv_cfg.get('apply_on_boot', False))
        self.boot_check.blockSignals(False)

    def _read_current(self):
        try:
            vals = read_undervolt()
            for key, lbl in self.current_labels.items():
                v = vals.get(key, 0.0)
                lbl.setText(f'{v:.1f} mV')
            set_status(self.status, "Read MSR offsets", "info")
        except Exception as e:
            set_status(self.status, f"Read failed: {str(e)}", "err")

    def _apply(self):
        try:
            uv_cfg = self.config.setdefault('undervolt', {})
            for plane, slider in self.sliders.items():
                val = float(slider.value())
                set_undervolt(plane, val)
                uv_cfg[plane] = val
            
            uv_cfg['apply_on_boot'] = self.boot_check.isChecked()
            self.save_cb()
            set_status(self.status, "Applied successfully", "ok")
            QTimer.singleShot(500, self._read_current)
        except Exception as e:
            set_status(self.status, f"Apply failed: {str(e)}", "err")

    def _reset(self):
        for s in self.sliders.values():
            s.setValue(0)

    def _save_prefs(self):
        self.config.setdefault('undervolt', {})['apply_on_boot'] = self.boot_check.isChecked()
        self.save_cb()

    def _on_slider_changed(self, key, val):
        self.slider_labels[key].setText(f'{val} mV')
        if hasattr(self, 'boot_check_link') and self.boot_check_link.isChecked():
            if key == 'core' and self.sliders['cache'].value() != val:
                self.sliders['cache'].blockSignals(True)
                self.sliders['cache'].setValue(val)
                self.slider_labels['cache'].setText(f'{val} mV')
                self.sliders['cache'].blockSignals(False)
            elif key == 'cache' and self.sliders['core'].value() != val:
                self.sliders['core'].blockSignals(True)
                self.sliders['core'].setValue(val)
                self.slider_labels['core'].setText(f'{val} mV')
                self.sliders['core'].blockSignals(False)

    def _on_link_toggled(self, checked):
        if checked:
            val = self.sliders['core'].value()
            if self.sliders['cache'].value() != val:
                self.sliders['cache'].blockSignals(True)
                self.sliders['cache'].setValue(val)
                self.slider_labels['cache'].setText(f'{val} mV')
                self.sliders['cache'].blockSignals(False)

