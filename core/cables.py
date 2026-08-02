#!/usr/bin/env python3
# ============================================================
# mousectl Cables & USB Diagnostics (WhatCable-Linux Integration)
# Reads USB devices, negotiated link speeds, max power draw, 
# USB-C Type-C roles, and AC/Battery Power Delivery metrics.
# ============================================================

import os
import glob
from pathlib import Path

def parse_speed(speed_raw: str) -> dict:
    """Parses raw sysfs USB speed string (e.g. '480', '5000', '12', '1.5') into human-readable details."""
    try:
        val = float(speed_raw)
    except Exception:
        return {"speed_str": speed_raw or "Unknown", "version": "Unknown", "class": "Standard"}
        
    if val <= 1.5:
        return {"speed_str": "1.5 Mbps", "version": "USB 1.0", "class": "Low-Speed"}
    elif val <= 12:
        return {"speed_str": "12 Mbps", "version": "USB 1.1", "class": "Full-Speed"}
    elif val <= 480:
        return {"speed_str": "480 Mbps", "version": "USB 2.0", "class": "High-Speed"}
    elif val <= 5000:
        return {"speed_str": "5 Gbps", "version": "USB 3.2 Gen 1", "class": "SuperSpeed 5G"}
    elif val <= 10000:
        return {"speed_str": "10 Gbps", "version": "USB 3.2 Gen 2", "class": "SuperSpeed 10G"}
    elif val <= 20000:
        return {"speed_str": "20 Gbps", "version": "USB 3.2 Gen 2x2", "class": "SuperSpeed 20G"}
    elif val <= 40000:
        return {"speed_str": "40 Gbps", "version": "USB4 / Thunderbolt", "class": "USB4 40G"}
    else:
        return {"speed_str": f"{val} Mbps", "version": "High-Speed USB", "class": "SuperSpeed"}

def get_usb_devices() -> list:
    """Scans /sys/bus/usb/devices/ for connected USB devices, hubs, and cables."""
    devices = []
    base_path = "/sys/bus/usb/devices"
    if not os.path.exists(base_path):
        return devices

    for dev_dir in sorted(glob.glob(os.path.join(base_path, "*"))):
        # Ignore interface sub-nodes (e.g. 1-1:1.0)
        dev_name = os.path.basename(dev_dir)
        if ":" in dev_name:
            continue
            
        speed_file = os.path.join(dev_dir, "speed")
        product_file = os.path.join(dev_dir, "product")
        id_vendor_file = os.path.join(dev_dir, "idVendor")
        
        # Only process if speed file or product/vendor exists
        if not (os.path.exists(speed_file) or os.path.exists(product_file) or os.path.exists(id_vendor_file)):
            continue

        def read_file(fname: str, default: str = "") -> str:
            p = os.path.join(dev_dir, fname)
            if os.path.isfile(p):
                try:
                    return Path(p).read_text().strip()
                except Exception:
                    pass
            return default

        product = read_file("product", "")
        manufacturer = read_file("manufacturer", "")
        id_vendor = read_file("idVendor", "")
        id_product = read_file("idProduct", "")
        speed_raw = read_file("speed", "")
        max_power = read_file("maxpower", "")
        bcd_device = read_file("bcdDevice", "")
        busnum = read_file("busnum", "")
        devnum = read_file("devnum", "")
        rx_lanes = read_file("rx_lanes", "")
        tx_lanes = read_file("tx_lanes", "")

        # Skip entries without any name, product, or vendor ID
        if not product and not manufacturer and not id_vendor:
            continue

        name = product or manufacturer or f"USB Device ({id_vendor}:{id_product})"
        speed_info = parse_speed(speed_raw)

        lanes_str = ""
        if rx_lanes and tx_lanes:
            lanes_str = f"{rx_lanes}x{tx_lanes}"

        devices.append({
            "sysfs_id": dev_name,
            "name": name,
            "manufacturer": manufacturer,
            "product": product,
            "vendor_id": id_vendor,
            "product_id": id_product,
            "speed_raw": speed_raw,
            "speed_str": speed_info["speed_str"],
            "version": speed_info["version"],
            "class": speed_info["class"],
            "max_power": max_power,
            "bcd_device": bcd_device,
            "busnum": busnum,
            "devnum": devnum,
            "lanes": lanes_str
        })

    return devices

