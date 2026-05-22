from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLabel, QSlider, QComboBox, QPushButton, QCheckBox, QGridLayout, QSpinBox, QMessageBox)
from PySide6.QtCore import Qt
from ui.style import T
from ui.widgets import status_label, set_status
import core.sysfs as sysfs
import core.msr as msr
from core.config import reset_config

class PowerTab(QWidget):
    def __init__(self, config, save_cb, profile_cb=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.save_cb = save_cb
        self.profile_cb = profile_cb
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        content = QHBoxLayout()
        content.setSpacing(10)
        main_layout.addLayout(content)
        
        left_vbox = QVBoxLayout()
        right_vbox = QVBoxLayout()
        content.addLayout(left_vbox, 3)
        content.addLayout(right_vbox, 2)

        # ── Power Profile ──
        profile_group = QGroupBox('SYSTEM76 POWER PROFILE')
        pl = QHBoxLayout(profile_group)
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(['battery', 'balanced', 'performance'])
        self.profile_combo.setCurrentText(config.get('power', {}).get('profile', 'balanced'))
        
        self.profile_active_lbl = QLabel('Current: …')
        self.profile_active_lbl.setStyleSheet(f'color:{T["accent"]};font-weight:bold;')
        
        btn_set_profile = QPushButton('Apply Profile')
        btn_set_profile.setObjectName('primary')
        btn_set_profile.clicked.connect(self._apply_profile)
        
        pl.addWidget(QLabel('Profile:'))
        pl.addWidget(self.profile_combo)
        pl.addWidget(btn_set_profile)
        pl.addWidget(self.profile_active_lbl)
        pl.addStretch()
        left_vbox.addWidget(profile_group)

        # ── TDP Limits ──
        tdp_group = QGroupBox('CPU TDP LIMITS (INTEL RAPL)')
        tl = QGridLayout(tdp_group)
        tl.setSpacing(8)

        power_cfg = config.get('power', {})
        
        tl.addWidget(QLabel('Long-term (sustained):'), 0, 0)
        self.long_slider = QSlider(Qt.Horizontal)
        self.long_slider.setRange(5, 45)
        self.long_slider.setValue(power_cfg.get('long', 15))
        self.long_lbl = QLabel(f'{self.long_slider.value()} W')
        self.long_lbl.setStyleSheet(f'color:{T["accent"]};font-weight:bold;min-width:55px;')
        self.long_slider.valueChanged.connect(lambda v: self.long_lbl.setText(f'{v} W'))
        tl.addWidget(self.long_slider, 0, 1)
        tl.addWidget(self.long_lbl, 0, 2)

        tl.addWidget(QLabel('Short-term (burst):'), 1, 0)
        self.short_slider = QSlider(Qt.Horizontal)
        self.short_slider.setRange(15, 64)
        self.short_slider.setValue(power_cfg.get('short', 25))
        self.short_lbl = QLabel(f'{self.short_slider.value()} W')
        self.short_lbl.setStyleSheet(f'color:{T["accent2"]};font-weight:bold;min-width:55px;')
        self.short_slider.valueChanged.connect(lambda v: self.short_lbl.setText(f'{v} W'))
        tl.addWidget(self.short_slider, 1, 1)
        tl.addWidget(self.short_lbl, 1, 2)

        # Presets
        pre_layout = QHBoxLayout()
        for name, pl_l, pl_s in [('Cool',12,20),('Bal',15,25),('Perf',25,45),('Max',35,64)]:
            b = QPushButton(name)
            b.clicked.connect(lambda _, l=pl_l, s=pl_s: (self.long_slider.setValue(l),
                                                          self.short_slider.setValue(s)))
            pre_layout.addWidget(b)
        tl.addLayout(pre_layout, 2, 0, 1, 3)

        btn_tdp = QPushButton('⚡ Apply TDP Limits')
        btn_tdp.setObjectName('primary')
        btn_tdp.clicked.connect(self._apply_tdp)
        tl.addWidget(btn_tdp, 3, 0, 1, 3)

        # Live hardware readout
        self.lbl_hw_tdp = QLabel('Hardware: PL1 — W  |  PL2 — W')
        self.lbl_hw_tdp.setStyleSheet(f'color:{T["muted2"]}; font-size:10px; font-style:italic;')
        tl.addWidget(self.lbl_hw_tdp, 4, 0, 1, 3)

        self.chk_boot_power = QCheckBox('Apply TDP on boot')
        self.chk_boot_power.setChecked(power_cfg.get('apply_on_boot', False))
        self.chk_boot_power.toggled.connect(self._save_boot_pref)
        tl.addWidget(self.chk_boot_power, 5, 0, 1, 3)

        self.chk_turbo = QCheckBox('Enable Intel Turbo Boost')
        try:
            self.chk_turbo.setChecked(msr.get_turbo_boost())
        except:
            self.chk_turbo.setChecked(True)
        self.chk_turbo.toggled.connect(self._apply_turbo)
        tl.addWidget(self.chk_turbo, 6, 0, 1, 3)
        left_vbox.addWidget(tdp_group)
        
        # ── Turbo Ratios ──
        ratio_group = QGroupBox('TURBO RATIO LIMITS')
        rl = QGridLayout(ratio_group)
        rl.setSpacing(6)
        rl.setContentsMargins(10, 15, 10, 10)
        self._ratio_spins  = []
        self._ratio_flbls  = []   # inline GHz labels

        try:
            curr_ratios = msr.get_turbo_ratios()
        except:
            curr_ratios = [0, 0, 0, 0]

        saved_ratios = power_cfg.get('ratios', curr_ratios)

        # Header row
        for ci, txt in enumerate(['Active cores', 'Ratio', 'Freq']):
            h = QLabel(txt)
            h.setStyleSheet(f'color:{T["muted2"]}; font-size:9px; letter-spacing:1px;')
            h.setAlignment(Qt.AlignCenter)
            rl.addWidget(h, 0, ci)

        for i in range(4):
            core_lbl = QLabel(f'{i+1}C')
            core_lbl.setStyleSheet(f'color:{T["text"]}; font-size:13px; font-weight:bold;')
            core_lbl.setAlignment(Qt.AlignCenter)

            spin = QSpinBox()
            spin.setRange(8, 60)
            val = saved_ratios[i] if i < len(saved_ratios) else (curr_ratios[i] if i < len(curr_ratios) else 30)
            spin.setValue(val)
            spin.setAlignment(Qt.AlignCenter)
            spin.setMinimumWidth(80)
            spin.setStyleSheet(
                f"QSpinBox {{ background:{T['surface2']}; border:1px solid {T['border']}; "
                f"border-radius:6px; color:{T['accent']}; min-height:34px; "
                f"font-size:16px; font-weight:900; padding:0 8px; }}"
                f"QSpinBox::up-button, QSpinBox::down-button {{ width:22px; }}"
            )

            freq_lbl = QLabel(f'{val / 10:.2f} GHz')
            freq_lbl.setStyleSheet(f'color:{T["accent2"]}; font-weight:bold; font-size:12px;')
            freq_lbl.setAlignment(Qt.AlignCenter)

            # Live update GHz label as spinbox changes
            spin.valueChanged.connect(lambda v, fl=freq_lbl: fl.setText(f'{v / 10:.2f} GHz'))

            rl.addWidget(core_lbl,  i + 1, 0)
            rl.addWidget(spin,      i + 1, 1)
            rl.addWidget(freq_lbl,  i + 1, 2)
            self._ratio_spins.append(spin)
            self._ratio_flbls.append(freq_lbl)

        # Buttons row
        btn_read_ratios = QPushButton('↺ Read')
        btn_read_ratios.setToolTip('Read current ratios from hardware')
        btn_read_ratios.clicked.connect(self._read_ratios)
        btn_apply_ratios = QPushButton('⚡ Apply')
        btn_apply_ratios.setObjectName('primary')
        btn_apply_ratios.clicked.connect(self._apply_ratios)
        rl.addWidget(btn_read_ratios,  5, 0)
        rl.addWidget(btn_apply_ratios, 5, 1, 1, 2)
        right_vbox.addWidget(ratio_group)

        # ── Battery Info ──
        bat_group = QGroupBox('BATTERY STATUS')
        bl = QGridLayout(bat_group)
        self._bat_vals = {}
        for i, (key, title) in enumerate([('percent','Charge'),('status','Status'),('voltage','Voltage'),('power','Draw')]):
            t = QLabel(title); t.setStyleSheet(f'color:{T["muted2"]};font-size:10px;')
            v = QLabel('—');   v.setStyleSheet(f'color:{T["text"]};font-weight:bold;')
            bl.addWidget(t, 0, i); bl.addWidget(v, 1, i)
            self._bat_vals[key] = v
        right_vbox.addWidget(bat_group)

        self.status = status_label()
        main_layout.addWidget(self.status)

        # ── Flush Settings ──
        flush_group = QGroupBox('DANGER ZONE')
        flush_group.setStyleSheet(f'QGroupBox {{ border:1px solid {T["danger"]}; border-radius:6px; margin-top:6px; }} QGroupBox::title {{ color:{T["danger"]}; }}')
        fl = QHBoxLayout(flush_group)
        flush_lbl = QLabel('Remove all saved settings and stop boot persistence.')
        flush_lbl.setStyleSheet(f'color:{T["muted2"]}; font-size:10px;')
        self.btn_flush = QPushButton('🗑  Flush All Settings')
        self.btn_flush.setObjectName('danger')
        self.btn_flush.setMinimumWidth(160)
        self.btn_flush.clicked.connect(self._flush_settings)
        fl.addWidget(flush_lbl)
        fl.addStretch()
        fl.addWidget(self.btn_flush)
        main_layout.addWidget(flush_group)

        left_vbox.addStretch()
        right_vbox.addStretch()

    def refresh_widgets(self):
        power_cfg = self.config.get('power', {})
        
        self.long_slider.blockSignals(True)
        self.long_slider.setValue(power_cfg.get('long', 15))
        self.long_lbl.setText(f"{self.long_slider.value()} W")
        self.long_slider.blockSignals(False)

        self.short_slider.blockSignals(True)
        self.short_slider.setValue(power_cfg.get('short', 25))
        self.short_lbl.setText(f"{self.short_slider.value()} W")
        self.short_slider.blockSignals(False)

        self.profile_combo.blockSignals(True)
        self.profile_combo.setCurrentText(power_cfg.get('profile', 'balanced'))
        self.profile_combo.blockSignals(False)

        self.chk_boot_power.blockSignals(True)
        self.chk_boot_power.setChecked(power_cfg.get('apply_on_boot', False))
        self.chk_boot_power.blockSignals(False)

        saved_ratios = power_cfg.get('ratios', [0, 0, 0, 0])
        for i, (spin, flbl) in enumerate(zip(self._ratio_spins, self._ratio_flbls)):
            if i < len(saved_ratios):
                spin.blockSignals(True)
                spin.setValue(saved_ratios[i])
                spin.blockSignals(False)
                flbl.setText(f"{saved_ratios[i] / 10:.2f} GHz")

    def update_telemetry(self, data: dict, temp: float, fan: int = 0):
        bat = data.get('battery', {})
        for key, lbl in self._bat_vals.items():
            v = bat.get(key, '—')
            if key == 'percent': lbl.setText(f'{v}%')
            elif key == 'voltage': 
                try: lbl.setText(f'{float(v):.2f}V')
                except: lbl.setText(str(v))
            elif key == 'power': 
                try: lbl.setText(f'{float(v):.1f}W')
                except: lbl.setText(str(v))
            else: lbl.setText(str(v))

        # Guard: don't override the combo while the user has it open
        if not self.profile_combo.view().isVisible():
            prof = data.get('profile', 'unknown')
            # blockSignals so setCurrentText doesn't fire _apply_profile
            self.profile_combo.blockSignals(True)
            idx = self.profile_combo.findText(prof)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
            self.profile_combo.blockSignals(False)
            self.profile_active_lbl.setText(f'Current: {prof.upper()}')

        # Live hardware TDP readout
        pl1, pl2 = data.get('tdp', (0, 0))
        if pl1 or pl2:
            self.lbl_hw_tdp.setText(f'Hardware now:  PL1 {pl1} W  |  PL2 {pl2} W')
        else:
            self.lbl_hw_tdp.setText('Hardware: could not read RAPL limits')

    def _apply_profile(self):
        try:
            p = self.profile_combo.currentText()
            if self.profile_cb:
                self.profile_cb(p)
            else:
                sysfs.set_power_profile(p)
                self.config.setdefault('power', {})['profile'] = p
                self.save_cb()
            set_status(self.status, f"Profile set to {p}", "ok")
        except Exception as e:
            set_status(self.status, f"Profile failed: {str(e)}", "err")

    def _apply_tdp(self):
        try:
            l = self.long_slider.value()
            s = self.short_slider.value()
            sysfs.set_tdp(l, s)
            self.config.setdefault('power', {})['long'] = l
            self.config.setdefault('power', {})['short'] = s
            self.save_cb()
            set_status(self.status, f"TDP Limits applied: {l}W/{s}W", "ok")
        except Exception as e:
            set_status(self.status, f"TDP failed: {str(e)}", "err")

    def _apply_ratios(self):
        try:
            r = [s.value() for s in self._ratio_spins]
            msr.set_turbo_ratios(r)
            self.config.setdefault('power', {})['ratios'] = r
            self.save_cb()
            set_status(self.status, 'Turbo ratios applied', 'ok')
        except Exception as e:
            set_status(self.status, f'Ratios failed: {str(e)}', 'err')

    def _read_ratios(self):
        """Read current turbo ratios from hardware and refresh spinboxes."""
        try:
            ratios = msr.get_turbo_ratios()
            for i, (spin, flbl) in enumerate(zip(self._ratio_spins, self._ratio_flbls)):
                v = ratios[i] if i < len(ratios) else spin.value()
                spin.blockSignals(True)
                spin.setValue(v)
                spin.blockSignals(False)
                flbl.setText(f'{v / 10:.2f} GHz')
            set_status(self.status, 'Ratios read from hardware', 'ok')
        except Exception as e:
            set_status(self.status, f'Read failed: {str(e)}', 'err')

    def _apply_turbo(self, checked: bool):
        try:
            msr.set_turbo_boost(checked)
            set_status(self.status, f"Turbo Boost {'Enabled' if checked else 'Disabled'}", "warn")
        except Exception as e:
            set_status(self.status, f"Turbo toggle failed: {str(e)}", "err")

    def _save_boot_pref(self, checked: bool):
        self.config.setdefault('power', {})['apply_on_boot'] = checked
        self.save_cb()

    def _flush_settings(self):
        reply = QMessageBox.question(
            self, 'Flush All Settings',
            'This will delete all saved settings and disable boot persistence.\n\n'
            'Fan curve daemon will be stopped. The app will reset to defaults.\n\n'
            'Continue?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Stop fan daemon if running
        from core.fan import fan_daemon
        if fan_daemon and fan_daemon.isRunning():
            fan_daemon.stop()

        # Reset config to defaults and update in-place so all tabs reflect it
        fresh = reset_config()
        self.config.clear()
        self.config.update(fresh)

        # Sync UI controls to defaults
        self.long_slider.setValue(fresh['power']['long'])
        self.short_slider.setValue(fresh['power']['short'])
        self.profile_combo.setCurrentText(fresh['power']['profile'])
        self.chk_boot_power.setChecked(False)
        self.chk_turbo.setChecked(True)

        set_status(self.status, 'All settings flushed — defaults restored', 'warn')
