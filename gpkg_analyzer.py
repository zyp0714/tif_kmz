import os
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from osgeo import gdal, ogr, osr

# 启用 GDAL / OGR 异常捕获
gdal.UseExceptions()


@dataclass
class GPKGLayerInfo:
    """GPKG 内部单个图层详细元数据"""
    table_name: str
    category: str                    # 'raster' | 'vector' | 'attribute' | 'unknown'
    raw_data_type: str               # 'tiles', 'features', 'attributes', '2d-gridded-coverage'
    identifier: str = ""
    description: str = ""
    srs_id: int = 0
    srs_desc: str = "未知坐标系"     # e.g. 'EPSG:4326'
    is_wgs84: bool = False
    bounds: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # min_x, min_y, max_x, max_y
    
    # 矢量专有属性
    geom_type: Optional[str] = None  # 'POINT', 'LINESTRING', 'POLYGON', 'MULTIPOINT' 等
    feature_count: int = 0
    fields: List[str] = field(default_factory=list)
    
    # 栅格专有属性
    raster_width: int = 0
    raster_height: int = 0
    band_count: int = 0
    
    # 内嵌样式
    has_embedded_qml: bool = False
    embedded_qml_content: Optional[str] = None


@dataclass
class GPKGSummary:
    """整个 GPKG 数据集的综合分析报告"""
    file_path: str
    file_size_mb: float
    layers: List[GPKGLayerInfo] = field(default_factory=list)
    raster_layers: List[GPKGLayerInfo] = field(default_factory=list)
    vector_layers: List[GPKGLayerInfo] = field(default_factory=list)
    attribute_layers: List[GPKGLayerInfo] = field(default_factory=list)
    has_layer_styles_table: bool = False
    embedded_styles_count: int = 0
    
    @property
    def primary_category(self) -> str:
        """主分类：'raster' / 'vector' / 'mixed' / 'empty'"""
        has_r = len(self.raster_layers) > 0
        has_v = len(self.vector_layers) > 0
        if has_r and has_v:
            return "mixed"
        elif has_r:
            return "raster"
        elif has_v:
            return "vector"
        return "empty"

    def get_brief_description(self) -> str:
        """生成界面表格显示的极简紧凑描述文本"""
        if not self.layers:
            return "GPKG: 空文件或未知格式"
        
        parts = []
        if self.raster_layers:
            r = self.raster_layers[0]
            band_text = f"{r.band_count}波段" if r.band_count > 0 else "切片金字塔"
            parts.append(f"栅格({band_text})")
            
        if self.vector_layers:
            v = self.vector_layers[0]
            geom = v.geom_type or "要素"
            count_text = f"{v.feature_count}条" if v.feature_count > 0 else ""
            parts.append(f"矢量{geom}({count_text})" if count_text else f"矢量{geom}")
            
        desc = "GPKG: " + " + ".join(parts)
        if self.embedded_styles_count > 0:
            desc += " [内置QML]"
        return desc


def _query_srs_description(cursor: sqlite3.Cursor, srs_id: int) -> Tuple[str, bool]:
    """查询 GPKG 内部 gpkg_spatial_ref_sys 表获取坐标系 EPSG 代码与是否为 WGS84"""
    try:
        cursor.execute(
            "SELECT organization, organization_coordsys_id, definition FROM gpkg_spatial_ref_sys WHERE srs_id = ?",
            (srs_id,)
        )
        row = cursor.fetchone()
        if row:
            org, code, definition = row[0], row[1], row[2]
            if org and str(org).upper() == "EPSG" and code:
                auth = f"EPSG:{code}"
                is_wgs = (code == 4326)
                return auth, is_wgs
            if definition:
                srs = osr.SpatialReference()
                srs.ImportFromWkt(definition)
                auth_code = srs.GetAuthorityCode(None)
                if auth_code:
                    return f"EPSG:{auth_code}", (auth_code == "4326")
                name = srs.GetName() or "自定义坐标系"
                return name, False
    except Exception:
        pass
    return "未知坐标系", False


def _check_embedded_qml(cursor: sqlite3.Cursor, table_name: str) -> Tuple[bool, Optional[str]]:
    """检测并提取特定图层保存在 GPKG layer_styles 表中的 QML 样式"""
    try:
        # 检查 layer_styles 表是否存在
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='layer_styles'"
        )
        if not cursor.fetchone():
            return False, None
            
        cursor.execute(
            "SELECT styleQML FROM layer_styles WHERE f_table_name = ? ORDER BY useAsDefault DESC, id DESC LIMIT 1",
            (table_name,)
        )
        row = cursor.fetchone()
        if row and row[0]:
            return True, row[0]
            
        # 若没有精确匹配表名，检查是否有任意通用默认样式
        cursor.execute("SELECT styleQML FROM layer_styles ORDER BY useAsDefault DESC LIMIT 1")
        row = cursor.fetchone()
        if row and row[0]:
            return True, row[0]
    except Exception:
        pass
    return False, None


