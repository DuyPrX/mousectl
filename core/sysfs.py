import os
import glob
import subprocess
import time
import logging
from pathlib import Path
from core.msr import _sudo_hw, _sudo_hw_read

log = logging.getLogger(__name__)

# Fix #6/#9: Cache hwmon paths — avoid re-scanning /sys every tick
_hwmon_cache: dict[str, str | None] = {}

def _find_hwmon(name: str) -> str | None:
    if name in _hwmon_cache:
        return _hwmon_cache[name]
    for path in glob.glob('/sys/class/hwmon/hwmon*'):
        try:
            with open(os.path.join(path, 'name'), 'r') as f:
                if name in f.read():
                    _hwmon_cache[name] = path
                    return path
        except: pass
    _hwmon_cache[name] = None
    return None

_cpu_temp_path_cache: str | None = None
_rapl_path_cache: str | None = None

def _find_rapl_path() -> str | None:
    global _rapl_path_cache
    if _rapl_path_cache is not None:
        return _rapl_path_cache
    paths = glob.glob('/sys/class/powercap/intel-rapl*/intel-rapl:0')
    if not paths:
        paths = glob.glob('/sys/class/powercap/intel-rapl:0')
    if paths:
        _rapl_path_cache = paths[0]
        return _rapl_path_cache
    return None

def invalidate_hwmon_cache():
    """Call if hardware changes at runtime (e.g. module reload)."""
    global _cpu_temp_path_cache, _rapl_path_cache
    _hwmon_cache.clear()
    _cpu_temp_path_cache = None
    _rapl_path_cache = None

def get_cpu_temp() -> float:
    global _cpu_temp_path_cache
    if _cpu_temp_path_cache and os.path.exists(_cpu_temp_path_cache):
        try:
            with open(_cpu_temp_path_cache, 'r') as f:
                return float(f.read().strip()) / 1000.0
        except: pass

    path = _find_hwmon('coretemp')
    if path:
        try:
            for lp in glob.glob(f'{path}/temp*_label'):
                if 'Package' in Path(lp).read_text():
                    input_path = lp.replace('_label', '_input')
                    if os.path.exists(input_path):
                        _cpu_temp_path_cache = input_path
                        with open(input_path, 'r') as f:
                            return float(f.read().strip()) / 1000.0
            
            input_path = os.path.join(path, 'temp1_input')
            if os.path.exists(input_path):
                _cpu_temp_path_cache = input_path
                with open(input_path, 'r') as f:
                    return float(f.read().strip()) / 1000.0
        except: pass
    return 0.0

def get_fan_speed() -> int:
    path = _find_hwmon('system76') or _find_hwmon('it5570')
    if path:
        try:
            fpath = os.path.join(path, 'fan1_input')
            if os.path.exists(fpath):
                with open(fpath, 'r') as f:
                    return int(f.read().strip())
        except: pass
    return 0

def get_fan_duty() -> int:
    """Reads current fan duty cycle percentage from hardware (pwm1)."""
    path = _find_hwmon('system76') or _find_hwmon('it5570')
    if path:
        try:
            pwm_path = os.path.join(path, 'pwm1')
            if os.path.exists(pwm_path):
                with open(pwm_path, 'r') as f:
                    val = int(f.read().strip())
                    return int(round((val / 255.0) * 100))
        except: pass
    return 0

def set_fan_speed(percent: int) -> bool:
    pwm_val = int((percent / 100.0) * 255)
    path = _find_hwmon('system76') or _find_hwmon('it5570')
    if not path: return False
    
    success = True
    en_path = os.path.join(path, 'pwm1_enable')
    if os.path.exists(en_path):
        current_enable = None
        try:
            with open(en_path, 'r') as f:
                current_enable = f.read().strip()
        except:
            pass
        if current_enable != '1':
            _sudo_hw('sysfs_write', en_path, '1')

    pwm_path = os.path.join(path, 'pwm1')
    if os.path.exists(pwm_path):
        current_pwm = None
        try:
            with open(pwm_path, 'r') as f:
                current_pwm = f.read().strip()
        except:
            pass
        if current_pwm != str(pwm_val):
            if not _sudo_hw('sysfs_write', pwm_path, str(pwm_val)):
                success = False
    return success