def get_power_supply_info() -> dict:
    """Scans /sys/class/power_supply/ for AC charger and battery data, calculating direct Type-C power draw."""
    res = {
        "ac_online": False,
        "ac_type": "Disconnected",
        "battery_capacity": 0,
        "battery_status": "Unknown",
        "battery_health_pct": 100.0,
        "battery_voltage_v": 0.0,
        "battery_current_a": 0.0,
        "battery_power_w": 0.0,
        "charge_now_mah": 0,
        "charge_full_mah": 0,
        "charge_design_mah": 0,
        "manufacturer": "",
        "model": "",
        "cpu_power_w": 0.0,
        "direct_typec_power_w": 0.0,
        "is_passthrough": False
    }

    # Fetch CPU Package Power from RAPL (via sysfs)
    try:
        import core.sysfs as sysfs
        res["cpu_power_w"] = round(sysfs.get_cpu_power(), 1)
    except Exception:
        pass

    base_path = "/sys/class/power_supply"
    if not os.path.exists(base_path):
        return res

    for ps in glob.glob(os.path.join(base_path, "*")):
        name = os.path.basename(ps)
        def read_val(fname: str, default: str = "") -> str:
            p = os.path.join(ps, fname)
            if os.path.isfile(p):
                try:
                    return Path(p).read_text().strip()
                except Exception:
                    pass
            return default

        ps_type = read_val("type", "").lower()
        if "ac" in name.lower() or ps_type in ("mains", "usb", "usb_pd", "usb_dcp", "usb_cdp", "usb_sdp"):
            online = read_val("online", "0")
            if online == "1":
                res["ac_online"] = True
                res["ac_type"] = read_val("type", "Mains")
        elif "bat" in name.lower() or ps_type == "battery":
            res["battery_capacity"] = int(read_val("capacity", "0") or 0)
            res["battery_status"] = read_val("status", "Unknown")
            res["manufacturer"] = read_val("manufacturer", "")
            res["model"] = read_val("model_name", "")

            # Microvolts & Microamps to Volts & Amps
            v_now = float(read_val("voltage_now", "0") or 0) / 1e6
            i_now = float(read_val("current_now", "0") or 0) / 1e6
            res["battery_voltage_v"] = round(v_now, 2)
            res["battery_current_a"] = round(i_now, 2)
            res["battery_power_w"] = round(v_now * i_now, 2)

            # Charges
            c_now = float(read_val("charge_now", "0") or 0) / 1000.0
            c_full = float(read_val("charge_full", "0") or 0) / 1000.0
            c_design = float(read_val("charge_full_design", "0") or 0) / 1000.0
            
            res["charge_now_mah"] = int(c_now)
            res["charge_full_mah"] = int(c_full)
            res["charge_design_mah"] = int(c_design)

            if c_design > 0:
                res["battery_health_pct"] = round((c_full / c_design) * 100.0, 1)

    # 1. Check for Direct Hardware Sensor Nodes (UCSI, USB PD controller, hwmon charger sensors)
    direct_hw_power = None
    hardware_sensor_name = ""

    for ps in glob.glob(os.path.join(base_path, "*")):
        ps_name = os.path.basename(ps).lower()
        if any(k in ps_name for k in ("ucsi", "usb_pd", "usb-pd", "charger", "typec")):
            v_path = os.path.join(ps, "voltage_now")
            i_path = os.path.join(ps, "current_now")
            p_path = os.path.join(ps, "power_now")
            
            if os.path.isfile(p_path):
                try:
                    p_uw = float(Path(p_path).read_text().strip())
                    if p_uw > 0:
                        direct_hw_power = round(p_uw / 1e6, 1)
                        hardware_sensor_name = os.path.basename(ps)
                        break
                except Exception:
                    pass
            elif os.path.isfile(v_path) and os.path.isfile(i_path):
                try:
                    v_uv = float(Path(v_path).read_text().strip())
                    i_ua = float(Path(i_path).read_text().strip())
                    if v_uv > 0 and i_ua > 0:
                        direct_hw_power = round((v_uv / 1e6) * (i_ua / 1e6), 1)
                        hardware_sensor_name = os.path.basename(ps)
                        break
                except Exception:
                    pass

    # 2. Assign values: Direct Hardware Sensor vs RAPL Fallback Calculation
    if direct_hw_power is not None:
        res["direct_typec_power_w"] = direct_hw_power
        res["power_sensor_type"] = "Direct Hardware ADC Sensor"
        res["sensor_label"] = f"W (Hardware: {hardware_sensor_name})"
        res["is_passthrough"] = res["ac_online"] and (res["battery_status"].lower() in ("not charging", "idle", "full") or res["battery_current_a"] == 0)
    else:
        res["power_sensor_type"] = "RAPL Calculated"
        res["sensor_label"] = "W (Calculated)"
        if res["ac_online"]:
            st = res["battery_status"].lower()
            if st in ("not charging", "idle", "full") or res["battery_current_a"] == 0:
                res["is_passthrough"] = True
                # In direct pass-through mode, battery input is 0. Total Type-C draw = CPU Package W + System Overhead (~4.0W)
                res["direct_typec_power_w"] = round(res["cpu_power_w"] + 4.0, 1)
            else:
                res["is_passthrough"] = False
                res["direct_typec_power_w"] = round(res["cpu_power_w"] + res["battery_power_w"] + 4.0, 1)

    return res

