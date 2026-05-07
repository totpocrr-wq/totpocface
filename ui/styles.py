"""Тёмная тема приложения. Единая палитра."""

# Палитра: глубокий графит + тёплый янтарный акцент
COLORS = {
    "bg": "#0F1115",
    "surface": "#171A21",
    "surface_2": "#1F232C",
    "border": "#2A2F3A",
    "text": "#E6E8EC",
    "text_muted": "#8B92A1",
    "accent": "#E8A33D",       # янтарь
    "accent_hover": "#F5B454",
    "accent_pressed": "#C68A2C",
    "danger": "#E0556C",
    "ok": "#4CB782",
}

QSS = f"""
* {{
    color: {COLORS['text']};
    font-family: "Segoe UI", "SF Pro Text", system-ui, sans-serif;
    font-size: 13px;
}}

QMainWindow, QWidget#root {{
    background-color: {COLORS['bg']};
}}

QLabel#title {{
    font-size: 22px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}

QLabel#subtitle {{
    color: {COLORS['text_muted']};
    font-size: 12px;
}}

QFrame#card {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
}}

QLabel#cardTitle {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.5px;
    color: {COLORS['text_muted']};
    text-transform: uppercase;
}}

QLabel#preview {{
    background-color: #000;
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    color: {COLORS['text_muted']};
}}

QPushButton {{
    background-color: {COLORS['surface_2']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 9px 16px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {COLORS['border']};
    border-color: {COLORS['text_muted']};
}}
QPushButton:disabled {{
    color: {COLORS['text_muted']};
    background-color: {COLORS['surface']};
}}

QPushButton#primary {{
    background-color: {COLORS['accent']};
    color: #1A1A1A;
    border: 1px solid {COLORS['accent']};
}}
QPushButton#primary:hover {{
    background-color: {COLORS['accent_hover']};
    border-color: {COLORS['accent_hover']};
}}
QPushButton#primary:pressed {{
    background-color: {COLORS['accent_pressed']};
}}
QPushButton#primary:disabled {{
    background-color: {COLORS['surface_2']};
    color: {COLORS['text_muted']};
    border-color: {COLORS['border']};
}}

QPushButton#danger {{
    background-color: transparent;
    color: {COLORS['danger']};
    border: 1px solid {COLORS['danger']};
}}
QPushButton#danger:hover {{
    background-color: {COLORS['danger']};
    color: #FFFFFF;
}}

QComboBox {{
    background-color: {COLORS['surface_2']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px 12px;
    min-width: 200px;
}}
QComboBox:hover {{
    border-color: {COLORS['text_muted']};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS['surface_2']};
    border: 1px solid {COLORS['border']};
    selection-background-color: {COLORS['accent']};
    selection-color: #1A1A1A;
    padding: 4px;
}}

QProgressBar {{
    background-color: {COLORS['surface_2']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    height: 10px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {COLORS['accent']};
    border-radius: 5px;
}}

QStatusBar {{
    background-color: {COLORS['surface']};
    color: {COLORS['text_muted']};
    border-top: 1px solid {COLORS['border']};
}}

QLabel#status_ok {{ color: {COLORS['ok']}; }}
QLabel#status_warn {{ color: {COLORS['accent']}; }}
QLabel#status_err {{ color: {COLORS['danger']}; }}

QLabel#dropzone {{
    background-color: {COLORS['surface_2']};
    border: 2px dashed {COLORS['border']};
    border-radius: 10px;
    color: {COLORS['text_muted']};
    padding: 12px;
}}
QLabel#dropzone[active="true"] {{
    border-color: {COLORS['accent']};
    color: {COLORS['accent']};
}}

QLabel#recIndicator {{
    color: {COLORS['danger']};
    font-weight: 700;
    letter-spacing: 1px;
}}
"""
