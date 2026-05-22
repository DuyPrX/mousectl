import os
import glob
import struct
import subprocess

# MSR Constants
MSR_VOLTAGE            = 0x150
MSR_TURBO_RATIO_LIMIT  = 0x1AD
HW_WRITE_HELPER       = '/usr/local/bin/mousectl-hw-write'

def _sudo_hw(op: str, *args) -> bool:
    try:
        ret = subprocess.run(
            ['sudo', HW_WRITE_HELPER, op] + [str(a) for a in args],
            capture_output=True, timeout=5
        )
        return ret.returncode == 0
    except Exception:
        return False

def _sudo_hw_read(op: str, *args) -> str | None:
    try:
        ret = subprocess.run(
            ['sudo', HW_WRITE_HELPER, op] + [str(a) for a in args],
            capture_output=True, text=True, timeout=5
        )
        return ret.stdout.strip() if ret.returncode == 0 else None
    except Exception:
        return None

def _load_msr():
    if not glob.glob('/dev/cpu/*/msr'):
        os.system('sudo modprobe msr 2>/dev/null')

def _get_cpus() -> list:
    cpus = []
    for path in sorted(glob.glob('/dev/cpu/[0-9]*/msr')):
        try:
            cpus.append(int(path.split('/')[3]))
        except Exception:
            pass
    return cpus

def _write_msr(val: int, cpu: int = 0, msr_addr: int = MSR_VOLTAGE) -> bool:
    try:
        fd = os.open(f'/dev/cpu/{cpu}/msr', os.O_WRONLY)
        try:
            os.lseek(fd, msr_addr, os.SEEK_SET)
            os.write(fd, struct.pack('Q', val))
        finally:
            os.close(fd)
        return True
    except PermissionError:
        return _sudo_hw('msr_write', cpu, hex(msr_addr), hex(val))
    except Exception:
        return False

def _read_msr(cpu: int = 0, msr_addr: int = MSR_VOLTAGE) -> int | None:
    try:
        fd = os.open(f'/dev/cpu/{cpu}/msr', os.O_RDONLY)
        try:
            os.lseek(fd, msr_addr, os.SEEK_SET)
            return struct.unpack('Q', os.read(fd, 8))[0]
        finally:
            os.close(fd)
    except PermissionError:
        raw = _sudo_hw_read('msr_read', cpu, hex(msr_addr))
        return int(raw, 16) if raw else None
    except Exception:
        return None

def get_turbo_ratios() -> list[int]:
    _load_msr()
    val = _read_msr(0, MSR_TURBO_RATIO_LIMIT)
    if val is None: return [0,0,0,0]
    return [
        val & 0xFF,
        (val >> 8) & 0xFF,
        (val >> 16) & 0xFF,
        (val >> 24) & 0xFF
    ]

def set_turbo_ratios(ratios: list[int]) -> bool:
    if len(ratios) < 4: return False
    _load_msr()
    curr = _read_msr(0, MSR_TURBO_RATIO_LIMIT)
    if curr is None: return False
    
    # Keep upper bits, replace lower 32 bits with ratios
    new_val = (curr & ~0xFFFFFFFF) | (ratios[3] << 24) | (ratios[2] << 16) | (ratios[1] << 8) | ratios[0]
    
    success = True
    for cpu in _get_cpus():
        if not _write_msr(new_val, cpu, MSR_TURBO_RATIO_LIMIT):
            success = False
    return success

def get_turbo_boost() -> bool:
    """Returns True if Turbo Boost is ENABLED (no_turbo == '0')"""
    try:
        path = '/sys/devices/system/cpu/intel_pstate/no_turbo'
        if os.path.exists(path):
            with open(path, 'r') as f:
                return f.read().strip() == '0'
    except Exception:
        pass
    return True

def set_turbo_boost(enable: bool) -> bool:
    path = '/sys/devices/system/cpu/intel_pstate/no_turbo'
    if not os.path.exists(path):
        return False
    val = '0' if enable else '1'
    try:
        with open(path, 'w') as f:
            f.write(val)
        return True
    except PermissionError:
        return _sudo_hw('sysfs_write', path, val)
    except Exception:
        return False