def analyze_gpkg(gpkg_path: str) -> GPKGSummary:
    """
    全面深度扫描 GPKG 文件，自动分析内部所有图层（栅格/矢量/属性/内嵌样式）。
    
    :param gpkg_path: .gpkg 文件路径
    :return: GPKGSummary 汇总对象
    """
    if not os.path.exists(gpkg_path):
        raise FileNotFoundError(f"未找到 GPKG 文件: {gpkg_path}")
        
    f_size_mb = os.path.getsize(gpkg_path) / (1024 * 1024)
    summary = GPKGSummary(file_path=gpkg_path, file_size_mb=f_size_mb)
    
    # 1. 采用原生 SQLite 快速安全探测元数据表 (只读连接)
    uri_path = f"file:{os.path.abspath(gpkg_path)}?mode=ro"
    conn = sqlite3.connect(uri_path, uri=True)
    cursor = conn.cursor()
    
    # 检查是否有 layer_styles 表
    try:
        cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='layer_styles'")
        has_styles = cursor.fetchone()[0] > 0
        summary.has_layer_styles_table = has_styles
        if has_styles:
            cursor.execute("SELECT count(*) FROM layer_styles")
            summary.embedded_styles_count = cursor.fetchone()[0]
    except Exception:
        pass
        
    # 查询 gpkg_contents 核心图层注册表
    try:
        cursor.execute("""
            SELECT table_name, data_type, identifier, description, srs_id, min_x, min_y, max_x, max_y
            FROM gpkg_contents
        """)
        contents_rows = cursor.fetchall()
    except Exception:
        contents_rows = []
        
    for row in contents_rows:
        t_name, d_type, ident, desc, srs_id, min_x, min_y, max_x, max_y = row
        d_type_lower = (d_type or "").lower()
        
        srs_desc, is_wgs84 = _query_srs_description(cursor, srs_id)
        has_qml, qml_content = _check_embedded_qml(cursor, t_name)
        
        bounds = (
            float(min_x or 0.0),
            float(min_y or 0.0),
            float(max_x or 0.0),
            float(max_y or 0.0)
        )
        
        layer_info = GPKGLayerInfo(
            table_name=t_name,
            category="unknown",
            raw_data_type=d_type,
            identifier=ident or t_name,
            description=desc or "",
            srs_id=srs_id or 0,
            srs_desc=srs_desc,
            is_wgs84=is_wgs84,
            bounds=bounds,
            has_embedded_qml=has_qml,
            embedded_qml_content=qml_content
        )
        
        # A. 栅格类型判断: tiles 或 2d-gridded-coverage
        if "tile" in d_type_lower or "coverage" in d_type_lower or "grid" in d_type_lower:
            layer_info.category = "raster"
            # 进一步通过 GDAL 探查切片尺寸与波段数
            try:
                ds = gdal.Open(f"GPKG:{gpkg_path}:{t_name}", gdal.GA_ReadOnly)
                if ds:
                    layer_info.raster_width = ds.RasterXSize
                    layer_info.raster_height = ds.RasterYSize
                    layer_info.band_count = ds.RasterCount
                    ds = None
            except Exception:
                # 兼容直接通过主库打开
                try:
                    ds = gdal.Open(gpkg_path, gdal.GA_ReadOnly)
                    if ds:
                        layer_info.raster_width = ds.RasterXSize
                        layer_info.raster_height = ds.RasterYSize
                        layer_info.band_count = ds.RasterCount
                        ds = None
                except Exception:
                    pass
            summary.raster_layers.append(layer_info)
            
        # B. 矢量类型判断: features
        elif "feature" in d_type_lower:
            layer_info.category = "vector"
            # 查询 gpkg_geometry_columns 获取具体几何类型 (Point/Line/Polygon)
            try:
                cursor.execute(
                    "SELECT geometry_type_name FROM gpkg_geometry_columns WHERE table_name = ?",
                    (t_name,)
                )
                geom_row = cursor.fetchone()
                if geom_row and geom_row[0]:
                    layer_info.geom_type = geom_row[0].upper()
            except Exception:
                pass
                
            # 统计要素总行数
            try:
                cursor.execute(f'SELECT count(*) FROM "{t_name}"')
                layer_info.feature_count = cursor.fetchone()[0]
            except Exception:
                pass
                
            # 获取字段列表
            try:
                cursor.execute(f'PRAGMA table_info("{t_name}")')
                cols = cursor.fetchall()
                layer_info.fields = [c[1] for c in cols if c[1] != "geom" and c[1] != "geometry"]
            except Exception:
                pass
                
            summary.vector_layers.append(layer_info)
            
        # C. 纯属性表
        elif "attribute" in d_type_lower:
            layer_info.category = "attribute"
            summary.attribute_layers.append(layer_info)
            
        summary.layers.append(layer_info)
        
    conn.close()
    return summary
