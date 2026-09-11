# -*- coding: utf-8 -*-
"""
GeoKMZ UI 样式表定义
包含现代工业/专业 GIS 风格的 QSS 配置
"""

APP_STYLE = """
    QMainWindow {
        background-color: #f8fafc;
    }
    QWidget {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    QFrame#cardFrame {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
    }
    QLabel#headerTitle {
        font-size: 20px;
        font-weight: 700;
        color: #0f172a;
    }
    QLabel#headerSubTitle {
        font-size: 12px;
        color: #64748b;
    }
    QLabel#sectionTitle {
        font-size: 13px;
        font-weight: 600;
        color: #1e293b;
    }
    QLabel#statusTag {
        font-size: 12px;
        color: #64748b;
    }
    QLineEdit {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 12px;
        color: #1e293b;
    }
    QLineEdit:focus {
        border-color: #3b82f6;
    }
    QComboBox {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 12px;
        color: #1e293b;
        min-width: 280px;
    }
    QComboBox:focus {
        border-color: #3b82f6;
    }
    QPushButton#primaryBtn {
        background-color: #3b82f6;
        color: #ffffff;
        font-size: 13px;
        font-weight: 500;
        border: none;
        border-radius: 4px;
        padding: 6px 16px;
        min-height: 20px;
    }
    QPushButton#primaryBtn:hover {
        background-color: #2563eb;
    }
    QPushButton#primaryBtn:pressed {
        background-color: #1d4ed8;
    }
    QPushButton#primaryBtn:disabled {
        background-color: #94a3b8;
    }
    QPushButton#dangerBtn {
        background-color: #ef4444;
        color: #ffffff;
        font-size: 13px;
        font-weight: 500;
        border: none;
        border-radius: 4px;
        padding: 6px 16px;
        min-height: 20px;
    }
    QPushButton#dangerBtn:hover {
        background-color: #dc2626;
    }
    QPushButton#dangerBtn:pressed {
        background-color: #b91c1c;
    }
    QPushButton#secondaryBtn {
        background-color: #ffffff;
        color: #475569;
        font-size: 12px;
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        padding: 4px 12px;
    }
    QPushButton#secondaryBtn:hover {
        background-color: #f1f5f9;
        color: #1e293b;
    }
    QProgressBar {
        border: 1px solid #e2e8f0;
        border-radius: 3px;
        background-color: #edf2f7;
        height: 10px;
        text-align: center;
        font-size: 9px;
    }
    QProgressBar::chunk {
        background-color: #3b82f6;
        border-radius: 2px;
    }
    QTableWidget {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 4px;
        gridline-color: #f1f5f9;
        font-size: 12px;
        color: #334155;
    }
    QTableWidget::item {
        padding: 4px 8px;
    }
    QTableWidget::item:selected {
        background-color: #eff6ff;
        color: #1e40af;
    }
    QHeaderView::section {
        background-color: #f8fafc;
        color: #475569;
        font-size: 12px;
        font-weight: 600;
        border: none;
        border-bottom: 1px solid #e2e8f0;
        padding: 6px 8px;
    }
    QTextEdit#logBox {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 4px;
        font-family: "Consolas", "Courier New", monospace;
        font-size: 11px;
        color: #475569;
        padding: 6px;
    }
    QCheckBox {
        font-size: 12px;
        color: #475569;
    }
    QStatusBar {
        background-color: #ffffff;
        border-top: 1px solid #e2e8f0;
        font-size: 11px;
        color: #64748b;
    }
    QMenu {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 20px 6px 12px;
        font-size: 12px;
        color: #1e293b;
        border-radius: 4px;
    }
    QMenu::item:selected {
        background-color: #f1f5f9;
        color: #0f172a;
    }
    QMenu::item:disabled {
        color: #94a3b8;
    }
    QMenu::separator {
        height: 1px;
        background-color: #e2e8f0;
        margin: 4px 6px;
    }
"""

def get_app_stylesheet() -> str:
    """获取程序主界面全局 QSS 样式表"""
    return APP_STYLE