def get_typec_info() -> list:
    """Scans /sys/class/typec/ for Type-C ports and USB-C roles."""
    ports = []
    base_path = "/sys/class/typec"
    if not os.path.exists(base_path):
        return ports

    for port_dir in sorted(glob.glob(os.path.join(base_path, "port*"))):
        port_name = os.path.basename(port_dir)
        def read_file(fname: str) -> str:
            p = os.path.join(port_dir, fname)
            if os.path.isfile(p):
                try:
                    return Path(p).read_text().strip()
                except Exception:
                    pass
            return "N/A"

        power_role = read_file("power_role")
        data_role = read_file("data_role")
        pwr_opmode = read_file("power_operation_mode")
        vconn_role = read_file("vconn_role")

        ports.append({
            "port": port_name,
            "power_role": power_role,
            "data_role": data_role,
            "power_opmode": pwr_opmode,
            "vconn_role": vconn_role
        })

    return ports

def get_cables_report() -> dict:
    """Combines USB devices, Power Supply, and Type-C info into a full WhatCable diagnostic report."""
    usb_devs = get_usb_devices()
    power = get_power_supply_info()
    typec = get_typec_info()

    # Generate plain-English summary (WhatCable style!)
    summary_parts = []
    if power["is_passthrough"]:
        summary_parts.append(
            f"⚡ Direct Type-C / AC Power Active (Pass-Through Mode). "
            f"Battery charging paused at {power['battery_capacity']}% (0.00A). "
            f"Estimated Type-C Input Draw: ~{power['direct_typec_power_w']} W (Derived: RAPL CPU {power['cpu_power_w']} W + System ~4.0 W; no direct Type-C hardware ADC sensor on this platform)."
        )
    elif power["ac_online"]:
        summary_parts.append(
            f"🔌 Charging via {power['ac_type']} ({power['battery_power_w']} W into battery). "
            f"Total Type-C Input Draw: ~{power['direct_typec_power_w']} W."
        )
    else:
        summary_parts.append(
            f"🔋 Running on Battery ({power['battery_capacity']}%, {power['battery_power_w']} W discharge)."
        )

    if typec:
        p0 = typec[0]
        summary_parts.append(f"⚡ USB-C Port: Power [{p0['power_role']}], Data [{p0['data_role']}].")

    if usb_devs:
        high_speed = [d for d in usb_devs if "Gbps" in d["speed_str"] or "480" in d["speed_str"]]
        summary_parts.append(f"📦 {len(usb_devs)} USB Peripherals connected ({len(high_speed)} High/SuperSpeed).")
    else:
        summary_parts.append("📦 No external USB devices detected.")

    summary = " ".join(summary_parts)

    return {
        "summary": summary,
        "power": power,
        "typec": typec,
        "devices": usb_devs
    }

if __name__ == "__main__":
    import json
    print(json.dumps(get_cables_report(), indent=2))
