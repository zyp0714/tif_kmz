import os
import sys
import xml.etree.ElementTree as ET
from typing import List, Tuple, Optional


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """将 #RRGGBB 或 #RRGGBBAA 转换为 (R, G, B) 整数元组"""
    hex_str = hex_str.strip().lstrip('#')
    if len(hex_str) >= 6:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return r, g, b
    elif len(hex_str) == 3:
        r = int(hex_str[0] * 2, 16)
        g = int(hex_str[1] * 2, 16)
        b = int(hex_str[2] * 2, 16)
        return r, g, b
    return 0, 0, 0


def parse_color_str(color_val: str, default_alpha: int = 255) -> Tuple[int, int, int, int]:
    """解析多样化的颜色格式（HEX、逗号分隔、带透明度）"""
    color_val = color_val.strip()
    if color_val.startswith('#'):
        r, g, b = hex_to_rgb(color_val)
        a = default_alpha
        # 如果是 8 位十六进制 (#RRGGBBAA)
        clean_hex = color_val.lstrip('#')
        if len(clean_hex) == 8:
            a = int(clean_hex[6:8], 16)
        return r, g, b, a
    elif ',' in color_val:
        parts = [int(p.strip()) for p in color_val.split(',') if p.strip().isdigit()]
        if len(parts) >= 4:
            return parts[0], parts[1], parts[2], parts[3]
        elif len(parts) >= 3:
            return parts[0], parts[1], parts[2], default_alpha
    return 0, 0, 0, default_alpha


def parse_qml_color_ramp(qml_path: str) -> List[Tuple[float, int, int, int, int]]:
    """
    解析 QGIS .qml 样式文件，提取单波段伪彩色（Singleband Pseudocolor）的阶梯色标表。

    :param qml_path: .qml 文件路径
    :return: 排序后的列表 [(value, R, G, B, Alpha), ...]
    """
    if not os.path.exists(qml_path):
        raise FileNotFoundError(f"未找到 QML 样式文件: {qml_path}")

    tree = ET.parse(qml_path)
    root = tree.getroot()

    color_entries: List[Tuple[float, int, int, int, int]] = []

    # 1. 寻找 <colorrampshader> 节点
    for cr_shader in root.iter('colorrampshader'):
        for item in cr_shader.iter('item'):
            val_str = item.get('value')
            color_str = item.get('color')
            alpha_str = item.get('alpha', '255')

            if val_str is None or color_str is None:
                continue

            try:
                val = float(val_str)
                default_alpha = int(float(alpha_str)) if alpha_str else 255
                r, g, b, a = parse_color_str(color_str, default_alpha)
                color_entries.append((val, r, g, b, a))
            except ValueError:
                continue

    # 2. 如果标准 <colorrampshader> 没找到，兼容其他可能的色卡节点
    if not color_entries:
        for item in root.iter('item'):
            val_str = item.get('value')
            color_str = item.get('color')
            if val_str and color_str:
                try:
                    val = float(val_str)
                    r, g, b, a = parse_color_str(color_str)
                    color_entries.append((val, r, g, b, a))
                except ValueError:
                    continue

    if not color_entries:
        raise ValueError(f"在样式文件 {os.path.basename(qml_path)} 中未解析到有效的栅格单波段颜色映射 (colorrampshader item)")

    # 按照数值升序排序
    color_entries.sort(key=lambda x: x[0])
    return color_entries


def generate_gdal_color_file(color_entries: List[Tuple[float, int, int, int, int]], output_txt_path: str):
    """
    将解析出的色标表生成为 GDAL DEMProcessing (color-relief) 所需的标准格式文本。

    格式示例:
      -40.0 177 62 130 255
      -30.0 212 95 52 255
      nv 0 0 0 0
    """
    lines = []
    lines.append("# GDAL color-relief table generated from QGIS QML style\n")
    for val, r, g, b, a in color_entries:
        lines.append(f"{val} {r} {g} {b} {a}\n")
    # 设置 NoData (nv) 为完全透明
    lines.append("nv 0 0 0 0\n")

    with open(output_txt_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def get_default_qml_path() -> str:
    """获取内置默认沉降样式文件的绝对路径（兼容开发环境与打包环境）"""
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    default_path = os.path.join(base_dir, 'default_subsidence.qml')
    return default_path
