#!/bin/bash
# ============================================================
# mousectl system76-dkms patch
# Patches system76-dkms for non-System76 Clevo hardware
# MousePro NB410H / Clevo L140CU / Pop!_OS
#
# Usage: sudo bash patch-system76-dkms.sh
# Revert: sudo apt install --reinstall system76-dkms -y
# ============================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $1"; }
success() { echo -e "${GREEN}[OK]${RESET}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $1"; }
error()   { echo -e "${RED}[ERR]${RESET}   $1"; exit 1; }
step()    { echo -e "\n${BOLD}━━━ $1 ━━━${RESET}"; }

[ "$EUID" -eq 0 ] || error "Run as root: sudo bash patch-system76-dkms.sh"

echo -e "${CYAN}${BOLD}
  🔧 system76-dkms patch v5
  For non-System76 Clevo hardware
${RESET}"

# ─── Preflight ────────────────────────────────────────────────────────────────
step "Preflight checks"

KERNEL=$(uname -r)
DMI_VENDOR=$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null || echo "unknown")
DMI_PRODUCT=$(cat /sys/class/dmi/id/product_name 2>/dev/null || echo "unknown")

info "Kernel:   $KERNEL"
info "Vendor:   $DMI_VENDOR"
info "Product:  $DMI_PRODUCT"

[ -d "/lib/modules/$KERNEL/build" ] \
    || error "Kernel headers missing — run: sudo apt install linux-headers-$(uname -r)"

WMI_OK=true
ls /sys/bus/wmi/devices/ 2>/dev/null | grep -q "ABBC0F6B" || WMI_OK=false
ls /sys/bus/wmi/devices/ 2>/dev/null | grep -q "ABBC0F6D" || WMI_OK=false
[ "$WMI_OK" = true ] \
    && success "WMI GUIDs present (ABBC0F6B + ABBC0F6D)" \
    || warn "WMI GUIDs not found"

# ─── Clean ────────────────────────────────────────────────────────────────────
step "Cleaning previous attempts"

dkms remove system76-mousepro/1.0 --all 2>/dev/null || true
rm -rf /usr/src/system76-mousepro-1.0
rm -rf /tmp/system76-patch-*
success "Clean"

# ─── Dependencies ─────────────────────────────────────────────────────────────
step "Installing dependencies"

if dpkg -s git dkms build-essential linux-headers-$(uname -r) >/dev/null 2>&1; then
    info "Dependencies already installed (dpkg-checked)"
else
    # Only run apt-get if any dependency is missing
    apt-get update -q || true
    apt-get install -y -qq git dkms build-essential linux-headers-$(uname -r) > /dev/null 2>&1
fi
success "Dependencies ready"

# ─── Clone ────────────────────────────────────────────────────────────────────
step "Cloning system76-dkms"

WORK_DIR=$(mktemp -d /tmp/system76-patch-XXXXXX)
cd "$WORK_DIR"
git clone --quiet https://github.com/pop-os/system76-dkms.git
cd system76-dkms

[ -f "src/system76.c" ] || error "src/system76.c not found"

info "Repo files:"
find . -name "*.c" -o -name "Makefile" -o -name "dkms.conf" 2>/dev/null | sort | sed 's/^/  /'

success "Cloned"

# ─── Patch ────────────────────────────────────────────────────────────────────
step "Applying DMI patch"

python3 - <<'PYEOF'
import sys

with open('src/system76.c', 'r') as f:
    lines = f.readlines()

vendor  = open('/sys/class/dmi/id/sys_vendor').read().strip()
product = open('/sys/class/dmi/id/product_name').read().strip()

print(f"  Patching for: {vendor} / {product}")

# Build the macro lines using chr(92) for backslash so the heredoc quoting
# mode cannot corrupt them — no shell expansion touches a quoted <<'PYEOF'.
bs = chr(92)
new_macro_lines = [
    "\n",
    f"#define DMI_TABLE_CLEVO(VENDOR, PRODUCT, DATA) {{ {bs}\n",
    f"\t.ident = VENDOR \" \" PRODUCT, {bs}\n",
    f"\t.matches = {{ {bs}\n",
    f"\t\tDMI_MATCH(DMI_SYS_VENDOR, VENDOR), {bs}\n",
    f"\t\tDMI_MATCH(DMI_PRODUCT_NAME, PRODUCT), {bs}\n",
    f"\t}}, {bs}\n",
    f"\t.callback = s76_dmi_matched, {bs}\n",
    f"\t.driver_data = (void *)(uint64_t)(DATA), {bs}\n",
    f"}}\n",
]

new_entry = (
    f'\tDMI_TABLE_CLEVO("{vendor}", "{product}",'
    ' DRIVER_AP_KEY | DRIVER_HWMON | DRIVER_KB_LED_WMI),\n'
)

result = []
inserted_macro = False
inserted_entry = False
in_dmi_table_macro = False

