from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLabel, QPushButton, QComboBox, QLineEdit, QGridLayout, QMessageBox, QFrame)
from PySide6.QtCore import Qt
from ui.style import T
from ui.widgets import status_label, set_status, make_sep

class ProfilesTab(QWidget):
    def __init__(self, config, save_cb, apply_profile_cb, parent=None):
        super().__init__(parent)
        self.config = config
        self.save_cb = save_cb
        self.apply_profile_cb = apply_profile_cb
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Header Info Banner
        info_banner = QLabel("📋 Profile Manager: Apply presets or save custom configurations of TDP, ratios, and undervolts.")
        info_banner.setWordWrap(True)
        info_banner.setStyleSheet(f"color:{T['muted2']}; font-size:10px; border:1px solid {T['border']}; "
                                  f"border-radius:6px; padding:6px; background:{T['surface2']};")
        main_layout.addWidget(info_banner)
        
        # Main Split Content Layout
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)
        main_layout.addLayout(content_layout)
        
        # Left Panel - Selector and Snapshot Info
        left_panel = QVBoxLayout()
        content_layout.addLayout(left_panel, 3)
        
        # Right Panel - Actions (Create, Delete)
        right_panel = QVBoxLayout()
        content_layout.addLayout(right_panel, 2)
        
        # ─── Left Panel: Quick Switcher ───
        selector_group = QGroupBox("PROFILE SELECTOR")
        sel_layout = QGridLayout(selector_group)
        sel_layout.setSpacing(8)
        
        sel_layout.addWidget(QLabel("Select Profile:"), 0, 0)
        self.profile_dropdown = QComboBox()
        self.profile_dropdown.currentIndexChanged.connect(self._on_dropdown_selection_changed)
        sel_layout.addWidget(self.profile_dropdown, 0, 1)
        
        self.btn_apply = QPushButton("⚡ Apply Profile")
        self.btn_apply.setObjectName("primary")
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        sel_layout.addWidget(self.btn_apply, 0, 2)
        
        # Active profile display
        active_container = QHBoxLayout()
        lbl_active_title = QLabel("Active Profile: ")
        lbl_active_title.setStyleSheet(f"color:{T['muted2']}; font-size:11px;")
        self.lbl_active_val = QLabel("None")
        self.lbl_active_val.setStyleSheet(f"color:{T['green']}; font-size:14px; font-weight:bold; letter-spacing:1px;")
        active_container.addWidget(lbl_active_title)
        active_container.addWidget(self.lbl_active_val)
        active_container.addStretch()
        sel_layout.addLayout(active_container, 1, 0, 1, 3)
        
        left_panel.addWidget(selector_group)
        
        # ─── Left Panel: Snapshot Preview Panel ───
        preview_group = QGroupBox("PROFILE PARAMETERS PREVIEW")
        prev_layout = QHBoxLayout(preview_group)
        prev_layout.setSpacing(10)
        
        # Undervolt Preview Column
        uv_box = QFrame()
        uv_box.setStyleSheet(f"QFrame {{ background:{T['surface2']}; border:1px solid {T['border']}; border-radius:6px; }}")
        uv_layout = QVBoxLayout(uv_box)
        uv_layout.setContentsMargins(10, 10, 10, 10)
        uv_layout.setSpacing(6)
        
        uv_title = QLabel("UNDERVOLT OFFSETS")
        uv_title.setStyleSheet(f"color:{T['accent']}; font-weight:bold; font-size:9px; letter-spacing:1px; border:none;")
        uv_layout.addWidget(uv_title)
        uv_layout.addWidget(make_sep())
        
        self.preview_uv_labels = {}
        for plane in ['core', 'cache', 'gpu', 'uncore', 'analogio']:
            row = QHBoxLayout()
            lbl_name = QLabel(plane.upper())
            lbl_name.setStyleSheet(f"color:{T['muted2']}; font-size:10px; border:none;")
            lbl_val = QLabel("— mV")
            lbl_val.setStyleSheet(f"color:{T['text']}; font-weight:bold; border:none;")
            row.addWidget(lbl_name)
            row.addStretch()
            row.addWidget(lbl_val)
            uv_layout.addLayout(row)
            self.preview_uv_labels[plane] = lbl_val
            
        uv_layout.addStretch()
        prev_layout.addWidget(uv_box, 1)
        
        # Power & Limits Preview Column
        power_box = QFrame()
        power_box.setStyleSheet(f"QFrame {{ background:{T['surface2']}; border:1px solid {T['border']}; border-radius:6px; }}")
        power_layout = QVBoxLayout(power_box)
        power_layout.setContentsMargins(10, 10, 10, 10)
        power_layout.setSpacing(6)
        
        power_title = QLabel("POWER & TDP LIMITS")
        power_title.setStyleSheet(f"color:{T['accent2']}; font-weight:bold; font-size:9px; letter-spacing:1px; border:none;")
        power_layout.addWidget(power_title)
        power_layout.addWidget(make_sep())
        
        # Long TDP
        row_long = QHBoxLayout()
        lbl_long = QLabel("PL1 SUSTAINED")
        lbl_long.setStyleSheet(f"color:{T['muted2']}; font-size:10px; border:none;")
        self.lbl_val_long = QLabel("— W")
        self.lbl_val_long.setStyleSheet(f"color:{T['text']}; font-weight:bold; border:none;")
        row_long.addWidget(lbl_long)
        row_long.addStretch()
        row_long.addWidget(self.lbl_val_long)
        power_layout.addLayout(row_long)
        
        # Short TDP
        row_short = QHBoxLayout()
        lbl_short = QLabel("PL2 BURST")
        lbl_short.setStyleSheet(f"color:{T['muted2']}; font-size:10px; border:none;")
        self.lbl_val_short = QLabel("— W")
        self.lbl_val_short.setStyleSheet(f"color:{T['text']}; font-weight:bold; border:none;")
        row_short.addWidget(lbl_short)
        row_short.addStretch()
        row_short.addWidget(self.lbl_val_short)
        power_layout.addLayout(row_short)
        
        # System76 Profile
        row_prof = QHBoxLayout()
        lbl_prof = QLabel("SYS76 PROFILE")
        lbl_prof.setStyleSheet(f"color:{T['muted2']}; font-size:10px; border:none;")
        self.lbl_val_prof = QLabel("—")
        self.lbl_val_prof.setStyleSheet(f"color:{T['text']}; font-weight:bold; border:none;")
        row_prof.addWidget(lbl_prof)
        row_prof.addStretch()
        row_prof.addWidget(self.lbl_val_prof)
        power_layout.addLayout(row_prof)
        
        # Turbo Ratios
        row_ratios = QHBoxLayout()
        lbl_ratios = QLabel("TURBO RATIOS")
        lbl_ratios.setStyleSheet(f"color:{T['muted2']}; font-size:10px; border:none;")
        self.lbl_val_ratios = QLabel("—")
        self.lbl_val_ratios.setStyleSheet(f"color:{T['text']}; font-weight:bold; border:none;")
        row_ratios.addWidget(lbl_ratios)
        row_ratios.addStretch()
        row_ratios.addWidget(self.lbl_val_ratios)
        power_layout.addLayout(row_ratios)
        
        power_layout.addStretch()
        prev_layout.addWidget(power_box, 1)
        
        left_panel.addWidget(preview_group)
        
        # ─── Right Panel: Actions ───
        
        # Create Custom Profile Snapshot
        create_group = QGroupBox("SNAPSHOT LIVE SETTINGS")
        cr_layout = QVBoxLayout(create_group)
        cr_layout.setSpacing(10)
        
        lbl_desc = QLabel("Save your current active undervolt offsets and TDP limits as a custom named profile.")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color:{T['muted2']}; font-size:10px;")
        cr_layout.addWidget(lbl_desc)
        
        cr_layout.addWidget(QLabel("Profile Name:"))
        self.txt_profile_name = QLineEdit()
        self.txt_profile_name.setPlaceholderText("e.g. My Battery Tune")
        self.txt_profile_name.setStyleSheet(
            f"QLineEdit {{ background:{T['surface2']}; border:1px solid {T['border']}; "
            f"border-radius:6px; color:{T['text']}; padding:6px 10px; }}"
        )
        cr_layout.addWidget(self.txt_profile_name)
        
        self.btn_save_current = QPushButton("📷 Save Current Live Settings")
        self.btn_save_current.setObjectName("primary")
        self.btn_save_current.clicked.connect(self._on_save_current_clicked)
        cr_layout.addWidget(self.btn_save_current)
        
        self.btn_update_existing = QPushButton("💾 Save Live Settings to Selected Profile")
        self.btn_update_existing.clicked.connect(self._on_update_existing_clicked)
        cr_layout.addWidget(self.btn_update_existing)
        
        right_panel.addWidget(create_group)
        
        # Delete Selected Custom Profile
        mgmt_group = QGroupBox("PROFILE CONFIGURATION")
        mgmt_layout = QVBoxLayout(mgmt_group)
        mgmt_layout.setSpacing(10)
        
        lbl_del_desc = QLabel("Delete custom-created profiles. System default profiles are protected and cannot be deleted.")
        lbl_del_desc.setWordWrap(True)
        lbl_del_desc.setStyleSheet(f"color:{T['muted2']}; font-size:10px;")
        mgmt_layout.addWidget(lbl_del_desc)
        
        self.btn_delete = QPushButton("🗑  Delete Selected Profile")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        mgmt_layout.addWidget(self.btn_delete)
        
        right_panel.addWidget(mgmt_group)
        
        # Stretch items to line everything up beautifully
        left_panel.addStretch()
        right_panel.addStretch()
        
        # Status Label
        self.status = status_label()
        main_layout.addWidget(self.status)
        
        # Load initial profiles list
        self.refresh_profile_list()

    def refresh_profile_list(self):
        """Populates or updates the profile QComboBox list and shows active profile."""
        self.profile_dropdown.blockSignals(True)
        self.profile_dropdown.clear()
        
        profiles = self.config.get('profiles', {})
        active = self.config.get('active_profile', '')
        
        # Add all profiles
        self.profile_dropdown.addItems(sorted(profiles.keys()))
        
        # Select active in dropdown, or fall back to first one if items exist
        if self.profile_dropdown.count() > 0:
            idx = self.profile_dropdown.findText(active)
            if idx >= 0:
                self.profile_dropdown.setCurrentIndex(idx)
            else:
                self.profile_dropdown.setCurrentIndex(0)
            
        self.profile_dropdown.blockSignals(False)
        
        # Set active profile text
        self.lbl_active_val.setText(active.upper())
        
        # Trigger update of preview display
        self._on_dropdown_selection_changed()

    def _on_dropdown_selection_changed(self):
        """Fires when the dropdown selection changes to preview settings of that profile."""
        selected_name = self.profile_dropdown.currentText()
        if not selected_name:
            self._clear_preview()
            self.btn_delete.setEnabled(False)
            return
            
        profiles = self.config.get('profiles', {})
        p_data = profiles.get(selected_name)
        if not p_data:
            self._clear_preview()
            self.btn_delete.setEnabled(False)
            return
            
        # Update preview values
        # 1. Undervolts
        uv = p_data.get('undervolt', {})
        for plane, lbl in self.preview_uv_labels.items():
            val = uv.get(plane, 0.0)
            lbl.setText(f"{int(val)} mV")
            
        # 2. Power / TDP
        power = p_data.get('power', {})
        self.lbl_val_long.setText(f"{power.get('long', '—')} W")
        self.lbl_val_short.setText(f"{power.get('short', '—')} W")
        self.lbl_val_prof.setText(str(power.get('profile', '—')).upper())
        
        ratios = power.get('ratios', [])
        if ratios:
            r_text = "/".join(str(r) for r in ratios)
            self.lbl_val_ratios.setText(r_text)
        else:
            self.lbl_val_ratios.setText("—")
            
        # 3. Handle Delete and Overwrite Button Enablement
        default_names = []
        is_custom = selected_name not in default_names
        self.btn_delete.setEnabled(is_custom)
        self.btn_update_existing.setEnabled(is_custom)

    def _clear_preview(self):
        for lbl in self.preview_uv_labels.values():
            lbl.setText("— mV")
        self.lbl_val_long.setText("— W")
        self.lbl_val_short.setText("— W")
        self.lbl_val_prof.setText("—")
        self.lbl_val_ratios.setText("—")

    def _on_apply_clicked(self):
        name = self.profile_dropdown.currentText()
        if not name:
            set_status(self.status, "Select a valid profile first.", "err")
            return
            
        success = self.apply_profile_cb(name)
        if success:
            set_status(self.status, f"Profile '{name}' applied successfully!", "ok")
            self.lbl_active_val.setText(name.upper())
        else:
            set_status(self.status, f"Failed to apply profile '{name}'. Check logs.", "err")

    def _on_save_current_clicked(self):
        name = self.txt_profile_name.text().strip()
        if not name:
            set_status(self.status, "Please enter a profile name first.", "err")
            return
            
        default_names = []
        if name in default_names:
            set_status(self.status, "Cannot overwrite default system profiles.", "err")
            return
            
        # Capture a snapshot of current active settings from the config
        uv_cfg = self.config.get('undervolt', {})
        power_cfg = self.config.get('power', {})
        
        snapshot = {
            'undervolt': {
                'core': uv_cfg.get('core', 0.0),
                'cache': uv_cfg.get('cache', 0.0),
                'gpu': uv_cfg.get('gpu', 0.0),
                'uncore': uv_cfg.get('uncore', 0.0),
                'analogio': uv_cfg.get('analogio', 0.0)
            },
            'power': {
                'long': power_cfg.get('long', 15),
                'short': power_cfg.get('short', 25),
                'profile': power_cfg.get('profile', 'balanced'),
                'ratios': list(power_cfg.get('ratios', [30, 30, 30, 30]))
            }
        }
        
        # Save to config under profiles list
        self.config.setdefault('profiles', {})[name] = snapshot
        
        # Clean line edit
        self.txt_profile_name.clear()
        
        # Save config file (triggers debounce timer)
        self.save_cb()
        
        # Refresh and select new profile
        self.refresh_profile_list()
        
        # Select the newly created profile in the dropdown
        idx = self.profile_dropdown.findText(name)
        if idx >= 0:
            self.profile_dropdown.setCurrentIndex(idx)
            
        set_status(self.status, f"Current settings saved as profile '{name}'.", "ok")

    def _on_update_existing_clicked(self):
        name = self.profile_dropdown.currentText()
        if not name:
            set_status(self.status, "Select an existing profile first.", "err")
            return
            
        reply = QMessageBox.question(
            self, 'Update Profile',
            f"Are you sure you want to overwrite profile '{name}' with your current live settings?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
            
        # Capture a snapshot of current active settings from the config
        uv_cfg = self.config.get('undervolt', {})
        power_cfg = self.config.get('power', {})
        
        snapshot = {
            'undervolt': {
                'core': uv_cfg.get('core', 0.0),
                'cache': uv_cfg.get('cache', 0.0),
                'gpu': uv_cfg.get('gpu', 0.0),
                'uncore': uv_cfg.get('uncore', 0.0),
                'analogio': uv_cfg.get('analogio', 0.0)
            },
            'power': {
                'long': power_cfg.get('long', 15),
                'short': power_cfg.get('short', 25),
                'profile': power_cfg.get('profile', 'balanced'),
                'ratios': list(power_cfg.get('ratios', [30, 30, 30, 30]))
            }
        }
        
        # Save to config under profiles list
        self.config.setdefault('profiles', {})[name] = snapshot
        
        # Save config file (triggers debounce timer)
        self.save_cb()
        
        # Refresh and select profile
        self.refresh_profile_list()
        
        # Select the updated profile in the dropdown
        idx = self.profile_dropdown.findText(name)
        if idx >= 0:
            self.profile_dropdown.setCurrentIndex(idx)
            
        set_status(self.status, f"Profile '{name}' updated with live settings.", "ok")

    def _on_delete_clicked(self):
        name = self.profile_dropdown.currentText()
        if not name:
            return
            
        default_names = []
        if name in default_names:
            set_status(self.status, "Cannot delete system default profiles.", "err")
            return
            
        reply = QMessageBox.question(
            self, 'Delete Custom Profile',
            f"Are you sure you want to permanently delete custom profile '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
            
        # Delete from profiles dictionary
        if 'profiles' in self.config and name in self.config['profiles']:
            del self.config['profiles'][name]
            
        # If the deleted profile was active, set active to empty
        if self.config.get('active_profile') == name:
            self.config['active_profile'] = ''
            
        # Save and refresh dropdown list
        self.save_cb()
        self.refresh_profile_list()
        
        set_status(self.status, f"Profile '{name}' deleted.", "warn")
