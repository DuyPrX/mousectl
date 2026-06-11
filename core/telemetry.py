import time
import glob
import os
from pathlib import Path
from PySide6.QtCore import QThread, Signal
import core.sysfs as sysfs
from core.msr import _sudo_hw_read

_cpu_freq_paths_cache: list[str] = []
_cpu_freq_cache_initialized: bool = False

def get_cpu_freq() -> list[float]:
    """Returns list of current CPU frequencies in GHz."""
    global _cpu_freq_paths_cache, _cpu_freq_cache_initialized
    freqs = []
    
    if not _cpu_freq_cache_initialized:
        try:
            _cpu_freq_paths_cache = sorted(
                glob.glob('/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq'),
                key=lambda x: int(''.join(filter(str.isdigit, x)))
            )
            _cpu_freq_cache_initialized = True
        except:
            pass
            
    for path in _cpu_freq_paths_cache:
        try:
            with open(path, 'r') as f:
                val = int(f.read().strip())
                freqs.append(val / 1_000_000.0)
        except: pass
        
    if not freqs:
        # Fallback to /proc/cpuinfo if sysfs paths are locked or missing
        try:
            lines = Path('/proc/cpuinfo').read_text().splitlines()
            for line in lines:
                if line.startswith('cpu MHz'):
                    val = float(line.split(':')[1].strip())
                    freqs.append(val / 1000.0)
        except: pass
    return freqs

def get_cpu_usage(prev_times: list) -> tuple[dict, list]:
    """Returns (usage_dict, new_prev_times). Caller owns the state — no globals."""
    result = {'total': 0.0, 'cores': []}
    try:
        lines = Path('/proc/stat').read_text().splitlines()
        cpu_lines = [l for l in lines if l.startswith('cpu')]
        current = []
        for line in cpu_lines:
            parts = line.split()
            vals = list(map(int, parts[1:8]))  # user nice system idle iowait irq softirq
            current.append(vals)

        if prev_times and len(prev_times) == len(current):
            usages = []
            for prev, cur in zip(prev_times, current):
                prev_idle  = prev[3] + prev[4]
                cur_idle   = cur[3]  + cur[4]
                delta_total = sum(cur) - sum(prev) or 1
                delta_idle  = cur_idle - prev_idle
                pct = 100.0 * (1 - delta_idle / delta_total)
                usages.append(round(max(0.0, min(100.0, pct)), 1))
            result['total'] = usages[0]   # aggregate 'cpu' line
            result['cores'] = usages[1:]  # per-core cpu0, cpu1, ...

        return result, current
    except:
        return result, prev_times

def get_ram_usage() -> dict:
    """Read RAM usage from /proc/meminfo without external dependencies."""
    try:
        meminfo = Path('/proc/meminfo').read_text()
        total = 0
        available = 0
        for line in meminfo.splitlines():
            if line.startswith('MemTotal:'):
                total = int(line.split()[1]) # kB
            elif line.startswith('MemAvailable:'):
                available = int(line.split()[1]) # kB
        if total > 0:
            used = total - available
            pct = (used / total) * 100
            return {'total_gb': total / 1_048_576.0, 'used_gb': used / 1_048_576.0, 'pct': pct}
    except: pass
    return {'total_gb': 0.0, 'used_gb': 0.0, 'pct': 0.0}

_igpu_paths_cache: tuple[str | None, str | None] = (None, None) # (act_path, busy_path)
_igpu_cache_initialized: bool = False

def get_igpu_info() -> dict:
    """Monitor Intel integrated GPU frequency and usage if available via sysfs."""
    global _igpu_paths_cache, _igpu_cache_initialized
    info = {'freq_mhz': 0, 'busy_pct': None}
    
    act_path, busy_path = _igpu_paths_cache
    
    if not _igpu_cache_initialized:
        try:
            cards = glob.glob('/sys/class/drm/card[0-9]')
            for card in cards:
                a_path = f'{card}/gt_act_freq_mhz'
                if not os.path.exists(a_path):
                    a_path = f'{card}/gt/gt0/rps_act_freq_mhz'
                    if not os.path.exists(a_path):
                        a_path = f'{card}/device/tile0/gt0/gt_act_freq_mhz'
                if os.path.exists(a_path):
                    act_path = a_path
                    b_path = f'{card}/device/gpu_busy_percent'
                    if os.path.exists(b_path):
                        busy_path = b_path
                    break
            _igpu_paths_cache = (act_path, busy_path)
            _igpu_cache_initialized = True
        except:
            pass
            
    if act_path:
        try:
            with open(act_path, 'r') as f:
                info['freq_mhz'] = int(f.read().strip())
        except: pass
        
    if busy_path:
        try:
            with open(busy_path, 'r') as f:
                info['busy_pct'] = int(f.read().strip())
        except: pass
        
    return info