for line in lines:
    if line.startswith('#define DMI_TABLE('):
        in_dmi_table_macro = True

    # End of the DMI_TABLE macro block: a lone "}" line (no trailing backslash)
    if in_dmi_table_macro and line.strip() == '}' and not inserted_macro:
        result.append(line)
        result.extend(new_macro_lines)
        inserted_macro = True
        in_dmi_table_macro = False
        continue

    result.append(line)

    # Insert Clevo entry as first entry in the table, before bonw13
    if 'DMI_TABLE_LEGACY("bonw13"' in line and not inserted_entry:
        result.insert(len(result) - 1, new_entry)
        inserted_entry = True

if not inserted_macro:
    sys.exit("ERROR: closing } of DMI_TABLE macro not found — check source structure")
if not inserted_entry:
    sys.exit("ERROR: bonw13 entry not found in dmi_table")

with open('src/system76.c', 'w') as f:
    f.writelines(result)

print("  Done!")
PYEOF

success "Patch applied"

# ─── Strip unused components ──────────────────────────────────────────────────
step "Stripping unused components (nv_hda / ap-led / OLED)"

python3 - <<'STRIPEOF'
import re

with open('src/system76.c', 'r') as f:
    lines = f.readlines()

removed = []
result  = []
i = 0

while i < len(lines):
    line = lines[i]

    # 1. Remove #include "nv_hda.c"
    if re.search(r'#\s*include\s*"nv_hda\.c"', line):
        removed.append('#include "nv_hda.c"')
        i += 1
        continue

    # 2. Remove  err = nv_hda_init(...);  and its following if-block
    #    Uses brace counting so nested () like unlikely(err) are not an issue
    if 'nv_hda_init' in line:
        removed.append('nv_hda_init() call')
        i += 1
        # Skip following blank lines then eat a brace-block if present
        j = i
        while j < len(lines) and lines[j].strip() == '':
            j += 1
        if j < len(lines) and '{' in lines[j]:
            depth = 0
            while i < len(lines):
                for ch in lines[i]:
                    if ch == '{': depth += 1
                    elif ch == '}': depth -= 1
                i += 1
                if depth <= 0:
                    break
        continue

    # 3. Remove  nv_hda_exit();
    if 'nv_hda_exit' in line:
        removed.append('nv_hda_exit() call')
        i += 1
        continue

    # 4. Strip DRIVER_OLED from the DRIVER_INPUT composite #define only.
    #    The case 0xD7 / ap_led_* blocks are kept — they are all guarded by
    #    flags (DRIVER_OLED, DRIVER_AP_LED) not set for our DMI entry, so
    #    they compile cleanly but never execute at runtime.
    if 'DRIVER_INPUT' in line and 'DRIVER_OLED' in line:
        line = re.sub(r'\|\s*DRIVER_OLED\b', '', line)
        line = re.sub(r'\bDRIVER_OLED\s*\|', '', line)
        removed.append('DRIVER_OLED from DRIVER_INPUT define')

    result.append(line)
    i += 1

if not removed:
    print("  WARNING: Nothing removed — check source structure hasn't changed")
else:
    for r in removed:
        print(f"  - Removed: {r}")

# Sanity check: no nv_hda references survive
leftover = [l.strip() for l in result if 'nv_hda' in l]
if leftover:
    print(f"  ERROR: {len(leftover)} nv_hda reference(s) still present:")
    for r in leftover: print(f"    {r}")
    raise SystemExit(1)
else:
    print("  OK: no nv_hda references remain")

with open('src/system76.c', 'w') as f:
    f.writelines(result)
STRIPEOF

success "Unused components stripped"

# ─── Build ────────────────────────────────────────────────────────────────────
step "Building kernel module"

make -C /lib/modules/$(uname -r)/build M=$(pwd)/src modules > /tmp/s76-build.log 2>&1 \
    || { tail -20 /tmp/s76-build.log; error "Build failed — see /tmp/s76-build.log"; }

[ -f "src/system76.ko" ] || error ".ko not found after build"
success "Built: src/system76.ko"

# ─── Install directly ─────────────────────────────────────────────────────────
step "Installing module"

install -D src/system76.ko /lib/modules/$(uname -r)/updates/dkms/system76.ko
depmod -a
success "Installed to /lib/modules/$KERNEL/updates/dkms/"

# ─── DKMS registration ────────────────────────────────────────────────────────
step "Registering with DKMS"

DKMS_NAME="system76-mousepro"
DKMS_VER="1.0"
DKMS_SRC="/usr/src/${DKMS_NAME}-${DKMS_VER}"

mkdir -p "$DKMS_SRC/src"

