# -*- coding: utf-8 -*-
"""
GeoKMZ 系统外设与通用工具函数
包含图标解析、文件管理器高亮与剪贴板操作
"""

import os
import sys
import subprocess
from typing import Optional
from PySide6.QtGui import QIcon, QGuiApplication
from PySide6.QtWidgets import QMessageBox, QWidget


def get_app_icon() -> QIcon:
    """获取程序主图标（兼容开发环境与 PyInstaller 打包环境）"""
    if getattr(sys, 'frozen', False):
        base_candidates = [
            getattr(sys, '_MEIPASS', ''),
            os.path.dirname(sys.executable),
            os.path.join(os.path.dirname(sys.executable), '_internal')
        ]
    else:
        base_candidates = [
            os.path.dirname(os.path.abspath(__file__))
        ]

    for b in base_candidates:
        if not b:
            continue
        for name in ("logo.ico", "logo.png", "logo.svg"):
            p = os.path.join(b, name)
            if os.path.exists(p):
                icon = QIcon(p)
                if not icon.isNull():
                    return icon
    return QIcon()


def locate_file_in_explorer(file_path: str, is_output: bool = True, parent: Optional[QWidget] = None) -> bool:
    """
    在操作系统文件资源管理器中定位并高亮选中目标文件。
    :param file_path: 文件绝对路径
    :param is_output: 是否为成果文件（影响提示文字）
    :param parent: 提示弹窗父窗口句柄
    :return: 是否成功调起资源管理器
    """
    target_name = "KMZ 成果" if is_output else "源文件"
    if not file_path or not os.path.exists(file_path):
        if parent:
            QMessageBox.information(parent, "提示", f"该{target_name}尚未生成或已被移除：\n{file_path}")
        return False

    abs_path = os.path.abspath(file_path)
    try:
        if sys.platform == "win32":
            subprocess.Popen(f'explorer /select,"{abs_path}"')
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(abs_path)])
        return True
    except Exception as e:
        if parent:
            QMessageBox.warning(parent, "错误", f"无法打开资源管理器: {e}")
        return False


def copy_text_to_clipboard(text: str) -> None:
    """将文本复制到系统剪贴板"""
    clipboard = QGuiApplication.clipboard()
    clipboard.setText(text)
