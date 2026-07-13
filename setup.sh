#!/bin/bash
# ============================================================
# mousectl setup v2.3 — COMPLETE PARITY REFACTORED
# MousePro NB410H / Clevo L140CU
# ============================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $1"; }
success() { echo -e "${GREEN}[OK]${RESET}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $1"; }
error()   { echo -e "${RED}[ERR]${RESET}   $1"; exit 1; }
step()    { echo -e "\n${BOLD}━━━ $1 ━━━${RESET}"; }

# ─── Root check ───────────────────────────────────────────────────────────────
[ "$EUID" -eq 0 ] || error "Run as root: sudo bash setup.sh"

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
INSTALL_DIR="/opt/mousectl"
KERNEL=$(uname -r)

echo -e "
${CYAN}${BOLD}
  🐭 mousectl setup v2.3
  COMPLETE FEATURE PARITY
${RESET}"

# ─── STEP 0: Preflight ────────────────────────────────────────────────────────
step "Preflight checks"

DMI_PRODUCT=$(cat /sys/class/dmi/id/product_name 2>/dev/null || echo "unknown")
info "Kernel:   $KERNEL"
info "Hardware: $DMI_PRODUCT"

CORE_FILES=("config.py" "msr.py" "sysfs.py" "telemetry.py" "undervolt.py")
UI_FILES=("style.py" "widgets.py")
TAB_FILES=("dashboard.py" "profiles.py" "power.py" "undervolt.py" "fan.py")
SCRIPT_FILES=("apply_boot.py" "fan_daemon.py")

for f in main.py "${CORE_FILES[@]/#/core/}" "${UI_FILES[@]/#/ui/}" "${TAB_FILES[@]/#/ui/tabs/}" "${SCRIPT_FILES[@]/#/scripts/}" "patch-system76-dkms.sh"; do
    [ -f "$SCRIPT_DIR/$f" ] || error "Missing $f — please ensure you are in the project root"
done
success "All modular source files present"

# ─── STEP 1: System dependencies ──────────────────────────────────────────────
step "System dependencies"

apt-get update -q
apt-get install -y msr-tools lm-sensors dkms x11-xserver-utils \
    libxcb-cursor0 libayatana-appindicator3-1 \
    python3-pip \
    linux-headers-$(uname -r) \
    build-essential git stress curl wget -y -q
success "APT packages installed"

info "Installing PySide6..."
pip3 install PySide6 --break-system-packages -q 2>/dev/null || warn "PySide6 install had issues"
success "PySide6 ready"

# ─── STEP 2: system76-dkms patch ──────────────────────────────────────────────
step "Patching system76-dkms for $DMI_PRODUCT"
bash "$SCRIPT_DIR/patch-system76-dkms.sh"

# ─── STEP 3: Install mousectl app ─────────────────────────────────────────────
step "Installing mousectl to $INSTALL_DIR"

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/core"
mkdir -p "$INSTALL_DIR/ui/tabs"
mkdir -p "$INSTALL_DIR/scripts"

cp "$SCRIPT_DIR/main.py"            "$INSTALL_DIR/"
cp "$SCRIPT_DIR/patch-system76-dkms.sh" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/core/"*.py          "$INSTALL_DIR/core/"
cp "$SCRIPT_DIR/ui/"*.py            "$INSTALL_DIR/ui/"
cp "$SCRIPT_DIR/ui/tabs/"*.py       "$INSTALL_DIR/ui/tabs/"
cp "$SCRIPT_DIR/scripts/"*.py       "$INSTALL_DIR/scripts/"
[ -f "$SCRIPT_DIR/scripts/autopatch.sh" ] && cp "$SCRIPT_DIR/scripts/autopatch.sh" "$INSTALL_DIR/scripts/"
[ -f "$SCRIPT_DIR/icon.png" ] && cp "$SCRIPT_DIR/icon.png" "$INSTALL_DIR/icon.png"

