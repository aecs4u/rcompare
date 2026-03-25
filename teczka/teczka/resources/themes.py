"""Light and dark QSS theme stylesheets matching the Slint GUI color palette.

Slint GUI palette colors (light):
    panel_bg      = #ffffff
    chrome        = #f6f7f9
    header        = #edf1f5
    border        = #c5ccd6
    accent        = #3a78d6
    accent_soft   = #e7f0ff
    toolbar       = #f4f6f8
    status_bg     = #eef2f7
    row_alt       = #fafbfc
    selected      = #cfe1f7
    selected_border = #6d96d6
    selected_text = #0b2346
"""


def load_light_theme() -> str:
    """Return a QSS stylesheet for the light theme.

    Provides a clean, professional look inspired by Beyond Compare 4 with
    subtle borders, clean fonts, and the RCompare accent color palette.
    """
    return """
/* ================================================================
   RCompare Light Theme
   ================================================================ */

/* --- Global defaults ----------------------------------------------- */
* {
    font-family: "Segoe UI", "Noto Sans", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

/* --- QMainWindow --------------------------------------------------- */
QMainWindow {
    background-color: #ffffff;
    color: #1c1c1c;
}

QMainWindow::separator {
    background-color: #c5ccd6;
    width: 1px;
    height: 1px;
}

/* --- QToolBar ------------------------------------------------------ */
QToolBar {
    background-color: #f4f6f8;
    border-bottom: 1px solid #c5ccd6;
    padding: 2px 4px;
    spacing: 4px;
}

QToolBar::separator {
    background-color: #c5ccd6;
    width: 1px;
    margin: 4px 6px;
}

/* --- QToolButton --------------------------------------------------- */
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 4px 8px;
    color: #1c1c1c;
}

QToolButton:hover {
    background-color: #e7f0ff;
    border: 1px solid #6d96d6;
}

QToolButton:pressed {
    background-color: #cfe1f7;
    border: 1px solid #3a78d6;
}

QToolButton:checked {
    background-color: #cfe1f7;
    border: 1px solid #6d96d6;
}

QToolButton:disabled {
    color: #a0a0a0;
}

/* --- QMenuBar ------------------------------------------------------ */
QMenuBar {
    background-color: #f6f7f9;
    border-bottom: 1px solid #c5ccd6;
    padding: 1px;
    color: #1c1c1c;
}

QMenuBar::item {
    background-color: transparent;
    padding: 4px 10px;
    border-radius: 3px;
}

QMenuBar::item:selected {
    background-color: #e7f0ff;
    color: #0b2346;
}

QMenuBar::item:pressed {
    background-color: #cfe1f7;
    color: #0b2346;
}

/* --- QMenu --------------------------------------------------------- */
QMenu {
    background-color: #ffffff;
    border: 1px solid #c5ccd6;
    padding: 4px 0;
    color: #1c1c1c;
}

QMenu::item {
    padding: 6px 30px 6px 20px;
}

QMenu::item:selected {
    background-color: #e7f0ff;
    color: #0b2346;
}

QMenu::item:disabled {
    color: #a0a0a0;
}

QMenu::separator {
    height: 1px;
    background-color: #c5ccd6;
    margin: 4px 10px;
}

QMenu::indicator {
    width: 14px;
    height: 14px;
    margin-left: 6px;
}

/* --- QStatusBar ---------------------------------------------------- */
QStatusBar {
    background-color: #eef2f7;
    border-top: 1px solid #c5ccd6;
    color: #1c1c1c;
    padding: 2px 6px;
}

QStatusBar::item {
    border: none;
}

QStatusBar QLabel {
    padding: 0 4px;
}

/* --- QTreeView ----------------------------------------------------- */
QTreeView {
    background-color: #ffffff;
    alternate-background-color: #fafbfc;
    border: 1px solid #c5ccd6;
    color: #1c1c1c;
    selection-background-color: #cfe1f7;
    selection-color: #0b2346;
    outline: none;
}

QTreeView::item {
    padding: 3px 4px;
    border: none;
}

QTreeView::item:hover {
    background-color: #e7f0ff;
}

QTreeView::item:selected {
    background-color: #cfe1f7;
    color: #0b2346;
    border: none;
}

QTreeView::item:selected:!active {
    background-color: #dde6f0;
    color: #0b2346;
}

QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {
    border-image: none;
}

QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {
    border-image: none;
}

/* --- QTableView ---------------------------------------------------- */
QTableView {
    background-color: #ffffff;
    alternate-background-color: #fafbfc;
    border: 1px solid #c5ccd6;
    color: #1c1c1c;
    selection-background-color: #cfe1f7;
    selection-color: #0b2346;
    gridline-color: #e0e4ea;
    outline: none;
}

QTableView::item {
    padding: 3px 6px;
    border: none;
}

QTableView::item:hover {
    background-color: #e7f0ff;
}

QTableView::item:selected {
    background-color: #cfe1f7;
    color: #0b2346;
}

QTableView::item:selected:!active {
    background-color: #dde6f0;
    color: #0b2346;
}

/* --- QHeaderView --------------------------------------------------- */
QHeaderView {
    background-color: #edf1f5;
    border: none;
}

QHeaderView::section {
    background-color: #edf1f5;
    color: #1c1c1c;
    padding: 5px 8px;
    border: none;
    border-right: 1px solid #c5ccd6;
    border-bottom: 1px solid #c5ccd6;
    font-weight: 600;
}

QHeaderView::section:hover {
    background-color: #e7f0ff;
}

QHeaderView::section:pressed {
    background-color: #cfe1f7;
}

QHeaderView::down-arrow {
    subcontrol-position: center right;
    padding-right: 6px;
}

QHeaderView::up-arrow {
    subcontrol-position: center right;
    padding-right: 6px;
}

/* --- QSplitter ----------------------------------------------------- */
QSplitter::handle {
    background-color: #c5ccd6;
}

QSplitter::handle:horizontal {
    width: 3px;
}

QSplitter::handle:vertical {
    height: 3px;
}

QSplitter::handle:hover {
    background-color: #3a78d6;
}

/* --- QPushButton --------------------------------------------------- */
QPushButton {
    background-color: #f6f7f9;
    border: 1px solid #c5ccd6;
    border-radius: 4px;
    padding: 5px 16px;
    color: #1c1c1c;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #e7f0ff;
    border: 1px solid #6d96d6;
}

QPushButton:pressed {
    background-color: #cfe1f7;
    border: 1px solid #3a78d6;
}

QPushButton:default {
    background-color: #3a78d6;
    border: 1px solid #2a5fb0;
    color: #ffffff;
}

QPushButton:default:hover {
    background-color: #4a88e6;
    border: 1px solid #3a78d6;
}

QPushButton:default:pressed {
    background-color: #2a5fb0;
    border: 1px solid #1e4d8e;
}

QPushButton:disabled {
    background-color: #edf1f5;
    border: 1px solid #dde0e5;
    color: #a0a0a0;
}

QPushButton:flat {
    background-color: transparent;
    border: none;
}

QPushButton:flat:hover {
    background-color: #e7f0ff;
}

/* --- QLineEdit ----------------------------------------------------- */
QLineEdit {
    background-color: #ffffff;
    border: 1px solid #c5ccd6;
    border-radius: 3px;
    padding: 4px 8px;
    color: #1c1c1c;
    selection-background-color: #cfe1f7;
    selection-color: #0b2346;
}

QLineEdit:focus {
    border: 1px solid #3a78d6;
}

QLineEdit:disabled {
    background-color: #f6f7f9;
    color: #a0a0a0;
}

QLineEdit:read-only {
    background-color: #f6f7f9;
}

/* --- QTextEdit / QPlainTextEdit ------------------------------------ */
QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    border: 1px solid #c5ccd6;
    border-radius: 3px;
    padding: 4px;
    color: #1c1c1c;
    selection-background-color: #cfe1f7;
    selection-color: #0b2346;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #3a78d6;
}

QTextEdit:disabled, QPlainTextEdit:disabled {
    background-color: #f6f7f9;
    color: #a0a0a0;
}

/* --- QCheckBox ----------------------------------------------------- */
QCheckBox {
    color: #1c1c1c;
    spacing: 6px;
}

QCheckBox:disabled {
    color: #a0a0a0;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #c5ccd6;
    border-radius: 3px;
    background-color: #ffffff;
}

QCheckBox::indicator:hover {
    border: 1px solid #6d96d6;
    background-color: #e7f0ff;
}

QCheckBox::indicator:checked {
    background-color: #3a78d6;
    border: 1px solid #2a5fb0;
}

QCheckBox::indicator:checked:hover {
    background-color: #4a88e6;
    border: 1px solid #3a78d6;
}

QCheckBox::indicator:disabled {
    background-color: #edf1f5;
    border: 1px solid #dde0e5;
}

/* --- QRadioButton -------------------------------------------------- */
QRadioButton {
    color: #1c1c1c;
    spacing: 6px;
}

QRadioButton:disabled {
    color: #a0a0a0;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #c5ccd6;
    border-radius: 8px;
    background-color: #ffffff;
}

QRadioButton::indicator:hover {
    border: 1px solid #6d96d6;
    background-color: #e7f0ff;
}

QRadioButton::indicator:checked {
    background-color: #3a78d6;
    border: 1px solid #2a5fb0;
}

QRadioButton::indicator:checked:hover {
    background-color: #4a88e6;
    border: 1px solid #3a78d6;
}

QRadioButton::indicator:disabled {
    background-color: #edf1f5;
    border: 1px solid #dde0e5;
}

/* --- QTabWidget ---------------------------------------------------- */
QTabWidget::pane {
    background-color: #ffffff;
    border: 1px solid #c5ccd6;
    border-top: none;
}

QTabWidget::tab-bar {
    alignment: left;
}

/* --- QTabBar ------------------------------------------------------- */
QTabBar {
    background-color: transparent;
    border: none;
}

QTabBar::tab {
    background-color: #edf1f5;
    border: 1px solid #c5ccd6;
    border-bottom: none;
    padding: 6px 16px;
    margin-right: 1px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    color: #1c1c1c;
}

QTabBar::tab:hover {
    background-color: #e7f0ff;
}

QTabBar::tab:selected {
    background-color: #ffffff;
    border-bottom: 1px solid #ffffff;
    color: #0b2346;
    font-weight: 600;
}

QTabBar::tab:!selected {
    margin-top: 2px;
}

QTabBar::tab:disabled {
    color: #a0a0a0;
}

QTabBar::close-button {
    border: none;
    padding: 2px;
}

QTabBar::close-button:hover {
    background-color: #cfe1f7;
    border-radius: 2px;
}

/* --- QGroupBox ----------------------------------------------------- */
QGroupBox {
    background-color: transparent;
    border: 1px solid #c5ccd6;
    border-radius: 4px;
    margin-top: 8px;
    padding: 12px 8px 8px 8px;
    font-weight: 600;
    color: #1c1c1c;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #0b2346;
}

/* --- QLabel -------------------------------------------------------- */
QLabel {
    color: #1c1c1c;
    background-color: transparent;
}

QLabel:disabled {
    color: #a0a0a0;
}

/* --- QComboBox ----------------------------------------------------- */
QComboBox {
    background-color: #ffffff;
    border: 1px solid #c5ccd6;
    border-radius: 3px;
    padding: 4px 8px;
    color: #1c1c1c;
    min-height: 20px;
}

QComboBox:hover {
    border: 1px solid #6d96d6;
}

QComboBox:focus {
    border: 1px solid #3a78d6;
}

QComboBox:disabled {
    background-color: #f6f7f9;
    color: #a0a0a0;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 20px;
    border-left: 1px solid #c5ccd6;
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
    background-color: #f6f7f9;
}

QComboBox::down-arrow {
    width: 10px;
    height: 10px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #c5ccd6;
    selection-background-color: #cfe1f7;
    selection-color: #0b2346;
    outline: none;
}

/* --- QScrollBar (vertical) ----------------------------------------- */
QScrollBar:vertical {
    background-color: #f6f7f9;
    width: 12px;
    margin: 0;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #c5ccd6;
    min-height: 30px;
    border-radius: 4px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #a0aab6;
}

QScrollBar::handle:vertical:pressed {
    background-color: #6d96d6;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
    border: none;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background-color: transparent;
}

/* --- QScrollBar (horizontal) --------------------------------------- */
QScrollBar:horizontal {
    background-color: #f6f7f9;
    height: 12px;
    margin: 0;
    border: none;
}

QScrollBar::handle:horizontal {
    background-color: #c5ccd6;
    min-width: 30px;
    border-radius: 4px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #a0aab6;
}

QScrollBar::handle:horizontal:pressed {
    background-color: #6d96d6;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
    border: none;
}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background-color: transparent;
}

/* --- QDialog ------------------------------------------------------- */
QDialog {
    background-color: #ffffff;
    color: #1c1c1c;
}

/* --- QProgressBar -------------------------------------------------- */
QProgressBar {
    background-color: #edf1f5;
    border: 1px solid #c5ccd6;
    border-radius: 3px;
    text-align: center;
    color: #1c1c1c;
    height: 18px;
}

QProgressBar::chunk {
    background-color: #3a78d6;
    border-radius: 2px;
}

/* --- QToolTip ------------------------------------------------------ */
QToolTip {
    background-color: #ffffff;
    border: 1px solid #c5ccd6;
    color: #1c1c1c;
    padding: 4px 8px;
}

/* --- QDockWidget --------------------------------------------------- */
QDockWidget {
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
    color: #1c1c1c;
}

QDockWidget::title {
    background-color: #edf1f5;
    border: 1px solid #c5ccd6;
    padding: 5px 8px;
    text-align: left;
}

QDockWidget::close-button,
QDockWidget::float-button {
    border: none;
    background-color: transparent;
    padding: 2px;
}

QDockWidget::close-button:hover,
QDockWidget::float-button:hover {
    background-color: #cfe1f7;
    border-radius: 2px;
}

/* --- QSpinBox / QDoubleSpinBox ------------------------------------- */
QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    border: 1px solid #c5ccd6;
    border-radius: 3px;
    padding: 4px 8px;
    color: #1c1c1c;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #3a78d6;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    border-left: 1px solid #c5ccd6;
    border-bottom: 1px solid #c5ccd6;
    background-color: #f6f7f9;
    width: 18px;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    border-left: 1px solid #c5ccd6;
    background-color: #f6f7f9;
    width: 18px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #e7f0ff;
}

/* --- QSlider ------------------------------------------------------- */
QSlider::groove:horizontal {
    border: 1px solid #c5ccd6;
    height: 4px;
    background-color: #edf1f5;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background-color: #3a78d6;
    border: 1px solid #2a5fb0;
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background-color: #4a88e6;
}

/* --- Focus ring (global) ------------------------------------------- */
*:focus {
    outline: none;
}
"""


