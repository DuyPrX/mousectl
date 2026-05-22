#!/usr/bin/env python3
"""
mousectl fan daemon (systemd service version)
Tuning constants and interpolate() are imported from core.fan so this daemon
and the UI FanCurveDaemon are guaranteed to behave identically.
Runs as root under mousectl-fan.service.
"""
import os
import sys
import time
import logging
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from core.config import load_config, CONFIG_PATH
from core.sysfs import get_cpu_temp, set_fan_speed, set_fan_auto
from core.fan import interpolate, STEP_UP, STEP_DOWN, POLL_SEC, HISTORY_SIZE

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [fan-daemon] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)

def main():
    log.info("Fan daemon started")

    current_duty: float = 30.0
    temp_history: list[float] = []
    cfg = load_config()
    
    last_mtime = 0.0
    try:
        if os.path.exists(CONFIG_PATH):
            last_mtime = os.path.getmtime(CONFIG_PATH)
    except:
        pass

    while True:
        # Check if config file was modified since last load
        try:
            exists = os.path.exists(CONFIG_PATH)
            if exists:
                mtime = os.path.getmtime(CONFIG_PATH)
                if mtime != last_mtime:
                    cfg = load_config()
                    last_mtime = mtime
                    log.info("Config file modification detected — reloaded config instantly")
            elif last_mtime != 0.0:
                cfg = load_config()
                last_mtime = 0.0
                log.info("Config file was deleted — loaded default config")
        except Exception as e:
            log.warning("Config reload check failed: %s", e)

        # Check if fan lock duty is set in config (user locked speed)
        lock_duty = cfg.get('fan_lock_duty')
        if lock_duty is not None:
            try:
                lock_duty = int(lock_duty)
                if 20 <= lock_duty <= 100:
                    set_fan_speed(lock_duty)
                    # Locked — check for config updates in a responsive sleep loop
                    for _ in range(5):
                        time.sleep(1)
                        exists = os.path.exists(CONFIG_PATH)
                        if exists:
                            mtime = os.path.getmtime(CONFIG_PATH)
                            if mtime != last_mtime:
                                cfg = load_config()
                                last_mtime = mtime
                                log.info("Config file modification detected during lock — reloaded")
                                break
                        elif last_mtime != 0.0:
                            cfg = load_config()
                            last_mtime = 0.0
                            log.info("Config file deletion detected during lock — loaded defaults")
                            break
                    continue
            except Exception as e:
                log.warning("Failed to apply locked fan duty: %s", e)

        if not cfg.get('fan_curve_active'):
            set_fan_auto()
            # Not active — check again after a shorter, responsive pause
            for _ in range(5):
                time.sleep(1)
                try:
                    exists = os.path.exists(CONFIG_PATH)
                    if exists:
                        mtime = os.path.getmtime(CONFIG_PATH)
                        if mtime != last_mtime:
                            cfg = load_config()
                            last_mtime = mtime
                            log.info("Config file modification detected during idle — reloaded")
                            break
                    elif last_mtime != 0.0:
                        cfg = load_config()
                        last_mtime = 0.0
                        log.info("Config file deletion detected during idle — loaded defaults")
                        break
                except:
                    pass
            continue

        curve = cfg.get('fan_curve', [])

        try:
            # 1. Rolling average — same as FanCurveDaemon
            raw_temp = get_cpu_temp()
            temp_history.append(raw_temp)
            if len(temp_history) > HISTORY_SIZE:
                temp_history.pop(0)
            smooth_temp = sum(temp_history) / len(temp_history)

            # 2. Target duty from curve
            target_duty = interpolate(curve, smooth_temp)

            # 3. Gradual step — ramp up +2%, ramp down -1%
            if target_duty > current_duty:
                current_duty = min(current_duty + STEP_UP, target_duty)
            elif target_duty < current_duty:
                current_duty = max(current_duty - STEP_DOWN, target_duty)

            ok = set_fan_speed(int(current_duty))
            if not ok:
                log.warning("set_fan_speed(%d) failed — hwmon write rejected", current_duty)

        except Exception as e:
            log.error("Fan daemon loop error: %s", e)

        time.sleep(POLL_SEC)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Interrupted — restoring auto fan")
        set_fan_auto()
        sys.exit(0)