# Init files
touch "$INSTALL_DIR/__init__.py"
touch "$INSTALL_DIR/core/__init__.py"
touch "$INSTALL_DIR/ui/__init__.py"
touch "$INSTALL_DIR/ui/tabs/__init__.py"
touch "$INSTALL_DIR/scripts/__init__.py"

chown -R "$REAL_USER:$REAL_USER" "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/patch-system76-dkms.sh"
[ -f "$INSTALL_DIR/scripts/autopatch.sh" ] && chmod +x "$INSTALL_DIR/scripts/autopatch.sh"
success "Files installed and owned by $REAL_USER"

# Main Launcher (V1 Style - no sudo -u which breaks Wayland/Env)
cat > /usr/local/bin/mousectl << LAUNCHEOF
#!/bin/bash
export REAL_HOME="$REAL_HOME"
export HOME="$REAL_HOME"
export QT_QPA_PLATFORMTHEME=gtk3
exec python3 /opt/mousectl/main.py "\$@"
LAUNCHEOF
chmod +x /usr/local/bin/mousectl
success "Launcher created: /usr/local/bin/mousectl"

# Hardware-write helper (shim) - V1 Robust Version
cat > /usr/local/bin/mousectl-hw-write << 'HWEOF'
#!/usr/bin/env python3
import sys, os, struct, glob
from pathlib import Path

