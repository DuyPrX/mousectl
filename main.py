import sys
import os
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QLabel, QSystemTrayIcon, QMenu)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QAction, QIcon

# Modular Imports
from core.config import load_config, save_config
from core.sysfs import get_cpu_temp, get_fan_speed
from core.telemetry import PowerSampler
from ui.style import SS, T
from ui.widgets import status_label, set_status
from ui.tabs.dashboard import DashboardTab
from ui.tabs.profiles import ProfilesTab
from ui.tabs.power import PowerTab
from ui.tabs.undervolt import UndervoltTab
from ui.tabs.fan import FanTab

from core.msr import _load_msr

class MouseCtl(QMainWindow):
    def __init__(self):
        super().__init__()
        _load_msr() # Ensure kernel module is loaded
        self._cfg = load_config()
        self._quitting = False
        
        self.setWindowTitle('mousectl')
        self.setMinimumSize(950, 750)
        
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # Central Widget
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.root = QVBoxLayout(self.central)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(0)

        self._setup_ui()
        self._setup_tray()

        # Fix #5: Interval configurable via config['telemetry']['interval'] (default 1.5s)
        interval = self._cfg.get('telemetry', {}).get('interval', 1.5)
        self.sampler = PowerSampler(interval=interval)
        self.sampler.data_ready.connect(self._on_telemetry)
        self.sampler.start()

        # Debounce timer — config is written 600ms after the last change, not on every event
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._do_save_cfg)

    def _setup_ui(self):
        # Header
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet(f"background:{T['surface']}; border-bottom:1px solid {T['border']};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 20, 0)
        
        logo = QLabel("🐭 mousectl")
        logo.setStyleSheet(f"color:{T['accent']}; font-size:18px; font-weight:900; letter-spacing:2px;")
        
        sub = QLabel("MousePro NB410H · Clevo L140CU")
        sub.setStyleSheet(f"color:{T['muted2']}; font-size:10px; margin-left:10px;")
        
        self.status = status_label()
        
        hl.addWidget(logo)
        hl.addWidget(sub)
        hl.addStretch()
        hl.addWidget(self.status)
        self.root.addWidget(header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        
        self.tab_dash = DashboardTab(self._cfg)
        self.tab_profiles = ProfilesTab(self._cfg, self._save_cfg, self.apply_custom_profile)
        self.tab_power = PowerTab(self._cfg, self._save_cfg, self.change_power_profile)
        self.tab_uv = UndervoltTab(self._cfg, self._save_cfg)
        self.tab_fan = FanTab(self._cfg, self._save_cfg)
        
        self.tabs.addTab(self.tab_dash, " DASHBOARD ")
        self.tabs.addTab(self.tab_profiles, " PROFILES ")
        self.tabs.addTab(self.tab_power, " POWER ")
        self.tabs.addTab(self.tab_uv, " UNDERVOLT ")
        self.tabs.addTab(self.tab_fan, " FAN CURVE ")
        
        self.root.addWidget(self.tabs)

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # Look for icon in project root or app data
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
            self.setWindowIcon(QIcon(icon_path))
        
        self.tray_menu = QMenu()
        self.tray_menu.setStyleSheet(SS)
        
        # Detailed Menu Items (v1 style)
        self.tray_cpu = QAction("CPU: --")
        self.tray_cpu.setEnabled(False)
        self.tray_usage = QAction("Usage: --")
        self.tray_usage.setEnabled(False)
        self.tray_fan = QAction("Fan: --")
        self.tray_fan.setEnabled(False)
        self.tray_bat = QAction("Battery: --")
        self.tray_bat.setEnabled(False)
        
        # New Diagnostics items
        self.tray_ram = QAction("RAM: --")
        self.tray_ram.setEnabled(False)
        self.tray_igpu = QAction("iGPU: --")
        self.tray_igpu.setEnabled(False)
        self.tray_net = QAction("Net: --")
        self.tray_net.setEnabled(False)
        self.tray_disk = QAction("Disk: --")
        self.tray_disk.setEnabled(False)
        
        self.tray_menu.addAction(self.tray_cpu)
        self.tray_menu.addAction(self.tray_usage)
        self.tray_menu.addAction(self.tray_fan)
        self.tray_menu.addAction(self.tray_bat)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.tray_ram)
        self.tray_menu.addAction(self.tray_igpu)
        self.tray_menu.addAction(self.tray_net)
        self.tray_menu.addAction(self.tray_disk)
        self.tray_menu.addSeparator()

        # Profiles Submenu
        self.profile_menu = self.tray_menu.addMenu("Power Profile")
        self.prof_actions = {}
        for p in ["Battery", "Balanced", "Performance"]:
            act = QAction(p, self)
            act.setCheckable(True)
            act.triggered.connect(lambda checked, name=p: self._change_profile_tray(name))
            self.profile_menu.addAction(act)
            self.prof_actions[p.lower()] = act

        self.tray_menu.addSeparator()
        
        show_act = QAction("Show Window", self)
        show_act.triggered.connect(self.show_window)
        self.tray_menu.addAction(show_act)
        self.tray_menu.setDefaultAction(show_act)
        
        self.tray_menu.addSeparator()
        
        quit_act = QAction("Exit App", self)
        quit_act.triggered.connect(self.quit_app)
        self.tray_menu.addAction(quit_act)
        
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def change_power_profile(self, name: str) -> bool:
        import core.sysfs as sysfs
        if sysfs.set_power_profile(name):
            self._cfg.setdefault('power', {})['profile'] = name.lower()
            self._save_cfg()
            # Invalidate telemetry cache instantly to avoid visual delay
            if hasattr(self, 'sampler'):
                self.sampler._profile_cache = name.lower()
            return True
        return False

    def apply_custom_profile(self, name: str) -> bool:
        if name not in self._cfg.get('profiles', {}):
            return False
            
        p_data = self._cfg['profiles'][name]
        
        # 1. Update active keys in-place
        for key in ['core', 'cache', 'gpu', 'uncore', 'analogio']:
            if key in p_data.get('undervolt', {}):
                self._cfg.setdefault('undervolt', {})[key] = p_data['undervolt'][key]
                
        for key in ['long', 'short', 'profile', 'ratios']:
            if key in p_data.get('power', {}):
                self._cfg.setdefault('power', {})[key] = p_data['power'][key]
                
        self._cfg['active_profile'] = name
        
        # 2. Write values to hardware
        import core.sysfs as sysfs
        import core.msr as msr
        from core.undervolt import set_undervolt
        
        p = self._cfg['power'].get('profile', 'balanced')
        sysfs.set_power_profile(p)
        if hasattr(self, 'sampler'):
            self.sampler._profile_cache = p.lower()
            
        l = self._cfg['power'].get('long', 15)
        s = self._cfg['power'].get('short', 25)
        sysfs.set_tdp(l, s)
        
        r = self._cfg['power'].get('ratios', [0, 0, 0, 0])
        try:
            msr.set_turbo_ratios(r)
        except Exception as e:
            print(f"[ERROR] Failed to apply turbo ratios: {e}")
            
        for plane in ['core', 'cache', 'gpu', 'uncore', 'analogio']:
            val = float(self._cfg['undervolt'].get(plane, 0.0))
            try:
                set_undervolt(plane, val)
            except Exception as e:
                print(f"[ERROR] Failed to apply undervolt to {plane}: {e}")
                
        # 3. Save config
        self._save_cfg()
        
        # 4. Refresh other tabs
        self.tab_power.refresh_widgets()
        self.tab_uv.refresh_widgets()
        
        return True

    def _change_profile_tray(self, name):
        self.change_power_profile(name)

    def _on_tray_activated(self, reason):
        # Trigger is single-click, DoubleClick is self-explanatory
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def show_window(self):
        self.show()
        self.activateWindow()

    def quit_app(self):
        self._quitting = True
        from core.fan import fan_daemon
        fan_daemon.stop()
        self.sampler.stop()
        QApplication.quit()

    def _save_cfg(self):
        """Called by any tab on change — restarts the debounce timer."""
        self._save_timer.start()   # resets the 600ms countdown on every call

    def _do_save_cfg(self):
        """Actual disk write — fires 600ms after the last _save_cfg call."""
        save_config(self._cfg)
        set_status(self.status, 'Config saved', 'ok')

    @Slot(dict)
    def _on_telemetry(self, data: dict):
        # This now runs on the UI thread due to signal/slot connection
        temp = data.get('temp', 0.0)
        fan = data.get('fan', 0)
        self.tab_dash.update_telemetry(data, temp, fan)
        self.tab_fan.update_telemetry(data, temp, fan)
        self.tab_power.update_telemetry(data, temp, fan)
        
        # Update Tray Menu (Details)
        bat    = data.get('battery', {})
        usage = data.get('cpu_usage', {}).get('total', 0.0)
        self.tray_cpu.setText(f"🌡 CPU: {temp:.1f}°C @ {data['cpu_w']:.1f}W")
        self.tray_usage.setText(f"📊 Usage: {usage:.1f}%")
        self.tray_fan.setText(f"🌪 Fan: {fan} RPM")

        # Context-aware battery label
        b_stat  = bat.get('status', 'Unknown')
        b_pct   = bat.get('percent', 0)
        b_power = bat.get('power', 0.0)
        if b_stat == 'Discharging':
            b_label = f"🔋 Bat: {b_pct}% ({abs(b_power):.1f}W draw)"
        elif b_stat == 'Charging':
            b_label = f"🔌 Bat: {b_pct}% (+{b_power:.1f}W charging)"
        else:  # Full / Not charging
            b_label = f"⚡ Bat: {b_pct}% ({b_power:.1f}W AC)"
        self.tray_bat.setText(b_label)

        # Update Diagnostics Tray Menu items
        ram = data.get('ram', {})
        self.tray_ram.setText(f"💾 RAM: {ram.get('used_gb', 0.0):.1f} / {ram.get('total_gb', 0.0):.1f} GB ({ram.get('pct', 0.0):.0f}%)")

        igpu = data.get('igpu', {})
        igpu_freq = igpu.get('freq_mhz', 0)
        igpu_busy = igpu.get('busy_pct')
        igpu_txt = f"🎮 iGPU: {igpu_freq} MHz"
        if igpu_busy is not None:
            igpu_txt += f" ({igpu_busy}%)"
        self.tray_igpu.setText(igpu_txt)

        def format_speed(kbps: float) -> str:
            if kbps >= 1024.0:
                return f"{kbps / 1024.0:.1f} MB/s"
            return f"{kbps:.0f} KB/s"

        net_rx, net_tx = data.get('net_speed', (0.0, 0.0))
        self.tray_net.setText(f"🌐 Net: ⬇ {format_speed(net_rx)} | ⬆ {format_speed(net_tx)}")

        disk_r, disk_w = data.get('disk_speed', (0.0, 0.0))
        self.tray_disk.setText(f"💽 Disk: 📖 {format_speed(disk_r)} | ✍ {format_speed(disk_w)}")
        
        # Sync Profile Checks
        active_prof = data.get('profile', 'balanced').lower()
        for p_name, act in self.prof_actions.items():
            act.setChecked(p_name == active_prof)

    def closeEvent(self, event):
        if not self._quitting:
            event.ignore()
            self.hide()
            # self.tray_icon.showMessage("mousectl", "Running in background", QSystemTrayIcon.Information, 1000)
        else:
            event.accept()

def main():
    app = QApplication(sys.argv)
    app.setDesktopFileName("mousectl")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(SS)
    win = MouseCtl()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
