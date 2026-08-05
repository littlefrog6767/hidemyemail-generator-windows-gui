"""Qt stylesheet (QSS) built from the same color tokens as theme.py, so the
port to PySide6 keeps the original dark visual identity. Button/label
variants are selected via a Qt dynamic property (`variant`) rather than
subclassing, e.g. button.setProperty("variant", "primary")."""

from gui import theme

STYLESHEET = f"""
QWidget {{
    background-color: {theme.BG_MAIN};
    color: {theme.TEXT_PRIMARY};
    font-family: "{theme.FONT_FAMILY}";
    font-size: 13px;
}}

QMainWindow {{
    background-color: {theme.BG_MAIN};
}}

#Sidebar {{
    background-color: {theme.BG_SIDEBAR};
}}

#SidebarTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {theme.TEXT_PRIMARY};
}}

#SidebarSubtitle, #FooterLabel {{
    font-size: 11px;
    color: {theme.TEXT_SECONDARY};
}}

QPushButton[variant="nav"] {{
    background-color: transparent;
    color: {theme.TEXT_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
}}
QPushButton[variant="nav"]:hover {{
    background-color: {theme.SIDEBAR_HOVER};
}}
QPushButton[variant="nav"][active="true"] {{
    background-color: {theme.SIDEBAR_SELECTED};
    color: #ffffff;
}}

QPushButton[variant="primary"] {{
    background-color: {theme.ACCENT};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{ background-color: {theme.ACCENT_HOVER}; }}
QPushButton[variant="primary"]:pressed {{ background-color: {theme.ACCENT_PRESSED}; }}
QPushButton[variant="primary"]:disabled {{ background-color: {theme.BG_CARD_ALT}; color: {theme.TEXT_MUTED}; }}

QPushButton[variant="secondary"] {{
    background-color: {theme.BG_CARD_ALT};
    color: {theme.TEXT_PRIMARY};
    border: 1px solid {theme.BORDER};
    border-radius: 8px;
    padding: 8px 16px;
}}
QPushButton[variant="secondary"]:hover {{ background-color: {theme.SIDEBAR_HOVER}; }}
QPushButton[variant="secondary"]:disabled {{ color: {theme.TEXT_MUTED}; }}

QPushButton[variant="danger"] {{
    background-color: {theme.DANGER};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
}}
QPushButton[variant="danger"]:hover {{ background-color: {theme.DANGER_HOVER}; }}

QPushButton[variant="pill"] {{
    background-color: {theme.BG_CARD_ALT};
    color: {theme.TEXT_SECONDARY};
    border: none;
    border-radius: 14px;
    padding: 5px 14px;
    font-weight: 600;
}}
QPushButton[variant="pill"][active="true"] {{
    background-color: {theme.ACCENT};
    color: #ffffff;
}}

#Card {{
    background-color: {theme.BG_CARD};
    border: 1px solid {theme.BORDER};
    border-radius: 12px;
}}

#BulkBar {{
    background-color: {theme.BG_CARD_ALT};
    border-radius: 8px;
}}

QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {theme.BG_INPUT};
    border: 1px solid {theme.BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    color: {theme.TEXT_PRIMARY};
}}
QLineEdit:focus {{ border: 1px solid {theme.ACCENT}; }}

QLabel[variant="secondary"] {{ color: {theme.TEXT_SECONDARY}; }}
QLabel[variant="muted"] {{ color: {theme.TEXT_MUTED}; }}
QLabel[variant="success"] {{ color: {theme.SUCCESS}; }}
QLabel[variant="warning"] {{ color: {theme.WARNING}; }}
QLabel[variant="danger"] {{ color: {theme.DANGER}; }}
QLabel[variant="heading"] {{ font-size: 22px; font-weight: 700; color: {theme.TEXT_PRIMARY}; }}
QLabel[variant="section"] {{ font-size: 11px; font-weight: 700; color: {theme.TEXT_SECONDARY}; }}

QTabWidget::pane {{
    border: 1px solid {theme.BORDER};
    border-radius: 10px;
    background-color: {theme.BG_CARD};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {theme.BG_CARD_ALT};
    color: {theme.TEXT_SECONDARY};
    padding: 8px 18px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
}}
QTabBar::tab:selected {{
    background-color: {theme.ACCENT};
    color: #ffffff;
}}

QTableView {{
    background-color: {theme.BG_INPUT};
    alternate-background-color: {theme.BG_CARD_ALT};
    gridline-color: {theme.BORDER};
    border: 1px solid {theme.BORDER};
    border-radius: 10px;
    selection-background-color: {theme.SIDEBAR_SELECTED};
    selection-color: #ffffff;
}}
QHeaderView::section {{
    background-color: {theme.BG_CARD};
    color: {theme.TEXT_SECONDARY};
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid {theme.BORDER};
    font-weight: 700;
    font-size: 11px;
}}
QHeaderView::section:hover {{ background-color: {theme.BG_CARD_ALT}; }}

QTextEdit, QPlainTextEdit {{
    background-color: {theme.BG_INPUT};
    border: 1px solid {theme.BORDER};
    border-radius: 8px;
}}

QProgressBar {{
    background-color: {theme.BG_INPUT};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {theme.ACCENT};
    border-radius: 4px;
}}

QCheckBox {{ color: {theme.TEXT_SECONDARY}; spacing: 8px; }}

QComboBox {{
    background-color: {theme.BG_INPUT};
    border: 1px solid {theme.BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    color: {theme.TEXT_PRIMARY};
}}
QComboBox QAbstractItemView {{
    background-color: {theme.BG_CARD_ALT};
    color: {theme.TEXT_PRIMARY};
    selection-background-color: {theme.ACCENT};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 12px;
}}
QScrollBar::handle:vertical {{
    background: {theme.BG_CARD_ALT};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {theme.SIDEBAR_HOVER}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

QMenu {{
    background-color: {theme.BG_CARD_ALT};
    border: 1px solid {theme.BORDER};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {theme.ACCENT}; color: #ffffff; }}
"""