def die(msg):
    print(f"[hw-write] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

if os.geteuid() != 0:
    die("Must run as root (via sudo)")

if len(sys.argv) < 2:
    die("Usage: mousectl-hw-write <op> [args...]")

op = sys.argv[1]

if op == 'msr_write':
    if len(sys.argv) < 5: die("msr_write needs cpu msr_hex value_hex")
    cpu, msr_addr, value = int(sys.argv[2]), int(sys.argv[3], 16), int(sys.argv[4], 16)
    dev = f'/dev/cpu/{cpu}/msr'
    if not os.path.exists(dev): die(f"MSR device not found: {dev}")
    fd = os.open(dev, os.O_WRONLY)
    os.lseek(fd, msr_addr, os.SEEK_SET)
    os.write(fd, struct.pack('Q', value))
    os.close(fd)
elif op == 'msr_read':
    if len(sys.argv) < 4: die("msr_read needs cpu msr_hex")
    cpu, msr_addr = int(sys.argv[2]), int(sys.argv[3], 16)
    dev = f'/dev/cpu/{cpu}/msr'
    if not os.path.exists(dev): die(f"MSR device not found: {dev}")
    fd = os.open(dev, os.O_RDONLY)
    os.lseek(fd, msr_addr, os.SEEK_SET)
    val = struct.unpack('Q', os.read(fd, 8))[0]
    os.close(fd)
    print(hex(val))
elif op == 'sysfs_write':
    if len(sys.argv) < 4: die("sysfs_write needs path value")
    path, value = sys.argv[2], sys.argv[3]
    allowed = ('/sys/class/powercap/', '/sys/devices/system/cpu/', '/sys/class/hwmon/', '/sys/module/msr/')
    if not any(path.startswith(p) for p in allowed): die(f"Path not allowed: {path}")
    Path(path).write_text(value)
elif op == 'sysfs_read':
    if len(sys.argv) < 3: die("sysfs_read needs path")
    path = sys.argv[2]
    allowed = ('/sys/class/powercap/', '/sys/devices/system/cpu/', '/sys/class/hwmon/', '/sys/module/msr/')
    if not any(path.startswith(p) for p in allowed): die(f"Path not allowed: {path}")
    print(Path(path).read_text().strip())
else:
    die(f"Unknown operation: {op}")
HWEOF
chmod +x /usr/local/bin/mousectl-hw-write

# Passwordless sudo rule
cat > /etc/sudoers.d/mousectl << SUDOEOF
ALL ALL=(root) NOPASSWD: /usr/local/bin/mousectl-hw-write
SUDOEOF
chmod 440 /etc/sudoers.d/mousectl
success "Hardware shim + sudoers rule installed"

# ─── STEP 4: Permissions (persistent + immediate) ────────────────────────────
step "Granting hardware permissions"

# 4a. Persistent udev rules — survive every reboot
cat > /etc/udev/rules.d/99-mousectl.rules << 'UDEVEOF'
# mousectl: allow normal users to read/write intel-rapl power limits
SUBSYSTEM=="powercap", KERNEL=="intel-rapl:0", ACTION=="add|change", MODE="0666"
SUBSYSTEM=="powercap", KERNEL=="intel-rapl:0:*", ACTION=="add|change", MODE="0666"

# mousectl: allow normal users to read/write MSR registers
KERNEL=="msr[0-9]*", ACTION=="add|change", GROUP="root", MODE="0666"

# mousectl: allow normal users to control fan PWM via hwmon
SUBSYSTEM=="hwmon", ACTION=="add|change", ATTR{name}=="system76",  RUN+="/bin/chmod 666 /sys%p/pwm1 /sys%p/pwm1_enable /sys%p/fan1_input"
SUBSYSTEM=="hwmon", ACTION=="add|change", ATTR{name}=="it5570",    RUN+="/bin/chmod 666 /sys%p/pwm1 /sys%p/pwm1_enable /sys%p/fan1_input"
UDEVEOF
udevadm control --reload-rules && udevadm trigger 2>/dev/null || true
success "Persistent udev rules installed: /etc/udev/rules.d/99-mousectl.rules"

# 4b. Immediate chmod for current session (udev trigger may not catch already-loaded devices)
set +e
for msr in /dev/cpu/*/msr; do [ -e "$msr" ] && chmod 666 "$msr"; done
chmod 666 /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || true
for p in /sys/class/powercap/intel-rapl*/intel-rapl:0/constraint_*_power_limit_uw; do [ -e "$p" ] && chmod 666 "$p"; done
for p in /sys/class/powercap/intel-rapl*/intel-rapl:0/energy_uj; do [ -e "$p" ] && chmod 666 "$p"; done
for f in /sys/class/hwmon/hwmon*/pwm*; do [ -e "$f" ] && chmod 666 "$f"; done
set -e
success "Runtime permissions applied (current session)"

# ─── STEP 5: Persistence & Services ───────────────────────────────────────────
step "Persistence & Background Services"

# 5a. Undervolt & Boot Apply
cat > /usr/local/bin/mousectl-apply-uv << BOOTEOF
#!/bin/bash
# Trigger driver auto-patch check on boot
if [ -f "$INSTALL_DIR/scripts/autopatch.sh" ]; then
    bash "$INSTALL_DIR/scripts/autopatch.sh"
fi

export REAL_HOME="$REAL_HOME"
export HOME="$REAL_HOME"
python3 $INSTALL_DIR/scripts/apply_boot.py
BOOTEOF
chmod +x /usr/local/bin/mousectl-apply-uv

cat > /etc/systemd/system/mousectl-undervolt.service << SVCEOF
[Unit]
Description=mousectl Undervolt/TDP (Boot)
After=multi-user.target system76-power.service power-profiles-daemon.service tlp.service
ConditionPathExists=$REAL_HOME/.config/mousectl/config.json

[Service]
Type=oneshot
Environment="REAL_HOME=$REAL_HOME"
ExecStartPre=/sbin/modprobe msr
ExecStart=/usr/local/bin/mousectl-apply-uv
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SVCEOF

# 5b. Fan Daemon Service (v1.0 Parity)
cat > /etc/systemd/system/mousectl-fan.service << FANEOF
[Unit]
Description=mousectl Fan Curve Daemon
After=multi-user.target system76-power.service power-profiles-daemon.service tlp.service
ConditionPathExists=$REAL_HOME/.config/mousectl/config.json

[Service]
Type=simple
Environment="REAL_HOME=$REAL_HOME"
ExecStart=/usr/bin/python3 $INSTALL_DIR/scripts/fan_daemon.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
FANEOF

systemctl daemon-reload
systemctl enable mousectl-undervolt.service > /dev/null 2>&1
systemctl enable mousectl-fan.service > /dev/null 2>&1
success "Background services enabled"

# 5c. APT Auto-patch hook (survives system updates)
cat > /etc/apt/apt.conf.d/99-mousectl-autopatch << APTEOF
DPkg::Post-Invoke {
    "if [ -f /opt/mousectl/scripts/autopatch.sh ]; then bash /opt/mousectl/scripts/autopatch.sh; fi";
};
APTEOF
success "APT auto-patch hook installed: /etc/apt/apt.conf.d/99-mousectl-autopatch"

# Sleep hook
cat > /usr/lib/systemd/system-sleep/mousectl-resume << EOF
#!/bin/bash
if [ "\$1" = "post" ]; then
    /usr/local/bin/mousectl-apply-uv
    systemctl restart mousectl-fan.service
fi
EOF
chmod +x /usr/lib/systemd/system-sleep/mousectl-resume
success "Sleep hook installed"

# ─── STEP 6: UI & Desktop Entry ───────────────────────────────────────────────
step "UI Integration & Icon"

# Icon Redundancy
[ -d "$REAL_HOME/.local/share/icons/hicolor/256x256/apps" ] || mkdir -p "$REAL_HOME/.local/share/icons/hicolor/256x256/apps"
if [ -f "$SCRIPT_DIR/icon.png" ]; then
    cp "$SCRIPT_DIR/icon.png" "$REAL_HOME/.local/share/icons/hicolor/256x256/apps/mousectl.png"
    cp "$SCRIPT_DIR/icon.png" "/usr/share/pixmaps/mousectl.png"
    chown "$REAL_USER:$REAL_USER" "$REAL_HOME/.local/share/icons/hicolor/256x256/apps/mousectl.png"
fi

mkdir -p "$REAL_HOME/.local/share/applications"
cat > "$REAL_HOME/.local/share/applications/mousectl.desktop" << DESKTOPEOF
[Desktop Entry]
Name=mousectl
Comment=NB410H Hardware Control Center
Exec=/usr/local/bin/mousectl
Icon=mousectl
Terminal=false
Type=Application
Categories=System;Settings;HardwareSettings;
Keywords=fan;undervolt;power;temperature;cooling;
StartupNotify=true
DESKTOPEOF
chown "$REAL_USER:$REAL_USER" "$REAL_HOME/.local/share/applications/mousectl.desktop"
update-desktop-database "$REAL_HOME/.local/share/applications" 2>/dev/null || true
success "Desktop entry created and database refreshed"

# ─── STEP 7: Permissions Cleanup ─────────────────────────────────────────────
step "Finalizing permissions"
if [ -d "$REAL_HOME/.config/mousectl" ]; then
    chown -R $REAL_USER:$REAL_USER "$REAL_HOME/.config/mousectl"
fi

# ─── STEP 8: Sensors ──────────────────────────────────────────────────────────
step "Sensors configuration"
sensors-detect --auto > /dev/null 2>&1 || true
success "lm-sensors auto-detected"

# ─── STEP 9: Cleanup ──────────────────────────────────────────────────────────
step "Cleaning up temporary files"
# Remove pycache from installation and script directories
find "$INSTALL_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Vacuum logs to keep them fresh
journalctl --vacuum-time=1s --unit=mousectl-undervolt > /dev/null 2>&1 || true
journalctl --vacuum-time=1s --unit=mousectl-fan > /dev/null 2>&1 || true

success "Cleanup complete"

# ─── Summary ──────────────────────────────────────────────────────────────────
echo -e "
${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🐭 mousectl v2.3 — SETUP COMPLETE (V1 PARITY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}

${BOLD}Installed:${RESET}
  ✅  Permissions (666) granted for low-latency control
  ✅  Background Fan Daemon enabled (always cooling)
  ✅  Undervolt/TDP Persistence enabled
  ✅  Desktop Entry & App Icon restored
  ✅  Hardware Write Shim + Sudoers rule

${BOLD}Quick Start:${RESET}
  1. Run 'mousectl' to configure your settings.
  2. Enable 'Apply on Boot' in tabs to persist.
"
