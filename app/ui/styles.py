"""
Krolix Download Manager v2.8 - Dynamic Theming & macOS Style System
Features macOS Modern Dark Design:
- Visual Themes: macOS Sonoma Dark, macOS OLED Midnight, macOS Space Gray, macOS Light
- Accent Colors: Krolix Green, macOS Blue, Chrome Silver, Dark Titanium, Neon Violet, Sunset Amber, Crimson Rose
- Instant live theme switching without restarting the application
- Comprehensive styling for Title Bar, Traffic Lights, Source List, Tables, Dialogs, and macOS Toolbars
"""
import os

THEMES = {
    "mica_dark": {
        "name": "macOS Sonoma Dark",
        "is_dark": True,
        "bg_base": "#1e1e1e",
        "bg_surface": "#252526",
        "bg_elevated": "#2d2d2d",
        "bg_hover": "#383838",
        "bg_pressed": "#181818",
        "border": "#333333",
        "border_subtle": "#282828",
        "text_primary": "#f5f5f7",
        "text_secondary": "#d1d1d6",
        "text_muted": "#8e8e93",
        "scroll_track": "#1e1e1e",
        "scroll_thumb": "#3a3a3c",
    },
    "oled_black": {
        "name": "macOS OLED Midnight",
        "is_dark": True,
        "bg_base": "#000000",
        "bg_surface": "#000000",
        "bg_elevated": "#0a0a0a",
        "bg_hover": "#171717",
        "bg_pressed": "#040404",
        "border": "#1c1c1c",
        "border_subtle": "#121212",
        "text_primary": "#ffffff",
        "text_secondary": "#d4d4d8",
        "text_muted": "#71717a",
        "scroll_track": "#000000",
        "scroll_thumb": "#262626",
    },
    "nordic_slate": {
        "name": "macOS Space Gray",
        "is_dark": True,
        "bg_base": "#181a1f",
        "bg_surface": "#20232a",
        "bg_elevated": "#282c34",
        "bg_hover": "#323742",
        "bg_pressed": "#121417",
        "border": "#313640",
        "border_subtle": "#22252c",
        "text_primary": "#f8fafc",
        "text_secondary": "#cbd5e1",
        "text_muted": "#64748b",
        "scroll_track": "#14161b",
        "scroll_thumb": "#313640",
    },
    "fluent_light": {
        "name": "macOS Light",
        "is_dark": False,
        "bg_base": "#f5f5f7",
        "bg_surface": "#ffffff",
        "bg_elevated": "#f8fafc",
        "bg_hover": "#e5e5ea",
        "bg_pressed": "#d1d1d6",
        "border": "#d2d2d7",
        "border_subtle": "#e5e5ea",
        "text_primary": "#1d1d1f",
        "text_secondary": "#48484a",
        "text_muted": "#86868b",
        "scroll_track": "#f5f5f7",
        "scroll_thumb": "#d2d2d7",
    }
}

THEMES["macos_dark"] = THEMES["mica_dark"]
THEMES["amoled_black"] = THEMES["oled_black"]

