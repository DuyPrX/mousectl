#!/bin/bash
# Self-healing check for mousectl system76 driver
# Runs on boot and after APT package operations to restore the custom DMI driver if overwritten.

ACTIVE_DRIVER=false
for name_path in /sys/class/hwmon/hwmon*/name; do
    if [ -f "$name_path" ] && [ "$(cat "$name_path")" = "system76" ]; then
        ACTIVE_DRIVER=true
        break
    fi
done

if [ "$ACTIVE_DRIVER" = "false" ]; then
    echo "[mousectl-autopatch] Custom system76 driver is not active. Attempting self-healing patch..." | logger -t mousectl-autopatch
    if [ -f /opt/mousectl/patch-system76-dkms.sh ]; then
        # Run patch script and log output
        bash /opt/mousectl/patch-system76-dkms.sh >> /var/log/mousectl-autopatch.log 2>&1
        
        # Restart services to apply settings
        systemctl restart mousectl-fan
        systemctl restart mousectl-undervolt
        echo "[mousectl-autopatch] Self-healing complete. Services restarted." | logger -t mousectl-autopatch
    else
        echo "[mousectl-autopatch] ERROR: /opt/mousectl/patch-system76-dkms.sh not found!" | logger -t mousectl-autopatch
    fi
else
    exit 0
fi
