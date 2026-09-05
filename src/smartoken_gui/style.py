# Smartoken GUI 视觉主题（深色科技风 v2）
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap

# ---- 色板 ----
BG_TOP = "#0a0f1f"
BG_BOTTOM = "#101a33"
PANEL = "#151e38"            # 面板底（半透效果由 qss rgba 叠加实现）
PANEL_BORDER = "#27365c"
TEXT = "#dbe6f8"
SUB = "#8fa5cc"
ACCENT = "#38bdf8"           # 天青
ACCENT2 = "#818cf8"          # 靛紫
OK = "#34d399"
WARN = "#fbbf24"
ERR = "#f87171"
NEUTRAL = "#64748b"

QSS = f"""
* {{ font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif; outline: none; }}

QWidget#root {{
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 {BG_TOP}, stop:0.55 #0d1526, stop:1 {BG_BOTTOM});
}}
QWidget#page {{ background: transparent; }}
QWidget {{ color: {TEXT}; font-size: 13px; }}

/* ---------- 顶栏 ---------- */
QLabel#appTitle {{ font-size: 20px; font-weight: 700; color: #eaf2ff; letter-spacing: 1px; }}
QLabel#appSub {{ font-size: 11px; color: {SUB}; margin-top: 2px; }}
QFrame#statusChip {{
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.10);
  border-radius: 14px; padding: 0px;
}}
QFrame#statusChip QLabel {{ color: {SUB}; font-size: 12px; }}

/* ---------- 标签页 ---------- */
QTabWidget::pane {{ border: none; top: 6px; }}
QTabBar::tab {{
  background: transparent; color: {SUB}; padding: 8px 18px 8px 18px;
  margin-right: 6px; font-size: 13px; border-radius: 8px 8px 0 0;
}}
QTabBar::tab:selected {{
  color: #ffffff; background: rgba(56,189,248,0.12);
  border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{ color: {TEXT}; background: rgba(255,255,255,0.05); }}

/* ---------- 面板卡片 ---------- */
QGroupBox {{
  background: rgba(255,255,255,0.035); border: 1px solid {PANEL_BORDER};
  border-radius: 12px; margin-top: 10px; padding: 12px 14px 12px 14px;
}}
QGroupBox::title {{
  subcontrol-origin: margin; subcontrol-position: top left; left: 14px;
  color: #a8c6ff; font-weight: 600; font-size: 12px; background: transparent; padding: 0 6px;
}}

/* ---------- 按钮 ---------- */
QPushButton {{
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14);
  border-radius: 8px; padding: 6px 16px; color: {TEXT}; font-size: 13px;
}}
QPushButton:hover {{ background: rgba(255,255,255,0.11); border-color: rgba(56,189,248,0.6); }}
QPushButton:pressed {{ background: rgba(56,189,248,0.22); }}
QPushButton:disabled {{ color: #51607e; background: rgba(255,255,255,0.03); border-color: rgba(255,255,255,0.06); }}
QPushButton[btnType="primary"] {{
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f7cf6, stop:1 #22b8e6);
  color: #ffffff; border: none; font-weight: 600; padding: 7px 18px;
}}
QPushButton[btnType="primary"]:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3f8cff, stop:1 #38c5f0); }}
QPushButton[btnType="primary"]:disabled {{ background: rgba(56,120,240,0.35); color: rgba(255,255,255,0.75); }}
QPushButton[btnType="danger"] {{
  color: #ffb4b4; border: 1px solid rgba(248,113,113,0.45); background: rgba(248,113,113,0.08);
}}
QPushButton[btnType="danger"]:hover {{ background: rgba(248,113,113,0.2); }}
QPushButton[btnType="ghost"] {{ border: none; background: transparent; color: {SUB}; }}
QPushButton[btnType="ghost"]:hover {{ color: {ACCENT}; background: rgba(56,189,248,0.1); }}

/* ---------- 表格 ---------- */
QTableWidget {{
  background: rgba(10,16,32,0.55); border: 1px solid {PANEL_BORDER}; border-radius: 10px;
  gridline-color: transparent; alternate-background-color: rgba(255,255,255,0.025);
  selection-background-color: rgba(56,189,248,0.18); selection-color: #ffffff;
}}
QTableWidget::item {{ padding: 2px 8px; border: none; }}
QTableWidget::item:selected {{ background: rgba(56,189,248,0.18); }}
QHeaderView::section {{
  background: #101a33; color: #7f97c4; border: none;
  border-bottom: 1px solid {PANEL_BORDER}; padding: 7px 8px; font-weight: 600; font-size: 12px;
}}
QTableCornerButton::section {{ background: #101a33; border: none; }}

/* ---------- 输入 ---------- */
QLineEdit, QComboBox {{
  background: rgba(10,16,32,0.6); border: 1px solid {PANEL_BORDER}; border-radius: 8px;
  padding: 5px 10px; color: {TEXT}; selection-background-color: rgba(56,189,248,0.4);
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ width: 0; height: 0; }}
QComboBox QAbstractItemView {{
  background: #131d38; border: 1px solid {PANEL_BORDER}; border-radius: 6px;
  selection-background-color: rgba(56,189,248,0.25); selection-color: #fff; outline: none;
  padding: 4px;
}}

QLabel {{ color: {TEXT}; }}
QLabel[role="hint"] {{ color: {SUB}; font-size: 12px; }}

QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{
  width: 16px; height: 16px; border: 1px solid #3d5078; border-radius: 4px; background: #0d1730;
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
  background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #2f7cf6, stop:1 #22d3ee);
  border-color: #2f7cf6;
}}

/* ---------- 状态灯 ---------- */
QLabel[darkDot] {{ border-radius: 5px; }}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2a3b63; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #38508a; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ---------- 看板数字瓷砖 ---------- */
QFrame[tile="1"] {{
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.10); border-radius: 12px;
}}
QLabel[tileCap] {{ color: {SUB}; font-size: 11px; }}
QLabel[tileNum] {{ font-family: "Consolas","Microsoft YaHei UI"; font-size: 21px; font-weight: 700; }}
"""


def apply_theme(app) -> None:
    font = QFont("Microsoft YaHei UI")
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(QSS)


def app_icon() -> QIcon:
    size = 64
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#2f7cf6"))
    grad.setColorAt(1.0, QColor("#22d3ee"))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), 15, 15)
    f = QFont("Arial", 30, QFont.Weight.Bold)
    p.setFont(f)
    p.setPen(QColor("#ffffff"))
    p.drawText(QRect(0, 0, size, size + 2), Qt.AlignmentFlag.AlignCenter, "S")
    p.end()
    return QIcon(pm)
