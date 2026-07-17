from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLabel, QGridLayout)
from PySide6.QtCore import Qt
from ui.style import T
from ui.widgets import StatCard, TempGraph

def _sensor_sort_key(kv):
    """Sort sensors: Package first, then S76, PCH/ACPI, NVMe, then individual cores."""
    k = kv[0].lower()
    if 'package' in k: return (0, kv[0])
    if k.startswith('s76'): return (1, kv[0])
    if k in ('pch', 'acpi'): return (2, kv[0])
    if k.startswith('nvme'): return (3, kv[0])
    return (4, kv[0])

class DashboardTab(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 1. Stat cards row
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(8)
        self.card_cpu_temp  = StatCard('CPU TEMP',  '°C',  T['accent2'])
        self.card_fan_rpm   = StatCard('CPU FAN',   'RPM', T['accent'])
        self.card_power     = StatCard('CPU POWER', 'W',   T['warn'])
        self.card_freq      = StatCard('CPU FREQ',  'GHz', T['green'])
        self.card_usage     = StatCard('CPU USAGE', '%',   T['accent'])
        self.card_bat       = StatCard('BATTERY',   '%',   T['text'])
        self.card_profile   = StatCard('PROFILE',   '',    T['muted2'])
        
        for c in [self.card_cpu_temp, self.card_fan_rpm, self.card_power,
                  self.card_freq, self.card_usage, self.card_bat, self.card_profile]:
            c.setMinimumHeight(85)
            cards_layout.addWidget(c)
        main_layout.addLayout(cards_layout)

        # 1b. Diagnostics cards row
        diag_layout = QHBoxLayout()
        diag_layout.setSpacing(8)
        self.card_ram  = StatCard('RAM USAGE',  'Used / Total ( % )', T['accent'])
        self.card_igpu = StatCard('INTEL iGPU', 'Frequency',          T['accent2'])
        self.card_net  = StatCard('NETWORK',    '⬇ Download  /  ⬆ Upload', T['green'])
        self.card_disk = StatCard('DISK I/O',   '📖 Read  /  ✍ Write',      T['warn'])

        for c in [self.card_ram, self.card_igpu, self.card_net, self.card_disk]:
            c.setMinimumHeight(85)
            diag_layout.addWidget(c)
        main_layout.addLayout(diag_layout)

        # 2. Graphs row
        graphs_layout = QHBoxLayout()
        graphs_layout.setSpacing(8)
        self.graph_temp  = TempGraph('CPU TEMPERATURE', '°C',   100,  T['accent2'])
        self.graph_power = TempGraph('CPU POWER DRAW',  'W',    45,   T['warn'])
        self.graph_fan   = TempGraph('FAN SPEED',       'RPM',  6000, T['accent'])
        # Fix #11: CPU Usage graph — the obvious missing fourth graph
        self.graph_usage = TempGraph('CPU USAGE',       '%',    100,  T['green'])
        for g in [self.graph_temp, self.graph_power, self.graph_fan, self.graph_usage]:
            g.setMinimumHeight(180)
            graphs_layout.addWidget(g)
        main_layout.addLayout(graphs_layout)

        # 3. Grids container
        grids_layout = QHBoxLayout()
        grids_layout.setSpacing(8)

        # 3a. Sensor Grid
        sensors_box = QGroupBox("ALL SENSORS")
        self.grid_sensors = QGridLayout(sensors_box)
        self.grid_sensors.setSpacing(4)
        self.sensor_labels = {}
        grids_layout.addWidget(sensors_box, 1)

        # 3b. Core Frequency Grid
        freq_box = QGroupBox("CORE FREQUENCIES")
        self.grid_freq = QGridLayout(freq_box)
        self.grid_freq.setSpacing(4)
        self.freq_labels = {}
        grids_layout.addWidget(freq_box, 1)

        main_layout.addLayout(grids_layout)
        main_layout.addStretch()

    def update_telemetry(self, data: dict, temp: float, fan: int = 0):
        # Update cards
        self.card_cpu_temp.set_value(temp, 1)
        self.card_fan_rpm.set_value(data.get('fan', 0))
        self.card_power.set_value(data.get('cpu_w', 0), 1)
        self.card_freq.set_value(data.get('avg_freq', 0), 2)
        
        usage = data.get('cpu_usage', {})
        total_usage = usage.get('total', 0.0)
        self.card_usage.set_value(total_usage, 1)
        u_col = T['green'] if total_usage < 40 else T['warn'] if total_usage < 75 else T['danger']
        self.card_usage.set_color(u_col)
        
        bat = data.get('battery', {})
        self.card_bat.set_value(bat.get('percent', 0))
        
        prof = data.get('profile', 'unknown').upper()
        self.card_profile.set_value(prof)
        
        # Color cards
        self.card_cpu_temp.set_color(T['green'] if temp < 55 else T['warn'] if temp < 75 else T['danger'])

        # Update System Diagnostics cards
        def format_speed(kbps: float) -> str:
            if kbps >= 1024.0:
                return f"{kbps / 1024.0:.1f} MB/s"
            return f"{kbps:.0f} KB/s"

        ram = data.get('ram', {})
        ram_used = ram.get('used_gb', 0.0)
        ram_total = ram.get('total_gb', 0.0)
        ram_pct = ram.get('pct', 0.0)
        self.card_ram.set_value(f"{ram_used:.1f}/{ram_total:.1f} GB")
        self.card_ram.set_unit(f"RAM Usage: {ram_pct:.0f}%")
        self.card_ram.set_color(T['green'] if ram_pct < 60 else T['warn'] if ram_pct < 85 else T['danger'])

        igpu = data.get('igpu', {})
        igpu_freq = igpu.get('freq_mhz', 0)
        igpu_busy = igpu.get('busy_pct')
        if igpu_freq > 0:
            self.card_igpu.set_value(f"{igpu_freq} MHz")
        else:
            self.card_igpu.set_value("—")
        if igpu_busy is not None:
            self.card_igpu.set_unit(f"iGPU Usage: {igpu_busy}%")
            self.card_igpu.set_color(T['green'] if igpu_busy < 50 else T['warn'] if igpu_busy < 85 else T['danger'])
        else:
            self.card_igpu.set_unit("Intel HD/Iris Xe Graphics")
            self.card_igpu.set_color(T['accent2'])

        net_rx, net_tx = data.get('net_speed', (0.0, 0.0))
        self.card_net.set_value(f"{format_speed(net_rx)} / {format_speed(net_tx)}")
        self.card_net.set_unit("⬇ Download  /  ⬆ Upload")

        disk_r, disk_w = data.get('disk_speed', (0.0, 0.0))
        self.card_disk.set_value(f"{format_speed(disk_r)} / {format_speed(disk_w)}")
        self.card_disk.set_unit("📖 Read  /  ✍ Write")
        
        # Update graphs
        self.graph_temp.push(temp)
        self.graph_power.push(data.get('cpu_w', 0))
        self.graph_fan.push(data.get('fan', 0))
        self.graph_usage.push(total_usage)

        # Update Sensor Grid — 3 cols, colour-coded, stale-label cleanup
        all_temps = data.get('all_temps', {})
        sorted_items = sorted(all_temps.items(), key=_sensor_sort_key)
        COLS = 3

        for i, (name, val) in enumerate(sorted_items):
            if name not in self.sensor_labels:
                short = (name.replace('Package id 0', 'Package')
                             .replace('S76 ', ''))
                l = QLabel(short)
                l.setStyleSheet(f"color:{T['muted2']}; font-size:9px; letter-spacing:0.5px;")
                v = QLabel('—')
                v.setStyleSheet(f"color:{T['text']}; font-weight:bold; font-size:11px;")
                row, col = i // COLS, i % COLS
                self.grid_sensors.addWidget(l, row * 2,     col)
                self.grid_sensors.addWidget(v, row * 2 + 1, col)
                self.sensor_labels[name] = v

            c = T['green'] if val < 55 else T['warn'] if val < 80 else T['danger']
            self.sensor_labels[name].setStyleSheet(
                f"color:{c}; font-weight:bold; font-size:11px;")
            self.sensor_labels[name].setText(f"{val:.0f}°C")

        # Remove labels that disappeared (e.g. GPU temps now filtered out)
        for name in [n for n in list(self.sensor_labels) if n not in all_temps]:
            self.sensor_labels[name].setText('—')
            del self.sensor_labels[name]

        # Fix #8: Update Core Freq Grid — clean up stale labels if core count changes
        freqs = data.get('freqs', [])
        core_usages = data.get('cpu_usage', {}).get('cores', [])
        active_names = set()
        for i, freq in enumerate(freqs):
            name = f"Core {i}"
            active_names.add(name)
            core_pct = core_usages[i] if i < len(core_usages) else None
            if name not in self.freq_labels:
                l = QLabel(name)
                l.setStyleSheet(f"color:{T['muted2']}; font-size:10px;")
                v = QLabel("—")
                v.setStyleSheet(f"color:{T['green']}; font-weight:bold; font-size:11px;")
                row, col = i // 2, i % 2
                self.grid_freq.addWidget(l, row, col*2)
                self.grid_freq.addWidget(v, row, col*2+1)
                self.freq_labels[name] = v
            f_col = T['green'] if freq < 2.0 else T['warn'] if freq < 3.5 else T['accent2']
            usage_str = f" ({core_pct:.0f}%)" if core_pct is not None else ""
            self.freq_labels[name].setStyleSheet(f"color:{f_col}; font-weight:bold; font-size:11px;")
            self.freq_labels[name].setText(f"{freq:.2f} GHz{usage_str}")
        # Remove labels for cores no longer present
        stale = [n for n in list(self.freq_labels) if n not in active_names]
        for name in stale:
            self.freq_labels[name].setText("—")
            del self.freq_labels[name]
