"""
core/fan.py — Fan curve logic and UI daemon.

Separates the PySide6 QThread concern from the pure hardware I/O in sysfs.py.
The shared interpolate() function is also used by scripts/fan_daemon.py so that
both the UI daemon and the systemd service behave identically.
"""
import time
import logging
from PySide6.QtCore import QThread

from core.sysfs import get_cpu_temp, set_fan_speed, set_fan_auto

log = logging.getLogger(__name__)

# ── Tuning constants — single source of truth for both UI and systemd daemon ──
STEP_UP      = 2    # % per tick when temperature is rising
STEP_DOWN    = 1    # % per tick when temperature is falling (acoustic comfort)
POLL_SEC     = 0.8  # seconds between fan updates
HISTORY_SIZE = 10   # rolling average window size


def interpolate(curve: list, temp: float) -> int:
    """Linear interpolation of duty% from a [(temp, duty), ...] curve."""
    if not curve:
        return 30
    if temp <= curve[0][0]:
        return curve[0][1]
    if temp >= curve[-1][0]:
        return curve[-1][1]
    for i in range(1, len(curve)):
        t0, d0 = curve[i - 1]
        t1, d1 = curve[i]
        if t0 <= temp <= t1:
            return int(d0 + (temp - t0) / (t1 - t0) * (d1 - d0))
    return 30


class FanCurveDaemon(QThread):
    """
    Background QThread that continuously applies a fan curve to the hardware.
    Runs inside the UI process. For the systemd service version see
    scripts/fan_daemon.py which imports interpolate() from here.
    """

    def __init__(self):
        super().__init__()
        self.curve        = [(30, 30), (45, 40), (60, 55), (70, 70), (80, 85), (90, 100)]
        self.running      = False
        self.current_duty: float = 30.0
        self.temp_history: list[float] = []

    def run(self):
        self.running = True
        while self.running:
            try:
                # 1. Rolling average — smooths out brief CPU spikes
                raw_temp = get_cpu_temp()
                self.temp_history.append(raw_temp)
                if len(self.temp_history) > HISTORY_SIZE:
                    self.temp_history.pop(0)

                smooth_temp = sum(self.temp_history) / len(self.temp_history)

                # 2. Target duty from the active curve
                target_duty = interpolate(self.curve, smooth_temp)

                # 3. Gradual step — ramp up faster than ramp down (acoustic comfort)
                if target_duty > self.current_duty:
                    self.current_duty = min(self.current_duty + STEP_UP, target_duty)
                elif target_duty < self.current_duty:
                    self.current_duty = max(self.current_duty - STEP_DOWN, target_duty)

                ok = set_fan_speed(int(self.current_duty))
                if not ok:
                    log.warning("set_fan_speed(%d) failed — hwmon write rejected",
                                self.current_duty)

            except Exception as exc:
                log.error("FanCurveDaemon loop error: %s", exc)

            time.sleep(POLL_SEC)

    def stop(self):
        self.running = False
        set_fan_auto()
        self.wait(3000)   # 3s timeout — don't block UI forever if hwmon hangs


# Module-level singleton — imported by ui/tabs/fan.py
fan_daemon = FanCurveDaemon()