class PowerSampler(QThread):
    data_ready = Signal(dict)

    def __init__(self, interval=1.0):
        super().__init__()
        self.interval = interval
        self.running = True
        # Fix #7: instance-owned state, not a global
        self._prev_cpu_times: list = []
        # Fix #1: cache profile, refresh every 15 ticks (~22s) — avoids subprocess every 1.5s
        self._profile_cache = 'unknown'
        self._fan_service_cache = False
        self._profile_tick  = 0
        self._profile_refresh_every = 15

        # Network and disk telemetry previous states
        self._prev_net_bytes = (0, 0) # (rx, tx)
        self._prev_net_time = 0.0
        self._prev_disk_bytes = (0, 0) # (read, write)
        self._prev_disk_time = 0.0

    def get_net_speed(self) -> tuple[float, float]:
        """Calculates download and upload speed in KB/s across all physical interfaces."""
        try:
            lines = Path('/proc/net/dev').read_text().splitlines()
            rx = 0
            tx = 0
            for line in lines:
                if ':' not in line: continue
                iface, stats = line.split(':', 1)
                iface = iface.strip()
                if iface == 'lo' or iface.startswith(('docker', 'br-', 'veth', 'virbr', 'wg', 'tun', 'tap', 'anycast')):
                    continue
                parts = stats.split()
                if len(parts) >= 9:
                    rx += int(parts[0])
                    tx += int(parts[8])
            now = time.monotonic()
            dt = now - self._prev_net_time
            rx_speed = 0.0
            tx_speed = 0.0
            if self._prev_net_time > 0 and dt > 0:
                rx_speed = (rx - self._prev_net_bytes[0]) / dt / 1024.0
                tx_speed = (tx - self._prev_net_bytes[1]) / dt / 1024.0
            self._prev_net_bytes = (rx, tx)
            self._prev_net_time = now
            return rx_speed, tx_speed
        except:
            return 0.0, 0.0

    def get_disk_speed(self) -> tuple[float, float]:
        """Calculates disk read and write speed in KB/s from proc diskstats."""
        try:
            import re
            lines = Path('/proc/diskstats').read_text().splitlines()
            read_bytes = 0
            write_bytes = 0
            for line in lines:
                parts = line.split()
                if len(parts) < 14: continue
                dev = parts[2]
                if not re.match(r'^(sd[a-z]|nvme[0-9]+n[0-9]+|vd[a-z]|mmcblk[0-9]+)$', dev):
                    continue
                read_sectors = int(parts[5])
                write_sectors = int(parts[9])
                read_bytes += read_sectors * 512
                write_bytes += write_sectors * 512

            now = time.monotonic()
            dt = now - self._prev_disk_time
            r_speed = 0.0
            w_speed = 0.0
            if self._prev_disk_time > 0 and dt > 0:
                r_speed = (read_bytes - self._prev_disk_bytes[0]) / dt / 1024.0
                w_speed = (write_bytes - self._prev_disk_bytes[1]) / dt / 1024.0
            self._prev_disk_bytes = (read_bytes, write_bytes)
            self._prev_disk_time = now
            return r_speed, w_speed
        except:
            return 0.0, 0.0

    def get_power(self) -> float:
        return sysfs.get_cpu_power()

    def get_all_temps(self) -> dict:
        if not hasattr(self, '_all_temps_cache') or not self._all_temps_cache:
            self._all_temps_cache = []
            _SKIP_DRIVERS = {'nouveau', 'amdgpu', 'radeon', 'nvidia'}
            _SKIP_LABELS  = {'gpu', 'graphics'}
            try:
                for path in glob.glob('/sys/class/hwmon/hwmon*/name'):
                    name = Path(path).read_text().strip()
                    if name in _SKIP_DRIVERS:
                        continue
                    hwmon = os.path.dirname(path)

                    if name == 'coretemp':
                        for lp in glob.glob(f'{hwmon}/temp*_label'):
                            try:
                                label = Path(lp).read_text().strip()
                                if any(s in label.lower() for s in _SKIP_LABELS):
                                    continue
                                self._all_temps_cache.append((lp.replace('_label', '_input'), label))
                            except: pass

                    elif name == 'system76':
                        for lp in glob.glob(f'{hwmon}/temp*_label'):
                            try:
                                label = Path(lp).read_text().strip()
                                if any(s in label.lower() for s in _SKIP_LABELS):
                                    continue
                                self._all_temps_cache.append((lp.replace('_label', '_input'), f'S76 {label}'))
                            except: pass

                    elif name in ('pch_cannonlake', 'pch_tigerlake', 'pch_alderlake'):
                        p = f'{hwmon}/temp1_input'
                        if os.path.exists(p):
                            self._all_temps_cache.append((p, 'PCH'))

                    elif name == 'nvme':
                        for ti in ['1', '2', '3']:
                            p = f'{hwmon}/temp{ti}_input'
                            lp = f'{hwmon}/temp{ti}_label'
                            if os.path.exists(p):
                                try:
                                    label = Path(lp).read_text().strip() if os.path.exists(lp) else f'NVMe T{ti}'
                                    self._all_temps_cache.append((p, f'NVMe {label}'))
                                except: pass
                                break  # only first valid NVMe sensor

                    elif name == 'acpitz':
                        p = f'{hwmon}/temp1_input'
                        if os.path.exists(p):
                            self._all_temps_cache.append((p, 'ACPI'))
            except: pass

        temps = {}
        for path, display_name in self._all_temps_cache:
            try:
                with open(path, 'r') as f:
                    val = int(f.read().strip()) / 1000.0
                    temps[display_name] = val
            except: pass
        return temps

    def get_battery_info(self) -> dict:
        info = {'percent': 0, 'status': 'Unknown', 'voltage': 0.0, 'power': 0.0}
        try:
            path = '/sys/class/power_supply/BAT0'
            if os.path.exists(path):
                def r(f):
                    p = f'{path}/{f}'
                    return Path(p).read_text().strip() if os.path.exists(p) else None
                
                cap = r('capacity')
                stat = r('status')
                volt = r('voltage_now')
                curr = r('current_now')
                pwr = r('power_now')
                
                if cap: info['percent'] = int(cap)
                if stat: info['status'] = stat
                if volt: info['voltage'] = int(volt) / 1_000_000.0
                
                if pwr:
                    p_val = int(pwr) / 1_000_000.0
                elif volt and curr:
                    p_val = (int(volt) / 1_000_000.0) * (int(curr) / 1_000_000.0)
                else:
                    p_val = 0.0
                
                if stat == 'Discharging':
                    info['power'] = -p_val          # negative  = draining battery
                elif stat == 'Charging':
                    info['power'] = p_val           # positive  = charging
                else:
                    # Full / Not charging / Unknown — p_val is still real system draw
                    # from the AC adapter through the battery controller; show it as-is
                    info['power'] = p_val           # positive  = AC system draw
        except: pass
        return info

    def run(self):
        import os
        if os.name == 'nt':
            import subprocess
            import json
            while self.running:
                try:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    res = subprocess.run(
                        ["ssh", "dnxk@100.115.117.31", "/usr/local/bin/mousectl --telemetry-json"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        startupinfo=startupinfo,
                        timeout=5
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        data = json.loads(res.stdout)
                        self.data_ready.emit(data)
                except Exception as e:
                    print(f"[REMOTE] Sampler error: {e}")
                self.msleep(int(self.interval * 1000))
            return

        while self.running:
            try:
                freqs = get_cpu_freq()
                usage, self._prev_cpu_times = get_cpu_usage(self._prev_cpu_times)

                # Fix #1: Only call get_power_profile() / is_fan_service_active() every N ticks
                self._profile_tick += 1
                if self._profile_tick == 1 or self._profile_tick % self._profile_refresh_every == 0:
                    self._profile_cache = sysfs.get_power_profile()
                    self._fan_service_cache = sysfs.is_fan_service_active()

                rx_speed, tx_speed = self.get_net_speed()
                disk_read, disk_write = self.get_disk_speed()
                ram = get_ram_usage()
                igpu = get_igpu_info()

                data = {
                    'freqs':      freqs,
                    'avg_freq':   sum(freqs) / (len(freqs) or 1),
                    'cpu_w':      self.get_power(),
                    'cpu_usage':  usage,
                    'battery':    self.get_battery_info(),
                    'fan':        sysfs.get_fan_speed(),
                    'fan_duty':   sysfs.get_fan_duty(),
                    'temp':       sysfs.get_cpu_temp(),
                    'all_temps':  self.get_all_temps(),
                    'profile':    self._profile_cache,
                    'fan_service_active': self._fan_service_cache,
                    'tdp':        sysfs.get_tdp(),   # (pl1_w, pl2_w) live from hw
                    'ram':        ram,
                    'igpu':       igpu,
                    'net_speed':  (rx_speed, tx_speed),
                    'disk_speed': (disk_read, disk_write),
                }
                self.data_ready.emit(data)
            except Exception as e:
                print(f"Sampler error: {e}")
            self.msleep(int(self.interval * 1000))

    def stop(self):
        self.running = False
        self.wait()
