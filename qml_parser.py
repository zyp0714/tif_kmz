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


import math

def parse_qml_content(xml_content: str) -> Tuple[List[Tuple[float, int, int, int, int]], str]:
    """
    解析 QML XML 字符串内容，提取单波段伪彩色的色标表及渲染模式。
    支持从文件读取或直接从 GPKG 数据库 layer_styles 字段中提取的 XML 字符串。

    :param xml_content: QML XML 文本
    :return: (排序后的列表 [(value, R, G, B, Alpha), ...], ramp_type 如 "DISCRETE" 或 "INTERPOLATED")
    """
    root = ET.fromstring(xml_content)
    color_entries: List[Tuple[float, int, int, int, int]] = []
    ramp_type = "INTERPOLATED"

    # 1. 寻找主渲染管道中的 <colorrampshader> 节点
    for cr_shader in root.iter('colorrampshader'):
        shader_type = cr_shader.get('colorRampType')
        if shader_type:
            ramp_type = shader_type.strip().upper()

        for item in cr_shader.iter('item'):
            val_str = item.get('value')
            color_str = item.get('color')
            alpha_str = item.get('alpha', '255')

            if val_str is None or color_str is None:
                continue

            try:
                # 兼容 "inf" 极端形变
                val = float(val_str)
                default_alpha = int(float(alpha_str)) if alpha_str else 255
                r, g, b, a = parse_color_str(color_str, default_alpha)
                color_entries.append((val, r, g, b, a))
            except ValueError:
                continue

        # 一旦成功解析出主着色器色标，停止后续遍历（防止重复解析 originalStyle 中的历史记录）
        if color_entries:
            break

    # 2. 如果标准 <colorrampshader> 没找到，兼容其他通用 item 节点
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
        raise ValueError("在样式内容中未解析到有效的栅格单波段颜色映射 (colorrampshader item)")

    # 按照数值升序排序
    color_entries.sort(key=lambda x: x[0])
    return color_entries, ramp_type


def parse_qml_color_ramp(qml_path: str) -> Tuple[List[Tuple[float, int, int, int, int]], str]:
    """
    解析 QGIS .qml 样式文件，提取单波段伪彩色（Singleband Pseudocolor）的色标表及渲染模式。

    :param qml_path: .qml 文件路径
    :return: (排序后的列表 [(value, R, G, B, Alpha), ...], ramp_type 如 "DISCRETE" 或 "INTERPOLATED")
    """
    if not os.path.exists(qml_path):
        raise FileNotFoundError(f"未找到 QML 样式文件: {qml_path}")

    with open(qml_path, 'r', encoding='utf-8', errors='ignore') as f:
        xml_content = f.read()

    return parse_qml_content(xml_content)


def generate_gdal_color_file(
    color_entries: List[Tuple[float, int, int, int, int]],
    output_txt_path: str,
    ramp_type: str = "INTERPOLATED"
):
    """
    将解析出的色标表生成为 GDAL DEMProcessing (color-relief) 所需的标准格式文本。
    支持：
      - DISCRETE（离散阶梯色块）：自动生成微步长区间边界，防止颜色渐变模糊，100% 还原 QGIS 阶梯图；
      - INTERPOLATED（连续线性插值）：生成平滑过渡色谱。
    """
    lines = []
    lines.append("# GDAL color-relief table generated from QGIS QML style\n")

    if ramp_type == "DISCRETE" and len(color_entries) > 1:
        # 离散色阶切片模式：
        # 第 0 级：覆盖负无穷到第 0 个阈值
        r0, g0, b0, a0 = color_entries[0][1:]
        lines.append(f"-1000000000.0 {r0} {g0} {b0} {a0}\n")
        lines.append(f"{color_entries[0][0]:.4f} {r0} {g0} {b0} {a0}\n")

        # 第 1 ~ N-1 级：从前一阈值微小偏移 (eps=0.0001) 到当前阈值
        for i in range(1, len(color_entries)):
            prev_v = color_entries[i - 1][0]
            curr_v = color_entries[i][0]
            r, g, b, a = color_entries[i][1:]

            start_v = prev_v + 0.0001
            end_v = 1000000000.0 if math.isinf(curr_v) else curr_v
            lines.append(f"{start_v:.4f} {r} {g} {b} {a}\n")
            lines.append(f"{end_v:.4f} {r} {g} {b} {a}\n")
    else:
        # 线性渐变模式
        for val, r, g, b, a in color_entries:
            val_str = "1000000000.0" if math.isinf(val) else f"{val:.4f}"
            lines.append(f"{val_str} {r} {g} {b} {a}\n")

    # 设置 NoData (nv) 为完全透明
    lines.append("nv 0 0 0 0\n")

    with open(output_txt_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def get_default_qml_path() -> str:
    """获取内置默认沉降样式文件的绝对路径（兼容开发环境与打包环境）"""
    if getattr(sys, 'frozen', False):
        base_candidates = [
            getattr(sys, '_MEIPASS', ''),
            os.path.dirname(sys.executable),
            os.path.join(os.path.dirname(sys.executable), '_internal')
        ]
        for b in base_candidates:
            if b and os.path.exists(os.path.join(b, 'default_subsidence.qml')):
                return os.path.join(b, 'default_subsidence.qml')
        return os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)), 'default_subsidence.qml')
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, 'default_subsidence.qml')