def load_dark_theme() -> str:
    """Return a QSS stylesheet for the dark theme.

    Uses dark backgrounds (#1e1e1e, #252526, #2d2d2d) with the RCompare
    accent colors adapted for dark mode readability.
    """
    return """
/* ================================================================
   RCompare Dark Theme
   ================================================================ */

/* --- Global defaults ----------------------------------------------- */
* {
    font-family: "Segoe UI", "Noto Sans", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

/* --- QMainWindow --------------------------------------------------- */
QMainWindow {
    background-color: #1e1e1e;
    color: #d4d4d4;
}

QMainWindow::separator {
    background-color: #3e3e42;
    width: 1px;
    height: 1px;
}

/* --- QToolBar ------------------------------------------------------ */
QToolBar {
    background-color: #2d2d2d;
    border-bottom: 1px solid #3e3e42;
    padding: 2px 4px;
    spacing: 4px;
}

QToolBar::separator {
    background-color: #3e3e42;
    width: 1px;
    margin: 4px 6px;
}

/* --- QToolButton --------------------------------------------------- */
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 4px 8px;
    color: #d4d4d4;
}

QToolButton:hover {
    background-color: #3a3d41;
    border: 1px solid #4a6ea9;
}

QToolButton:pressed {
    background-color: #2a4a7a;
    border: 1px solid #3a78d6;
}

QToolButton:checked {
    background-color: #2a4a7a;
    border: 1px solid #4a6ea9;
}

QToolButton:disabled {
    color: #5a5a5a;
}

/* --- QMenuBar ------------------------------------------------------ */
QMenuBar {
    background-color: #252526;
    border-bottom: 1px solid #3e3e42;
    padding: 1px;
    color: #d4d4d4;
}

QMenuBar::item {
    background-color: transparent;
    padding: 4px 10px;
    border-radius: 3px;
}

QMenuBar::item:selected {
    background-color: #3a3d41;
    color: #ffffff;
}

QMenuBar::item:pressed {
    background-color: #2a4a7a;
    color: #ffffff;
}

/* --- QMenu --------------------------------------------------------- */
QMenu {
    background-color: #252526;
    border: 1px solid #3e3e42;
    padding: 4px 0;
    color: #d4d4d4;
}

QMenu::item {
    padding: 6px 30px 6px 20px;
}

QMenu::item:selected {
    background-color: #2a4a7a;
    color: #ffffff;
}

QMenu::item:disabled {
    color: #5a5a5a;
}

QMenu::separator {
    height: 1px;
    background-color: #3e3e42;
    margin: 4px 10px;
}

QMenu::indicator {
    width: 14px;
    height: 14px;
    margin-left: 6px;
}

/* --- QStatusBar ---------------------------------------------------- */
QStatusBar {
    background-color: #252526;
    border-top: 1px solid #3e3e42;
    color: #d4d4d4;
    padding: 2px 6px;
}

QStatusBar::item {
    border: none;
}

QStatusBar QLabel {
    padding: 0 4px;
    color: #d4d4d4;
}

/* --- QTreeView ----------------------------------------------------- */
QTreeView {
    background-color: #1e1e1e;
    alternate-background-color: #252526;
    border: 1px solid #3e3e42;
    color: #d4d4d4;
    selection-background-color: #2a4a7a;
    selection-color: #ffffff;
    outline: none;
}

QTreeView::item {
    padding: 3px 4px;
    border: none;
}

QTreeView::item:hover {
    background-color: #2a2d2e;
}

QTreeView::item:selected {
    background-color: #2a4a7a;
    color: #ffffff;
    border: none;
}

QTreeView::item:selected:!active {
    background-color: #37373d;
    color: #d4d4d4;
}

QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {
    border-image: none;
}

QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {
    border-image: none;
}

/* --- QTableView ---------------------------------------------------- */
QTableView {
    background-color: #1e1e1e;
    alternate-background-color: #252526;
    border: 1px solid #3e3e42;
    color: #d4d4d4;
    selection-background-color: #2a4a7a;
    selection-color: #ffffff;
    gridline-color: #2d2d2d;
    outline: none;
}

QTableView::item {
    padding: 3px 6px;
    border: none;
}

QTableView::item:hover {
    background-color: #2a2d2e;
}

QTableView::item:selected {
    background-color: #2a4a7a;
    color: #ffffff;
}

QTableView::item:selected:!active {
    background-color: #37373d;
    color: #d4d4d4;
}

/* --- QHeaderView --------------------------------------------------- */
QHeaderView {
    background-color: #252526;
    border: none;
}

QHeaderView::section {
    background-color: #252526;
    color: #d4d4d4;
    padding: 5px 8px;
    border: none;
    border-right: 1px solid #3e3e42;
    border-bottom: 1px solid #3e3e42;
    font-weight: 600;
}

QHeaderView::section:hover {
    background-color: #2a4a7a;
    color: #ffffff;
}

QHeaderView::section:pressed {
    background-color: #3a78d6;
    color: #ffffff;
}

QHeaderView::down-arrow {
    subcontrol-position: center right;
    padding-right: 6px;
}

QHeaderView::up-arrow {
    subcontrol-position: center right;
    padding-right: 6px;
}

/* --- QSplitter ----------------------------------------------------- */
QSplitter::handle {
    background-color: #3e3e42;
}

QSplitter::handle:horizontal {
    width: 3px;
}

QSplitter::handle:vertical {
    height: 3px;
}

QSplitter::handle:hover {
    background-color: #3a78d6;
}

/* --- QPushButton --------------------------------------------------- */
QPushButton {
    background-color: #333337;
    border: 1px solid #3e3e42;
    border-radius: 4px;
    padding: 5px 16px;
    color: #d4d4d4;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #3a3d41;
    border: 1px solid #4a6ea9;
}

QPushButton:pressed {
    background-color: #2a4a7a;
    border: 1px solid #3a78d6;
}

QPushButton:default {
    background-color: #3a78d6;
    border: 1px solid #2a5fb0;
    color: #ffffff;
}

QPushButton:default:hover {
    background-color: #4a88e6;
    border: 1px solid #3a78d6;
}

QPushButton:default:pressed {
    background-color: #2a5fb0;
    border: 1px solid #1e4d8e;
}

QPushButton:disabled {
    background-color: #2d2d2d;
    border: 1px solid #3e3e42;
    color: #5a5a5a;
}

QPushButton:flat {
    background-color: transparent;
    border: none;
}

QPushButton:flat:hover {
    background-color: #3a3d41;
}

/* --- QLineEdit ----------------------------------------------------- */
QLineEdit {
    background-color: #2d2d2d;
    border: 1px solid #3e3e42;
    border-radius: 3px;
    padding: 4px 8px;
    color: #d4d4d4;
    selection-background-color: #2a4a7a;
    selection-color: #ffffff;
}

QLineEdit:focus {
    border: 1px solid #3a78d6;
}

QLineEdit:disabled {
    background-color: #252526;
    color: #5a5a5a;
}

QLineEdit:read-only {
    background-color: #252526;
}

/* --- QTextEdit / QPlainTextEdit ------------------------------------ */
QTextEdit, QPlainTextEdit {
    background-color: #1e1e1e;
    border: 1px solid #3e3e42;
    border-radius: 3px;
    padding: 4px;
    color: #d4d4d4;
    selection-background-color: #2a4a7a;
    selection-color: #ffffff;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #3a78d6;
}

QTextEdit:disabled, QPlainTextEdit:disabled {
    background-color: #252526;
    color: #5a5a5a;
}

/* --- QCheckBox ----------------------------------------------------- */
QCheckBox {
    color: #d4d4d4;
    spacing: 6px;
}

QCheckBox:disabled {
    color: #5a5a5a;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #3e3e42;
    border-radius: 3px;
    background-color: #2d2d2d;
}

QCheckBox::indicator:hover {
    border: 1px solid #4a6ea9;
    background-color: #3a3d41;
}

QCheckBox::indicator:checked {
    background-color: #3a78d6;
    border: 1px solid #2a5fb0;
}

QCheckBox::indicator:checked:hover {
    background-color: #4a88e6;
    border: 1px solid #3a78d6;
}

QCheckBox::indicator:disabled {
    background-color: #252526;
    border: 1px solid #333337;
}

/* --- QRadioButton -------------------------------------------------- */
QRadioButton {
    color: #d4d4d4;
    spacing: 6px;
}

QRadioButton:disabled {
    color: #5a5a5a;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #3e3e42;
    border-radius: 8px;
    background-color: #2d2d2d;
}

QRadioButton::indicator:hover {
    border: 1px solid #4a6ea9;
    background-color: #3a3d41;
}

QRadioButton::indicator:checked {
    background-color: #3a78d6;
    border: 1px solid #2a5fb0;
}

QRadioButton::indicator:checked:hover {
    background-color: #4a88e6;
    border: 1px solid #3a78d6;
}

QRadioButton::indicator:disabled {
    background-color: #252526;
    border: 1px solid #333337;
}

/* --- QTabWidget ---------------------------------------------------- */
QTabWidget::pane {
    background-color: #1e1e1e;
    border: 1px solid #3e3e42;
    border-top: none;
}

QTabWidget::tab-bar {
    alignment: left;
}

/* --- QTabBar ------------------------------------------------------- */
QTabBar {
    background-color: transparent;
    border: none;
}

QTabBar::tab {
    background-color: #2d2d2d;
    border: 1px solid #3e3e42;
    border-bottom: none;
    padding: 6px 16px;
    margin-right: 1px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    color: #d4d4d4;
}

QTabBar::tab:hover {
    background-color: #3a3d41;
}

QTabBar::tab:selected {
    background-color: #1e1e1e;
    border-bottom: 1px solid #1e1e1e;
    color: #ffffff;
    font-weight: 600;
}

QTabBar::tab:!selected {
    margin-top: 2px;
}

QTabBar::tab:disabled {
    color: #5a5a5a;
}

QTabBar::close-button {
    border: none;
    padding: 2px;
}

QTabBar::close-button:hover {
    background-color: #3a3d41;
    border-radius: 2px;
}

/* --- QGroupBox ----------------------------------------------------- */
QGroupBox {
    background-color: transparent;
    border: 1px solid #3e3e42;
    border-radius: 4px;
    margin-top: 8px;
    padding: 12px 8px 8px 8px;
    font-weight: 600;
    color: #d4d4d4;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #e0e0e0;
}

/* --- QLabel -------------------------------------------------------- */
QLabel {
    color: #d4d4d4;
    background-color: transparent;
}

QLabel:disabled {
    color: #5a5a5a;
}

/* --- QComboBox ----------------------------------------------------- */
QComboBox {
    background-color: #2d2d2d;
    border: 1px solid #3e3e42;
    border-radius: 3px;
    padding: 4px 8px;
    color: #d4d4d4;
    min-height: 20px;
}

QComboBox:hover {
    border: 1px solid #4a6ea9;
}

QComboBox:focus {
    border: 1px solid #3a78d6;
}

QComboBox:disabled {
    background-color: #252526;
    color: #5a5a5a;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 20px;
    border-left: 1px solid #3e3e42;
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
    background-color: #333337;
}

QComboBox::down-arrow {
    width: 10px;
    height: 10px;
}

QComboBox QAbstractItemView {
    background-color: #252526;
    border: 1px solid #3e3e42;
    selection-background-color: #2a4a7a;
    selection-color: #ffffff;
    outline: none;
}

/* --- QScrollBar (vertical) ----------------------------------------- */
QScrollBar:vertical {
    background-color: #1e1e1e;
    width: 12px;
    margin: 0;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #424242;
    min-height: 30px;
    border-radius: 4px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #5a5a5a;
}

QScrollBar::handle:vertical:pressed {
    background-color: #3a78d6;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
    border: none;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background-color: transparent;
}

/* --- QScrollBar (horizontal) --------------------------------------- */
QScrollBar:horizontal {
    background-color: #1e1e1e;
    height: 12px;
    margin: 0;
    border: none;
}

QScrollBar::handle:horizontal {
    background-color: #424242;
    min-width: 30px;
    border-radius: 4px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #5a5a5a;
}

QScrollBar::handle:horizontal:pressed {
    background-color: #3a78d6;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
    border: none;
}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background-color: transparent;
}

/* --- QDialog ------------------------------------------------------- */
QDialog {
    background-color: #1e1e1e;
    color: #d4d4d4;
}

/* --- QProgressBar -------------------------------------------------- */
QProgressBar {
    background-color: #2d2d2d;
    border: 1px solid #3e3e42;
    border-radius: 3px;
    text-align: center;
    color: #d4d4d4;
    height: 18px;
}

QProgressBar::chunk {
    background-color: #3a78d6;
    border-radius: 2px;
}

/* --- QToolTip ------------------------------------------------------ */
QToolTip {
    background-color: #2d2d2d;
    border: 1px solid #3e3e42;
    color: #d4d4d4;
    padding: 4px 8px;
}

/* --- QDockWidget --------------------------------------------------- */
QDockWidget {
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
    color: #d4d4d4;
}

QDockWidget::title {
    background-color: #252526;
    border: 1px solid #3e3e42;
    padding: 5px 8px;
    text-align: left;
}

QDockWidget::close-button,
QDockWidget::float-button {
    border: none;
    background-color: transparent;
    padding: 2px;
}

QDockWidget::close-button:hover,
QDockWidget::float-button:hover {
    background-color: #3a3d41;
    border-radius: 2px;
}

/* --- QSpinBox / QDoubleSpinBox ------------------------------------- */
QSpinBox, QDoubleSpinBox {
    background-color: #2d2d2d;
    border: 1px solid #3e3e42;
    border-radius: 3px;
    padding: 4px 8px;
    color: #d4d4d4;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #3a78d6;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    border-left: 1px solid #3e3e42;
    border-bottom: 1px solid #3e3e42;
    background-color: #333337;
    width: 18px;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    border-left: 1px solid #3e3e42;
    background-color: #333337;
    width: 18px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #3a3d41;
}

/* --- QSlider ------------------------------------------------------- */
QSlider::groove:horizontal {
    border: 1px solid #3e3e42;
    height: 4px;
    background-color: #2d2d2d;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background-color: #3a78d6;
    border: 1px solid #2a5fb0;
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background-color: #4a88e6;
}

/* --- Focus ring (global) ------------------------------------------- */
*:focus {
    outline: none;
}
"""
