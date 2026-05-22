# ─── Theme ────────────────────────────────────────────────────────────────────

T = {
    'bg':       '#080b10',
    'surface':  '#0e1219',
    'surface2': '#141a26',
    'border':   '#1c2438',
    'accent':   '#00d4ff',
    'accent2':  '#ff6b35',
    'green':    '#00e5a0',
    'warn':     '#ffb830',
    'danger':   '#ff3355',
    'text':     '#dce8ff',
    'muted':    '#3d4d6a',
    'muted2':   '#6a7a9a',
}

SS = f"""
QMainWindow, QWidget {{
    background: {T['bg']};
    color: {T['text']};
    font-family: 'JetBrains Mono', 'Fira Mono', 'Ubuntu Mono', monospace;
    font-size: 12px;
}}
QTabWidget::pane {{
    border: 1px solid {T['border']};
    border-radius: 8px;
    background: {T['surface']};
}}
QTabBar::tab {{
    background: {T['surface2']};
    color: {T['muted2']};
    padding: 9px 22px;
    margin-right: 2px;
    border-radius: 6px 6px 0 0;
    font-weight: bold;
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
QTabBar::tab:selected {{
    background: {T['surface']};
    color: {T['accent']};
    border-bottom: 2px solid {T['accent']};
}}
QTabBar::tab:hover:!selected {{ color: {T['text']}; background: {T['border']}; }}
QGroupBox {{
    border: 1px solid {T['border']};
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px;
    font-weight: bold;
    font-size: 10px;
    letter-spacing: 1.5px;
    color: {T['muted2']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    top: -1px;
    padding: 0 6px;
    background: {T['surface']};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {T['border']};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {T['accent']};
    width: 14px; height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{ background: {T['accent']}; border-radius: 2px; }}
QPushButton {{
    background: {T['surface2']};
    border: 1px solid {T['border']};
    border-radius: 6px;
    padding: 7px 16px;
    color: {T['text']};
    font-weight: bold;
    font-size: 11px;
}}
QPushButton:hover {{ background: {T['border']}; border-color: {T['muted2']}; }}
QPushButton:pressed {{ background: {T['bg']}; }}
QPushButton#primary {{
    background: rgba(0,212,255,0.12);
    border: 1px solid {T['accent']};
    color: {T['accent']};
}}
QPushButton#primary:hover {{ background: rgba(0,212,255,0.22); }}
QPushButton#danger {{
    background: rgba(255,51,85,0.10);
    border: 1px solid {T['danger']};
    color: {T['danger']};
}}
QPushButton#danger:hover {{ background: rgba(255,51,85,0.20); }}
QPushButton#success {{
    background: rgba(0,229,160,0.10);
    border: 1px solid {T['green']};
    color: {T['green']};
}}
QComboBox {{
    background: {T['surface2']};
    border: 1px solid {T['border']};
    border-radius: 6px;
    padding: 6px 12px;
    color: {T['text']};
    min-width: 140px;
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {T['surface2']};
    border: 1px solid {T['border']};
    selection-background-color: {T['border']};
}}
QCheckBox {{ spacing: 8px; color: {T['text']}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {T['border']};
    border-radius: 4px;
    background: {T['surface2']};
}}
QCheckBox::indicator:checked {{
    background: {T['accent']};
    border-color: {T['accent']};
}}
QLabel#status_ok  {{ color: {T['green']}; }}
QLabel#status_err {{ color: {T['danger']}; }}
QLabel#status_warn{{ color: {T['warn']}; }}
"""