ACCENTS = {
    "krolix_green": {
        "name": "Krolix Green",
        "primary": "#22c55e",
        "hover": "#16a34a",
        "gradient_end": "#15803d",
        "badge_bg": "rgba(34, 197, 94, 0.16)",
        "badge_text": "#4ade80"
    },
    "macos_blue": {
        "name": "macOS Blue",
        "primary": "#0a84ff",
        "hover": "#409cff",
        "gradient_end": "#0071e3",
        "badge_bg": "rgba(10, 132, 255, 0.16)",
        "badge_text": "#70b5ff"
    },
    "chrome": {
        "name": "Chrome Silver",
        "primary": "#94a3b8",
        "hover": "#cbd5e1",
        "gradient_end": "#64748b",
        "badge_bg": "rgba(148, 163, 184, 0.16)",
        "badge_text": "#e2e8f0"
    },
    "titanium": {
        "name": "Dark Titanium",
        "primary": "#64748b",
        "hover": "#94a3b8",
        "gradient_end": "#475569",
        "badge_bg": "rgba(100, 116, 139, 0.16)",
        "badge_text": "#cbd5e1"
    },
    "cyan": {
        "name": "Classic Blue",
        "primary": "#2563eb",
        "hover": "#3b82f6",
        "gradient_end": "#1d4ed8",
        "badge_bg": "rgba(37, 99, 235, 0.16)",
        "badge_text": "#60a5fa"
    },
    "emerald": {
        "name": "Emerald Green",
        "primary": "#10b981",
        "hover": "#34d399",
        "gradient_end": "#059669",
        "badge_bg": "rgba(16, 185, 129, 0.16)",
        "badge_text": "#34d399"
    },
    "violet": {
        "name": "Neon Violet",
        "primary": "#8b5cf6",
        "hover": "#a78bfa",
        "gradient_end": "#6366f1",
        "badge_bg": "rgba(139, 92, 246, 0.16)",
        "badge_text": "#a78bfa"
    },
    "amber": {
        "name": "Sunset Amber",
        "primary": "#f59e0b",
        "hover": "#fbbf24",
        "gradient_end": "#d97706",
        "badge_bg": "rgba(245, 158, 11, 0.16)",
        "badge_text": "#fbbf24"
    },
    "rose": {
        "name": "Crimson Rose",
        "primary": "#f43f5e",
        "hover": "#fb7185",
        "gradient_end": "#e11d48",
        "badge_bg": "rgba(244, 63, 94, 0.16)",
        "badge_text": "#fb7185"
    },
    "sky": {
        "name": "Sky Blue",
        "primary": "#0284c7",
        "hover": "#38bdf8",
        "gradient_end": "#0369a1",
        "badge_bg": "rgba(2, 132, 199, 0.16)",
        "badge_text": "#38bdf8"
    }
}

THEMES["nordic_navy"] = THEMES["nordic_slate"]

HEX_TO_ACCENT = {
    "#22c55e": "krolix_green",
    "#0a84ff": "macos_blue",
    "#94a3b8": "chrome",
    "#cbd5e1": "chrome",
    "#64748b": "titanium",
    "#2563eb": "cyan",
    "#06b6d4": "cyan",
    "#10b981": "emerald",
    "#8b5cf6": "violet",
    "#f59e0b": "amber",
    "#f43f5e": "rose",
    "#0284c7": "sky",
}


