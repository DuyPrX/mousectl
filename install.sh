#!/bin/bash
# ============================================================
# mousectl install script (Robust Minimal)
# ============================================================

set -e
echo "🐭 Installing mousectl (Modular)..."

# Install critical dependencies for launch and tray
sudo apt update -q
sudo apt install python3-pip msr-tools dkms libxcb-cursor0 libayatana-appindicator3-1 -y -q
sudo pip3 install PySide6 --break-system-packages -q 2>/dev/null || true

# Directory structure
INSTALL_DIR="/opt/mousectl"
sudo rm -rf "$INSTALL_DIR"
sudo mkdir -p "$INSTALL_DIR/core"
sudo mkdir -p "$INSTALL_DIR/ui/tabs"
sudo mkdir -p "$INSTALL_DIR/scripts"

# Copy modular files
sudo cp main.py "$INSTALL_DIR/"
sudo cp core/*.py "$INSTALL_DIR/core/"
sudo cp ui/*.py "$INSTALL_DIR/ui/"
sudo cp ui/tabs/*.py "$INSTALL_DIR/ui/tabs/"
sudo cp scripts/*.py "$INSTALL_DIR/scripts/"
[ -f icon.png ] && sudo cp icon.png "$INSTALL_DIR/"

# Init files
sudo touch "$INSTALL_DIR/__init__.py"
sudo touch "$INSTALL_DIR/core/__init__.py"
sudo touch "$INSTALL_DIR/ui/__init__.py"
sudo touch "$INSTALL_DIR/ui/tabs/__init__.py"
sudo touch "$INSTALL_DIR/scripts/__init__.py"

# Create launcher wrapper
sudo tee /usr/local/bin/mousectl > /dev/null << EOF
#!/bin/bash
export QT_QPA_PLATFORMTHEME=gtk3
exec python3 $INSTALL_DIR/main.py "\$@"
EOF
sudo chmod +x /usr/local/bin/mousectl

echo "✅ mousectl installation complete!"
echo "⚠️  NOTE: For full persistence, icon integration, and hardware permissions, run 'sudo bash setup.sh' instead."
echo "Run with:  mousectl"
