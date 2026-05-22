# 🐭 mousectl v2.3
**Deep Hardware Control & Real-Time Performance Diagnostics for MousePro NB410H / Clevo L140CU on Linux**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Platform: Pop!\_OS](https://img.shields.io/badge/Platform-Pop!_OS%2024.04-orange.svg)](https://system76.com/pop)
[![Display: Wayland](https://img.shields.io/badge/Display-Wayland-blue.svg)](https://wayland.freedesktop.org/)

`mousectl` bridges System76 hardware features with rebadged Clevo chassis. It gives you full control over fan curves, CPU voltage offsets, and power limits — from a beautiful, modern PySide6 GUI with a system tray icon, real-time diagnostic menu, and background daemon integration.

---

## ✨ Features

| Feature | Details |
| :--- | :--- |
| **🚀 Zero-Latency Telemetry** | High-performance sysfs path caching eliminates redundant file-system traversals. Reads temperatures, fan speeds, CPU power (via Intel RAPL energy counter delta), and iGPU stats with virtually zero CPU overhead. |
| **📊 Advanced Tray Menu** | Right-click the system tray icon for a premium diagnostic panel displaying CPU temperature/wattage, CPU usage%, Fan RPM, RAM usage, iGPU frequencies/utilization, Network upload/download speeds, Disk read/write rates, and Battery metrics. |
| **📈 Dynamic Graph Scaling** | Live rolling graphs for core temperature, CPU power, and fan speed featuring a hybrid auto-scaling grid that expands or compresses dynamically to display data with optimal visual resolution. |
| **🌪 Live Fan Duty Tracking** | Dynamically reads and displays the physical hardware fan duty cycle percentage (`pwm1`) rather than defaulting to hardcoded UI states. |
| **⚖️ Conflict-Free Daemon** | Syncs seamlessly with the `mousectl-fan.service` background systemd service. Detects active background daemons automatically and stops local UI worker threads to prevent conflicts, updating the status card in real-time. |
| **⚡ Linked Undervolting** | Safety-first core voltage plane offsets via MSR `0x150` with an option to link **Core & Cache** offsets to synchronize your undervolt profile safely. Also supports GPU and Uncore offsets. |
| **🔋 TDP Management** | PL1 (Long-term) and PL2 (Short-term) power limit controls with customized performance presets (Quiet, Balanced, Performance, Max) matching your active power profiles. |
| **🛡️ Safe Shutdown** | Graceful application exit sequence explicitly terminates manual overrides, joining worker threads cleanly and returning the physical fan immediately to BIOS automatic control. |
| **🔒 Security-First Shim** | Hardware writes go through a privileged helper (`mousectl-hw-write`). The graphical interface runs entirely as a normal unprivileged user. |

---

## 🏗️ Architecture

The codebase has been refactored for strict separation of concerns, high-performance querying, and acoustic/safety comfort.

```
mousectl/
├── main.py               # App entry point, tray icon layout, telemetry hooks
├── core/
│   ├── sysfs.py          # Cached hwmon lookups, Intel RAPL power cap reader, power profiles, and daemon detection
│   ├── telemetry.py      # Background PowerSampler QThread (RAM, CPU frequencies, network & disk metrics, iGPU monitors)
│   ├── msr.py            # MSR read/write operations, Turbo Boost/Ratio limits, and driver check
│   ├── undervolt.py      # MSR 0x150 undervolt encoder/decoder functions
│   └── config.py         # Thread-safe JSON configuration manager
├── ui/
│   ├── style.py          # Color system palette (vibrant dark mode tokens & layout rules)
│   ├── widgets.py        # StatCard, TempGraph (hybrid auto-scaler), FanCurveWidget (drag-to-edit canvas)
│   └── tabs/
│       ├── dashboard.py  # Live stats grid, core frequency list, and system specs
│       ├── power.py      # Long & short TDP sliders, power profile selectors, and turbo ratio limit spinboxes
│       ├── undervolt.py  # Voltage plane offset sliders with optional Core & Cache slider locking
│       └── fan.py        # Fan curve editor, preset selectors, manual duty locking, and daemon status cards
└── setup.sh              # Full system installer: dependencies, dkms driver, privileged shim, systemd services
```

---

## 🚀 Installation & Setup

### System Requirements
* **OS:** Pop!\_OS 24.04 LTS (Wayland / X11). Other modern Debian/Ubuntu-based distributions featuring the `system76-dkms` kernel module are fully supported.
* **BIOS:** Secure Boot must be **disabled** (`F2` at startup -> Security tab) to load the `msr` kernel module.
* **Kernel:** The model-specific register driver (`msr`) must be enabled and loadable (`modprobe msr`).

### Quick Install

Clone and run the automated installation script:
```bash
git clone https://github.com/DuyPrX/mousectl.git
cd mousectl
sudo bash setup.sh
```

**What the installer does:**
1. Installs necessary Python and system dependencies (`PySide6`, `python3-pip`).
2. Configures and registers the `system76-dkms` kernel module patch.
3. Installs the privileged `mousectl-hw-write` security shim.
4. Automatically generates and enables the `mousectl-undervolt.service` and `mousectl-fan.service` systemd services.
5. Setups correct file ownership rules so the graphical interface runs entirely without `sudo` privileges.
6. Cleans up temporary installation files and build cache automatically.

> 💡 **Recommendation:** Reboot your machine after installation to finalize systemd services and apply the kernel driver patch.

---

## 🖱️ Usage Guidelines

### Execution
Run the app via terminal or search for `mousectl` in your desktop environment's launcher:
```bash
mousectl
```
Closing the main window will automatically minimize the application to the system tray so monitoring remains active in the background.

### Premium Diagnostics System Tray
* **Left-click or Double-click** to instantly restore the main dashboard window.
* **Right-click** to access the premium system telemetry diagnostics overlay:
  * 🌡️ **CPU:** Package temperature and live power draw in watts
  * 📊 **Usage:** Aggregate CPU usage percentage across all cores
  * 🌪️ **Fan:** Live rotation speed in RPM
  * 💾 **RAM:** Active usage alongside physical capacity limit
  * 🎮 **iGPU:** Core clock frequencies and utilization percentage
  * 🌐 **Net:** Upstream and downstream physical interface bandwidth speeds
  * 💽 **Disk:** Read and write speed rates across block storage drives
  * 🔌 **Battery:** Percentage level, status (Charging/Discharging), and exact real-time wattage draw
  * ⚡ **Power Profile:** Checkable submenu to toggle system-wide performance profiles (Battery / Balanced / Performance)
  * **Exit App:** Triggers safety routine, shuts down local worker loops, resets hardware fan controls to BIOS, and terminates the process.

---

## ⚙️ Configuration & Customization

All configurations are stored in JSON format inside `~/.config/mousectl/config.json`. The application automatically monitors and reloads this configuration when changes occur:

```json
{
  "fan_curve": [[30,30],[45,40],[60,55],[70,70],[80,85],[90,100]],
  "fan_curve_active": true,
  "power": {
    "profile": "balanced",
    "long": 15,
    "short": 25,
    "apply_on_boot": false
  },
  "undervolt": {
    "core": -80,
    "cache": -80,
    "gpu": 0,
    "uncore": 0,
    "apply_on_boot": false
  },
  "telemetry": {
    "interval": 1.5
  }
}
```

### Telemetry & Safety Constants
* **`telemetry.interval` (default: 1.5):** Dictates how frequently (in seconds) the background telemetry thread monitors temperatures, frequencies, power draw, and physical devices. Can be configured lower for ultra-responsiveness, or higher to minimize CPU overhead.
* **Acoustic Comfort Step-Ramping:** The fan daemon transitions speeds in small `1-2%` steps per tick using a rolling `10-sample` temperature average. This prevents irritating "fan pulsing" sounds during quick CPU spikes.

---

## 🌿 High-Ambient Tuning (Vietnam & Tropical Climates)
Specifically optimized for high-ambient room temperatures (30°C+):
* **🌙 Silent Preset:** Calibrated for absolute acoustic comfort inside air-conditioned rooms or offices.
* **⚖️ Balanced Preset:** Standard daily-driver profile balancing system performance and fan acoustics.
* **🔥 Performance Preset:** Aggressive cooling response to prevent thermal throttling in warm non-AC environments.
* **🎯 Thermal Design:** Frequency-smoothing parameters specifically tuned to perform optimally with premium phase-change materials like Honeywell PTM7950.

---

## 📜 Credits & Licensing

* **Drivers:** [System76 Open Firmware / system76-dkms](https://github.com/pop-os/system76-dkms)
* **Chassis:** Clevo L140CU (Lemur Pro / lemp9 base)
* **License:** [MIT License](https://opensource.org/licenses/MIT)

*Built with ❤️ in Ho Chi Minh City, Vietnam 🇻🇳*
