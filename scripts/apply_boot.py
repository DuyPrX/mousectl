#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add project root to path to allow importing core modules
sys.path.append(str(Path(__file__).parent.parent))

from core.config import load_config, save_config
from core.sysfs import set_tdp, set_power_profile, set_fan_auto
from core.undervolt import set_undervolt
from core.msr import set_turbo_ratios

def main():
    print("--- mousectl boot apply ---")
    cfg = load_config()
    
    # 1. Undervolt
    if cfg['undervolt'].get('apply_on_boot'):
        planes = ['core', 'cache', 'gpu', 'uncore', 'analogio']
        for plane in planes:
            val = cfg['undervolt'].get(plane, 0.0)
            if set_undervolt(plane, val):
                print(f"[OK] {plane} undervolt: {val}mV")
            else:
                print(f"[FAIL] {plane} undervolt: {val}mV")

    # 2. Power & TDP
    if cfg['power'].get('apply_on_boot'):
        # TDP
        long_w = cfg['power'].get('long', 15)
        short_w = cfg['power'].get('short', 25)
        if set_tdp(long_w, short_w):
            print(f"[OK] TDP Limits: {long_w}W / {short_w}W")
        else:
            print(f"[FAIL] TDP Limits")
        
        # Profile
        profile = cfg['power'].get('profile', 'balanced')
        if set_power_profile(profile):
            print(f"[OK] Power Profile: {profile}")
        else:
            print(f"[FAIL] Power Profile: {profile}")
            
        # Turbo Ratios
        ratios = cfg['power'].get('ratios')
        if ratios:
            if set_turbo_ratios(ratios):
                print(f"[OK] Turbo Ratios: {ratios}")
            else:
                print(f"[FAIL] Turbo Ratios: {ratios}")

    # 3. Fan State
    if cfg.get('fan_lock_duty') is not None:
        cfg['fan_lock_duty'] = None
        save_config(cfg)
        print("[INFO] Cleared fan speed lock from previous session on boot")

    if cfg.get('fan_curve_active'):
        print("[INFO] Fan curve active in config. Check mousectl-fan.service.")
    else:
        if set_fan_auto():
            print("[OK] Fan set to Auto (Hardware Default)")
        else:
            print("[FAIL] Fan set to Auto")

    print("--- Done ---")

if __name__ == "__main__":
    main()