def set_fan_auto() -> bool:
    path = _find_hwmon('system76') or _find_hwmon('it5570')
    if not path: return False
    en_path = os.path.join(path, 'pwm1_enable')
    if os.path.exists(en_path):
        current_enable = None
        try:
            with open(en_path, 'r') as f:
                current_enable = f.read().strip()
        except:
            pass
        if current_enable != '2':
            return _sudo_hw('sysfs_write', en_path, '2')
        return True
    return False

# Fix #2: Store last energy reading — no sleep needed, delta computed across sampler ticks
_last_energy: tuple[int, float] = (0, 0.0)  # (energy_uj, monotonic_time)

def get_cpu_power() -> float:
    """Read instantaneous CPU power from intel-rapl energy counter (no blocking sleep)."""
    global _last_energy
    rapl_base = _find_rapl_path()
    if not rapl_base: return 0.0
    path = os.path.join(rapl_base, 'energy_uj')

    try:
        with open(path, 'r') as f:
            e2 = int(f.read().strip())
        t2 = time.monotonic()
        e1, t1 = _last_energy
        _last_energy = (e2, t2)
        dt = t2 - t1
        # Need at least 100ms gap for a meaningful delta; skip on first call
        if e1 > 0 and dt >= 0.1:
            return max(0.0, (e2 - e1) / (dt * 1_000_000.0))
    except Exception:
        # Fallback: try via privileged helper (no sleep version)
        raw = _sudo_hw_read('sysfs_read', path)
        if raw:
            try:
                e2 = int(raw)
                t2 = time.monotonic()
                e1, t1 = _last_energy
                _last_energy = (e2, t2)
                dt = t2 - t1
                if e1 > 0 and dt >= 0.1:
                    return max(0.0, (e2 - e1) / (dt * 1_000_000.0))
            except: pass
    return 0.0



def get_power_profile() -> str:
    try:
        ret = subprocess.run(['system76-power', 'profile'], capture_output=True, text=True)
        for line in ret.stdout.splitlines():
            if 'Profile:' in line: return line.split(':')[1].strip()
    except: pass
    try:
        ret = subprocess.run(['powerprofilesctl', 'get'], capture_output=True, text=True)
        if ret.stdout: return ret.stdout.strip()
    except: pass
    return 'unknown'

def set_power_profile(profile: str) -> bool:
    try:
        subprocess.run(['system76-power', 'profile', profile.lower()], check=True)
        return True
    except: pass
    try:
        # Map common names to powerprofilesctl
        prof_map = {'battery': 'power-saver', 'balanced': 'balanced', 'performance': 'performance'}
        p = prof_map.get(profile.lower(), profile.lower())
        subprocess.run(['powerprofilesctl', 'set', p], check=True)
        return True
    except: return False


def get_tdp() -> tuple[int, int]:
    """Read current PL1 (long) and PL2 (short) from intel-rapl in watts.
    Falls back to the privileged shim on kernels where powercap is root-only."""
    base = _find_rapl_path()
    if not base: return (0, 0)

    def _read(f: str) -> int | None:
        p = f'{base}/{f}'
        try:
            return int(Path(p).read_text().strip())
        except PermissionError:
            raw = _sudo_hw_read('sysfs_read', p)
            return int(raw) if raw else None
        except Exception:
            return None

    pl1_uw = _read('constraint_0_power_limit_uw')
    pl2_uw = _read('constraint_1_power_limit_uw')
    if pl1_uw is None or pl2_uw is None:
        return (0, 0)
    return (pl1_uw // 1_000_000, pl2_uw // 1_000_000)

def set_tdp(long_w: int, short_w: int) -> bool:
    base = _find_rapl_path()
    if not base: return False
    
    ok0 = _sudo_hw('sysfs_write', f'{base}/constraint_0_power_limit_uw', str(int(long_w * 1000000)))
    ok1 = _sudo_hw('sysfs_write', f'{base}/constraint_1_power_limit_uw', str(int(short_w * 1000000)))
    return ok0 and ok1

def is_fan_service_active() -> bool:
    """Checks if the systemd fan service is currently running."""
    try:
        ret = subprocess.run(['systemctl', 'is-active', '--quiet', 'mousectl-fan.service'], timeout=2)
        return ret.returncode == 0
    except Exception:
        return False