def get_app_stylesheet(theme_id: str = "mica_dark", accent_id: str = "chrome") -> str:
    """Generates the complete application stylesheet for the given theme and accent color."""
    t = THEMES.get(theme_id, THEMES.get("mica_dark"))
    if not t:
        t = THEMES["mica_dark"]

    # Support passing hex color directly or key
    if str(accent_id).lower() in HEX_TO_ACCENT:
        accent_key = HEX_TO_ACCENT[str(accent_id).lower()]
    else:
        accent_key = str(accent_id).lower()

    a = ACCENTS.get(accent_key)
    if not a:
        if str(accent_id).startswith("#"):
            a = {
                "name": "Custom",
                "primary": accent_id,
                "hover": accent_id,
                "gradient_end": accent_id,
                "badge_bg": "rgba(6, 182, 212, 0.16)",
                "badge_text": accent_id
            }
        else:
            a = ACCENTS["chrome"]

    bg_base = t["bg_base"]
    bg_surf = t["bg_surface"]
    bg_elev = t["bg_elevated"]
    bg_hov = t["bg_hover"]
    bg_press = t["bg_pressed"]
    border = t["border"]
    border_sub = t["border_subtle"]
    txt_prim = t["text_primary"]
    txt_sec = t["text_secondary"]
    txt_muted = t["text_muted"]
    sc_track = t["scroll_track"]
    sc_thumb = t["scroll_thumb"]

    acc_prim = a["primary"]
    acc_hov = a["hover"]
    acc_grad = a["gradient_end"]
    acc_badge_bg = a["badge_bg"]

    if bg_base == "#000000":
        capsule_bg = "rgba(255, 255, 255, 0.02)"
        capsule_border = "#1c1c1c"
    else:
        capsule_bg = "rgba(255, 255, 255, 0.035)" if t["is_dark"] else "rgba(0, 0, 0, 0.03)"
        capsule_border = "rgba(255, 255, 255, 0.08)" if t["is_dark"] else "rgba(0, 0, 0, 0.06)"

    chevron_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "chevron_down.svg")).replace("\\", "/")
    checkmark_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "checkmark.svg")).replace("\\", "/")
    spin_up_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "spinbox_up.svg")).replace("\\", "/")
    spin_down_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "spinbox_down.svg")).replace("\\", "/")

    return f"""
QWidget {{
    background-color: {bg_base};
    color: {txt_prim};
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Helvetica Neue", "Segoe UI", sans-serif;
    font-size: 12px;
}}

QMainWindow, QDialog {{
    background-color: {bg_base};
}}

/* macOS Signature Title Bar & Traffic Light Window Controls */
QWidget#KrolixMacOSTitleBar {{
    background-color: {bg_surf};
    border-bottom: 1px solid {border_sub};
    min-height: 38px;
    max-height: 38px;
}}

QLabel#macTitleLabel {{
    color: {txt_prim};
    font-size: 13px;
    font-weight: 600;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif;
    letter-spacing: 0.3px;
}}

QPushButton#macCloseBtn {{
    background-color: #ff5f56;
    border: 0.5px solid #e0443e;
    border-radius: 6px;
}}
QPushButton#macCloseBtn:hover {{
    background-color: #ff3b30;
    border: 0.5px solid #d32f2f;
}}
QPushButton#macCloseBtn:pressed {{
    background-color: #bf3026;
}}

QPushButton#macMinBtn {{
    background-color: #ffbd2e;
    border: 0.5px solid #dea123;
    border-radius: 6px;
}}
QPushButton#macMinBtn:hover {{
    background-color: #ff9500;
    border: 0.5px solid #e68500;
}}
QPushButton#macMinBtn:pressed {{
    background-color: #bf7400;
}}

QPushButton#macMaxBtn {{
    background-color: #27c93f;
    border: 0.5px solid #1aab29;
    border-radius: 6px;
}}
QPushButton#macMaxBtn:hover {{
    background-color: #34c759;
    border: 0.5px solid #28a745;
}}
QPushButton#macMaxBtn:pressed {{
    background-color: #1f8b31;
}}

/* Universal Clean Tooltip */
QToolTip {{
    background-color: {bg_elev};
    color: {txt_prim};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 500;
}}

/* Native Menu Bar */
QMenuBar {{
    background-color: {bg_base};
    color: {txt_sec};
    border-bottom: 1px solid {border_sub};
    padding: 4px 8px;
    font-size: 12px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 5px 11px;
    border-radius: 5px;
}}

QMenuBar::item:selected {{
    background-color: {bg_elev};
    color: {txt_prim};
}}

QMenuBar::item:pressed {{
    background-color: {bg_hov};
    color: {txt_prim};
}}

/* Context & Popup Menus */
QMenu {{
    background-color: {bg_surf};
    color: {txt_prim};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 6px;
}}

QMenu::item {{
    padding: 6px 28px 6px 12px;
    border-radius: 5px;
    font-size: 12px;
}}

QMenu::item:selected {{
    background-color: {bg_hov};
    color: #ffffff;
}}

QMenu::item:disabled {{
    color: {txt_muted};
}}

QMenu::separator {{
    height: 1px;
    background-color: {border_sub};
    margin: 5px 6px;
}}

/* macOS Command Bar / Toolbar Container */
QWidget#KrolixMacOSBar, QWidget#KrolixMacOSBar {{
    background-color: {bg_base};
    border-bottom: 1px solid {border_sub};
    min-height: 44px;
    max-height: 44px;
}}

/* Command Capsule Container */
QFrame.command-capsule {{
    background-color: {capsule_bg};
    border: 1px solid {capsule_border};
    border-radius: 10px;
    padding: 2px 4px;
}}

QToolButton.capsule-btn, QPushButton.capsule-btn {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 2px;
    color: {txt_sec};
    font-size: 10px;
    font-weight: 600;
    font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
    outline: none;
}}

QToolButton.capsule-btn:hover, QPushButton.capsule-btn:hover {{
    background-color: {bg_hov};
    border-color: {border_sub};
    color: #ffffff;
}}

QToolButton.capsule-btn:pressed, QPushButton.capsule-btn:pressed {{
    background-color: {bg_press};
    border-color: {acc_prim};
}}

QToolButton.capsule-btn:disabled, QPushButton.capsule-btn:disabled {{
    background-color: transparent;
    color: {txt_muted};
    opacity: 0.35;
}}

QToolButton.capsule-btn-accent, QPushButton.capsule-btn-accent {{
    color: {acc_prim};
}}

QToolButton.capsule-btn-danger:hover, QPushButton.capsule-btn-danger:hover {{
    background-color: rgba(239, 68, 68, 0.15);
    border-color: rgba(239, 68, 68, 0.3);
    color: #f87171;
}}

QToolButton.capsule-btn::menu-button {{
    border: none;
    background: transparent;
    width: 13px;
}}

QToolButton.capsule-btn::menu-button:hover {{
    background-color: rgba(255, 255, 255, 0.08);
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
}}

QToolButton.capsule-btn::menu-arrow {{
    image: url({chevron_path});
    width: 8px;
    height: 5px;
}}

/* Search Input (macOS Style Pill) */
QLineEdit#KrolixSearchBar, QLineEdit#W11SearchBar, QLineEdit#CommandSearch {{
    background-color: {bg_surf};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 6px 12px 6px 30px;
    color: {txt_prim};
    font-size: 12px;
}}

QLineEdit#KrolixSearchBar:focus, QLineEdit#W11SearchBar:focus, QLineEdit#CommandSearch:focus {{
    border: 1px solid {acc_prim};
    background-color: {bg_elev};
}}

/* Sidebar Tree View (macOS Source List) */
QTreeWidget#CategoryTree, QTreeWidget#KrolixTree, QTreeWidget#KrolixTree {{
    background-color: {bg_base};
    border: none;
    border-right: 1px solid {border_sub};
    padding: 6px 4px;
    outline: none;
}}

QTreeWidget#CategoryTree::item:focus, QTreeWidget#KrolixTree::item:focus, QTreeWidget#KrolixTree::item:focus {{
    outline: none;
    border: none;
}}

QTreeWidget#CategoryTree::item, QTreeWidget#KrolixTree::item, QTreeWidget#KrolixTree::item {{
    height: 32px;
    border-radius: 6px;
    padding-left: 8px;
    color: {txt_sec};
    font-size: 12px;
}}

QTreeWidget#CategoryTree::item:hover, QTreeWidget#KrolixTree::item:hover, QTreeWidget#KrolixTree::item:hover {{
    background-color: {bg_hov if bg_base == "#000000" else "rgba(255, 255, 255, 0.04)"};
    color: {txt_prim};
}}

QTreeWidget#CategoryTree::item:selected, QTreeWidget#KrolixTree::item:selected, QTreeWidget#KrolixTree::item:selected {{
    background-color: {bg_elev if bg_base == "#000000" else "rgba(255, 255, 255, 0.08)"};
    color: #ffffff;
    font-weight: 600;
}}

/* Main Download Table */
QTableWidget#DownloadTable, QTableWidget {{
    background-color: {bg_surf};
    border: none;
    gridline-color: transparent;
    selection-background-color: {"#0d223a" if bg_base == "#000000" else "rgba(255, 255, 255, 0.08)"};
    selection-color: #ffffff;
    outline: 0;
}}

QTableWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {border_sub};
    color: {txt_prim};
}}

QTableWidget::item:selected {{
    background-color: {"#0e253e" if bg_base == "#000000" else "rgba(255, 255, 255, 0.08)"};
    color: #ffffff;
}}

QTableWidget::item:hover:!selected {{
    background-color: {"#0c0c0e" if bg_base == "#000000" else "rgba(255, 255, 255, 0.03)"};
}}

/* Table Headers */
QHeaderView::section {{
    background-color: {bg_base};
    color: {txt_sec};
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {border};
    border-right: 1px solid {border_sub};
    font-weight: 600;
    font-size: 11px;
}}

QHeaderView::section:hover {{
    background-color: {bg_elev};
    color: {txt_prim};
}}

/* Splitters */
QSplitter::handle {{
    background-color: {border_sub};
    width: 2px;
    height: 2px;
}}

QSplitter::handle:hover {{
    background-color: {acc_prim};
}}

/* Modern Tab Widget & Tab Bar (Used in Settings, Dialogs) */
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 8px;
    background-color: {bg_surf};
    padding: 8px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: {bg_base};
    color: {txt_sec};
    border: 1px solid {border_sub};
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    padding: 7px 16px;
    font-weight: 500;
    font-size: 12px;
    margin-right: 3px;
}}

QTabBar::tab:hover {{
    background-color: {bg_elev};
    color: {txt_prim};
}}

QTabBar::tab:selected {{
    background-color: {bg_surf};
    color: {acc_prim};
    font-weight: 600;
    border-color: {border};
    border-bottom: 2px solid {acc_prim};
}}

/* Modern Scrollbars */
QScrollBar:vertical {{
    background-color: {sc_track};
    width: 9px;
    margin: 0px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background-color: {sc_thumb};
    min-height: 28px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {acc_prim};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {sc_track};
    height: 9px;
    margin: 0px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background-color: {sc_thumb};
    min-width: 28px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {acc_prim};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Status Bar */
QStatusBar {{
    background-color: {bg_base};
    color: {txt_muted};
    border-top: 1px solid {border_sub};
    font-size: 11px;
    padding: 3px 12px;
}}

/* Bottom Details Drawer (macOS Inspector Style) */
QWidget#KrolixDrawer, QWidget#KrolixDrawer {{
    background-color: {bg_elev if bg_base == "#000000" else bg_surf};
    border-top: 1px solid {border_sub};
}}

QWidget#KrolixDrawer QPushButton, QWidget#KrolixDrawer QPushButton {{
    background-color: {bg_surf if bg_base == "#000000" else bg_elev};
    border: 1px solid {border_sub};
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 500;
}}

QWidget#KrolixDrawer QPushButton:hover, QWidget#KrolixDrawer QPushButton:hover {{
    background-color: {bg_hov};
    border-color: {acc_prim};
}}

QWidget#KrolixDrawer QPushButton#LimiterPill, QWidget#KrolixDrawer QPushButton#LimiterPill {{
    background-color: rgba(255, 255, 255, 0.04);
    border: 1px solid {border_sub};
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    color: {txt_sec};
}}

QWidget#KrolixDrawer QPushButton#LimiterPill:hover, QWidget#KrolixDrawer QPushButton#LimiterPill:hover {{
    background-color: {bg_hov};
    border-color: {acc_prim};
    color: {txt_prim};
}}

QWidget#KrolixDrawer QPushButton#LimiterPill[active="true"], QWidget#KrolixDrawer QPushButton#LimiterPill[active="true"] {{
    background-color: {acc_badge_bg};
    border: 1px solid {acc_prim};
    color: {acc_prim};
}}

/* Inputs & Form Controls */
QLineEdit {{
    background-color: {bg_surf};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 7px 10px;
    color: {txt_prim};
    font-size: 12px;
}}

QLineEdit:focus {{
    border: 1px solid {acc_prim};
    background-color: {bg_elev};
}}

QSpinBox, QDoubleSpinBox {{
    background-color: {bg_surf};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 24px 6px 10px;
    color: {txt_prim};
    font-size: 12px;
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {acc_prim};
    background-color: {bg_elev};
}}

QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid {border_sub};
    border-bottom: 1px solid {border_sub};
    background-color: {bg_elev};
    border-top-right-radius: 5px;
}}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{
    background-color: {bg_hov};
}}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({spin_up_path});
    width: 8px;
    height: 5px;
}}

QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    border-left: 1px solid {border_sub};
    background-color: {bg_elev};
    border-bottom-right-radius: 5px;
}}

QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {bg_hov};
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({spin_down_path});
    width: 8px;
    height: 5px;
}}

QComboBox {{
    background-color: {bg_surf};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 28px 6px 10px;
    color: {txt_prim};
    font-size: 12px;
}}

QComboBox:focus {{
    border: 1px solid {acc_prim};
    background-color: {bg_elev};
}}

QComboBox::drop-down {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid {border_sub};
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: {bg_elev};
}}

QComboBox::drop-down:hover {{
    background-color: {bg_hov};
}}

QComboBox::down-arrow {{
    image: url({chevron_path});
    width: 9px;
    height: 6px;
}}

/* Standard Push Buttons */
QPushButton {{
    background-color: {bg_elev};
    color: {txt_prim};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 500;
    font-size: 12px;
}}

QPushButton:hover {{
    background-color: {bg_hov};
    color: {txt_prim};
    border-color: {acc_prim};
}}

QPushButton:pressed {{
    background-color: {bg_press};
    border-color: {acc_prim};
}}

QPushButton:disabled {{
    background-color: {bg_base};
    color: {txt_muted};
    border-color: {border_sub};
}}

/* Accent Colored Action Buttons */
QPushButton#AccentButton, QPushButton#PrimaryBtn {{
    background-color: {acc_prim};
    color: #ffffff;
    border: 1px solid {acc_prim};
    font-weight: 600;
    border-radius: 6px;
}}

QPushButton#AccentButton:hover, QPushButton#PrimaryBtn:hover {{
    background-color: {acc_hov};
    border-color: {acc_hov};
}}

QPushButton#AccentButton:pressed, QPushButton#PrimaryBtn:pressed {{
    background-color: {acc_grad};
    border-color: {acc_grad};
}}

/* Progress Bar */
QProgressBar {{
    background-color: {bg_elev};
    border: 1px solid {border};
    border-radius: 5px;
    text-align: center;
    color: {txt_prim};
    font-size: 10px;
    font-weight: 600;
    min-height: 14px;
}}

QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {acc_prim}, stop:1 {acc_grad});
    border-radius: 4px;
}}

/* Group Box */
QGroupBox {{
    font-weight: 600;
    color: {txt_sec};
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 12px;
    padding: 14px 12px 12px 12px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: {txt_prim};
}}

/* CheckBoxes & Radio Buttons */
QCheckBox, QRadioButton {{
    color: {txt_prim};
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {border};
    border-radius: 4px;
    background-color: {bg_surf};
}}

QCheckBox::indicator:hover {{
    border-color: {acc_prim};
}}

QCheckBox::indicator:checked {{
    background-color: {acc_prim};
    border-color: {acc_prim};
    image: url({checkmark_path});
}}

QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {border};
    border-radius: 8px;
    background-color: {bg_surf};
}}

QRadioButton::indicator:hover {{
    border-color: {acc_prim};
}}

QRadioButton::indicator:checked {{
    background-color: {acc_prim};
    border-color: {acc_prim};
}}

/* List Widgets */
QListWidget {{
    background-color: {bg_surf};
    border: 1px solid {border};
    border-radius: 7px;
    padding: 4px;
    outline: 0;
}}

QListWidget::item {{
    padding: 6px 10px;
    border-radius: 5px;
    color: {txt_prim};
}}

QListWidget::item:hover {{
    background-color: {bg_hov};
}}

QListWidget::item:selected {{
    background-color: rgba(255, 255, 255, 0.08);
    color: #ffffff;
}}

/* Slider */
QSlider::groove:horizontal {{
    height: 6px;
    background: {bg_elev};
    border: 1px solid {border};
    border-radius: 3px;
}}

QSlider::sub-page:horizontal {{
    background: {acc_prim};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: #ffffff;
    border: 2px solid {acc_prim};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: {acc_hov};
}}

/* Modern macOS Header and Tool Buttons */
QWidget#KrolixMacOSHeader {{
    background-color: {bg_base};
    border-bottom: 1px solid {border_sub};
}}

QToolButton#macAddBtn {{
    background-color: #22c55e;
    color: #ffffff;
    font-size: 12px;
    font-weight: 600;
    border-radius: 6px;
    padding: 5px 12px;
    border: none;
}}
QToolButton#macAddBtn:hover {{
    background-color: #16a34a;
}}
QToolButton#macAddBtn:pressed {{
    background-color: #15803d;
}}

QToolButton.mac-tool-btn {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px;
    color: {txt_sec};
}}
QToolButton.mac-tool-btn:hover {{
    background-color: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.12);
    color: #ffffff;
}}
QToolButton.mac-tool-btn:pressed {{
    background-color: rgba(255, 255, 255, 0.14);
}}

/* macOS Source List Sidebar */
QTreeWidget#KrolixTree {{
    background-color: #121216;
    border: none;
    border-right: 1px solid {border_sub};
    padding: 8px 6px;
    font-size: 12px;
    outline: none;
}}
QTreeWidget#KrolixTree::item {{
    height: 30px;
    padding: 4px 8px;
    border-radius: 6px;
    color: #d1d5db;
    margin: 1px 2px;
}}
QTreeWidget#KrolixTree::item:hover {{
    background-color: rgba(255, 255, 255, 0.05);
    color: #ffffff;
}}
QTreeWidget#KrolixTree::item:selected {{
    background-color: rgba(255, 255, 255, 0.12);
    color: #ffffff;
    font-weight: 600;
}}

/* macOS Status Footer */
QWidget#KrolixFooterBar {{
    background-color: #121216;
    border-top: 1px solid {border_sub};
    min-height: 28px;
    max-height: 28px;
    padding: 0 12px;
}}

/* Transparent overlay support - Eliminates rectangular blocks */
QWidget#KrolixEmptyState,
QWidget#KrolixEmptyState QLabel,
QLabel#EmptyStateIcon,
QLabel#EmptyStateTitle,
QLabel#EmptyStateSubtitle {{
    background: transparent !important;
    background-color: transparent !important;
    border: none !important;
}}

QPushButton#EmptyAddBtn {{
    background-color: #22c55e !important;
    color: #ffffff !important;
    border: 1px solid #22c55e !important;
    font-weight: 600;
    border-radius: 6px;
    padding: 6px 16px;
}}
QPushButton#EmptyAddBtn:hover {{
    background-color: #16a34a !important;
    border-color: #16a34a !important;
}}
QPushButton#EmptyAddBtn:pressed {{
    background-color: #15803d !important;
    border-color: #15803d !important;
}}
"""

# Theme exports
KROLIX_MACOS_THEME = get_app_stylesheet("mica_dark", "krolix_green")
KROLIX_OLED_THEME = get_app_stylesheet("oled_black", "krolix_green")
ZERO_WIN11_THEME = KROLIX_MACOS_THEME
ZERO_DARK_THEME = KROLIX_MACOS_THEME
VORTEX_OBSIDIAN_THEME = KROLIX_OLED_THEME
CYBER_GREEN_THEME = get_app_stylesheet("mica_dark", "emerald")
DARK_THEME = KROLIX_MACOS_THEME