from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFrame)
from PySide6.QtCore import Qt, QTimer
from ui.style import T
from ui.widgets import status_label, set_status, StatCard
import core.cables as cables

class CablesTab(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # WhatCable Plain-English Header Summary Banner
        self.info_banner = QLabel("🔌 WhatCable Diagnostic Summary: Scanning connected cables and power supply...")
        self.info_banner.setWordWrap(True)
        self.info_banner.setStyleSheet(
            f"color:{T['accent']}; font-size:11px; font-weight:bold; "
            f"border:1px solid {T['border']}; border-radius:6px; padding:8px 12px; "
            f"background:{T['surface2']};"
        )
        main_layout.addWidget(self.info_banner)

        # Power & Charging Status Cards Row
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(8)
        
        self.card_ac      = StatCard('CHARGER / AC',  'Type',  T['accent'])
        self.card_bat     = StatCard('BATTERY LEVEL', '%',     T['green'])
        self.card_health  = StatCard('BAT HEALTH',    '%',     T['accent2'])
        self.card_voltage = StatCard('VOLTAGE / AMPS', 'V / A', T['warn'])
        
        for c in [self.card_ac, self.card_bat, self.card_health, self.card_voltage]:
            c.setMinimumHeight(80)
            cards_layout.addWidget(c)
        main_layout.addLayout(cards_layout)

        # USB Devices Table Group
        usb_group = QGroupBox("CONNECTED USB DEVICES, HUBS & CABLES")
        usb_layout = QVBoxLayout(usb_group)
        usb_layout.setSpacing(8)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Device / Product Name", "Negotiated Speed", "USB Protocol", "Max Power Draw", "VID:PID", "Bus / Dev"
        ])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        
        self.table.setStyleSheet(
            f"QTableWidget {{ background:{T['surface']}; color:{T['text']}; gridline-color:{T['border']}; border:1px solid {T['border']}; border-radius:6px; font-size:11px; }}"
            f"QHeaderView::section {{ background:{T['surface2']}; color:{T['accent']}; font-weight:bold; border:none; padding:4px 8px; }}"
        )
        usb_layout.addWidget(self.table)
        main_layout.addWidget(usb_group)

        # Controls & Status
        ctrl = QHBoxLayout()
        btn_refresh = QPushButton("↺ Refresh Cables & USB Data")
        btn_refresh.setObjectName("primary")
        btn_refresh.clicked.connect(self.refresh_data)
        ctrl.addWidget(btn_refresh)
        ctrl.addStretch()
        main_layout.addLayout(ctrl)

        self.status = status_label()
        main_layout.addWidget(self.status)

        # Auto refresh on tab open
        QTimer.singleShot(100, self.refresh_data)

    def refresh_data(self):
        try:
            report = cables.get_cables_report()
            
            # Update Banner
            self.info_banner.setText(f" WhatCable Summary: {report['summary']}")

            # Update Power Cards
            p = report['power']
            ac_str = f"{p['ac_type']}" if p['ac_online'] else "Disconnected"
            self.card_ac.set_value(ac_str)
            self.card_bat.set_value(f"{p['battery_capacity']}% ({p['battery_status']})")
            self.card_health.set_value(f"{p['battery_health_pct']}%")
            self.card_voltage.set_value(f"{p['battery_voltage_v']}V / {p['battery_current_a']}A")

            # Update USB Table
            devs = report['devices']
            self.table.setRowCount(len(devs))
            for i, d in enumerate(devs):
                name_item = QTableWidgetItem(d['name'])
                speed_item = QTableWidgetItem(d['speed_str'])
                version_item = QTableWidgetItem(d['version'])
                power_item = QTableWidgetItem(d['max_power'] or "—")
                vidpid_item = QTableWidgetItem(f"{d['vendor_id']}:{d['product_id']}" if d['vendor_id'] else "—")
                bus_item = QTableWidgetItem(f"Bus {d['busnum']} Dev {d['devnum']}" if d['busnum'] else "—")

                # Alignment
                for item in (name_item, speed_item, version_item, power_item, vidpid_item, bus_item):
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

                self.table.setItem(i, 0, name_item)
                self.table.setItem(i, 1, speed_item)
                self.table.setItem(i, 2, version_item)
                self.table.setItem(i, 3, power_item)
                self.table.setItem(i, 4, vidpid_item)
                self.table.setItem(i, 5, bus_item)

            set_status(self.status, f"Refreshed USB & cable telemetry ({len(devs)} devices detected).", "info")
        except Exception as e:
            set_status(self.status, f"Failed to refresh cables data: {str(e)}", "err")