# Mirror the upstream two-level build structure exactly:
#   DKMS_SRC/Kbuild       -> obj-y += src/
#   DKMS_SRC/Makefile     -> delegates to kernel build with M=$PWD
#   DKMS_SRC/src/Kbuild   -> obj-m += system76.o
#   DKMS_SRC/src/*.c      -> system76.c #includes the others at preprocessor level
cp src/system76.c "$DKMS_SRC/src/"
cp src/hwmon.c    "$DKMS_SRC/src/"
# ap-led.c: kept — calls are guarded by DRIVER_AP_LED (not in our DMI entry), compiles but never runs
# nv_hda.c: excluded — its unconditional calls were stripped from system76.c
for f in src/ap-led.c src/input.c src/kb-led.c; do
    [ -f "$f" ] && cp "$f" "$DKMS_SRC/src/" || true
done

# Root Kbuild: descend into src/
printf 'obj-y += src/\n' > "$DKMS_SRC/Kbuild"

# Root Makefile (used by direct make invocations; DKMS uses MAKE[0] below)
printf 'KERNEL_DIR = /lib/modules/$(shell uname -r)/build\nall:\n\t$(MAKE) -C "$(KERNEL_DIR)" M="$(PWD)" modules\nclean:\n\t$(MAKE) -C "$(KERNEL_DIR)" M="$(PWD)" clean\n' > "$DKMS_SRC/Makefile"

# src/Kbuild: declare the module
printf 'obj-m += system76.o\n' > "$DKMS_SRC/src/Kbuild"

# dkms.conf:
#   M= points to DKMS_SRC root so the kernel build descends via
#   Kbuild -> src/Kbuild, matching the upstream repo layout.
#   BUILT_MODULE_LOCATION[0]="src" tells DKMS where the kernel places
#   system76.ko (next to the Kbuild that declared obj-m).
cat > "$DKMS_SRC/dkms.conf" << DKMSEOF
PACKAGE_NAME="${DKMS_NAME}"
PACKAGE_VERSION="${DKMS_VER}"
BUILT_MODULE_NAME[0]="system76"
BUILT_MODULE_LOCATION[0]="src"
DEST_MODULE_LOCATION[0]="/updates/dkms"
MAKE[0]="make -C /lib/modules/\${kernelver}/build M=\${dkms_tree}/${DKMS_NAME}/${DKMS_VER}/source modules"
CLEAN="make -C /lib/modules/\${kernelver}/build M=\${dkms_tree}/${DKMS_NAME}/${DKMS_VER}/source clean"
AUTOINSTALL="yes"
DKMSEOF

info "DKMS source:"
find "$DKMS_SRC" | sort | sed 's/^/  /'

dkms add -m "$DKMS_NAME" -v "$DKMS_VER" > /dev/null 2>&1 && success "dkms add OK" || warn "dkms add issues"

# dkms build symlinks source -> /usr/src/..., so M=.../source/src resolves back
# into /usr/src/ and the kernel writes system76.ko there instead of into DKMS's
# build staging area. We run the build anyway (it produces the .ko), then
# manually stage it into the DKMS build tree before dkms install.
dkms build -m "$DKMS_NAME" -v "$DKMS_VER" > /tmp/s76-dkms.log 2>&1 || true

KO_SRC="$DKMS_SRC/src/system76.ko"
KO_STAGE="/var/lib/dkms/${DKMS_NAME}/${DKMS_VER}/${KERNEL}/x86_64/module"

if [ -f "$KO_SRC" ]; then
    mkdir -p "$KO_STAGE"
    cp "$KO_SRC" "$KO_STAGE/system76.ko"
    success "dkms build OK (staged manually)"
else
    warn "dkms build failed — no .ko produced"
    tail -20 /tmp/s76-dkms.log
    warn "Full log: /tmp/s76-dkms.log"
fi

dkms install -m "$DKMS_NAME" -v "$DKMS_VER" --force > /dev/null 2>&1 && success "dkms install OK" || warn "dkms install issues"

echo "system76" > /etc/modules-load.d/system76-mousepro.conf
success "Auto-load on boot configured"

# ─── Load & verify ────────────────────────────────────────────────────────────
step "Loading module"

if lsmod | grep -q "^system76"; then
    modprobe -r system76 2>/dev/null && info "Unloaded old system76" || warn "Could not unload — will reload anyway"
    sleep 1
fi
modprobe system76 2>/dev/null && success "Loaded!" || warn "Try reboot if this fails"
sleep 1

# ─── Result ───────────────────────────────────────────────────────────────────
step "Result"

DMESG=$(dmesg | grep -i "system76" | tail -5)
echo "$DMESG" | sed 's/^/  /'

if echo "$DMESG" | grep -qi "found"; then
    success "🎉 Hardware recognized!"
    RPM=$(cat /sys/class/hwmon/hwmon*/fan1_input 2>/dev/null | head -1)
    [ -n "$RPM" ] && info "Fan RPM: $RPM RPM" || true
else
    warn "Check after reboot: sudo dmesg | grep system76"
fi

echo -e "\n${GREEN}${BOLD}Done!${RESET}"
echo "Revert: sudo apt install --reinstall system76-dkms -y"

cd /; rm -rf "$WORK_DIR"
