import os
import sys
import sqlite3
import tempfile
from osgeo import gdal, ogr, osr

# Ensure workspace in sys.path
sys.path.insert(0, r"d:\code\tif_kmz")

from gpkg_analyzer import analyze_gpkg


def test_gpkg_content_perception():
    with tempfile.TemporaryDirectory() as temp_dir:
        gpkg_path = os.path.join(temp_dir, "test_insar_multi.gpkg")
        
        # 1. 使用 OGR 创建一个包含矢量图层 (InSAR PS 点) 的 GPKG
        driver = ogr.GetDriverByName("GPKG")
        ds = driver.CreateDataSource(gpkg_path)
        assert ds is not None, "无法创建测试 GPKG 数据源"
        
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        
        # 创建点图层
        layer = ds.CreateLayer("insar_ps_points", srs, ogr.wkbPoint)
        layer.CreateField(ogr.FieldDefn("point_id", ogr.OFTString))
        layer.CreateField(ogr.FieldDefn("velocity_mm_yr", ogr.OFTReal))
        layer.CreateField(ogr.FieldDefn("coherence", ogr.OFTReal))
        
        # 写入 50 个模拟 PS 散点
        for i in range(50):
            feat = ogr.Feature(layer.GetLayerDefn())
            feat.SetField("point_id", f"PS_{i:04d}")
            feat.SetField("velocity_mm_yr", -25.0 + i * 0.8)
            feat.SetField("coherence", 0.75 + (i % 10) * 0.02)
            
            geom = ogr.Geometry(ogr.wkbPoint)
            geom.AddPoint(116.3 + i * 0.001, 39.9 + i * 0.001)
            feat.SetGeometry(geom)
            layer.CreateFeature(feat)
            feat = None
            
        ds = None # 释放写入
        
        # 2. 通过 SQLite 注入 layer_styles 表 (模拟 QGIS 将沉降样式保存至数据源)
        test_qml = """<!DOCTYPE qgis>
<qgis version="3.28">
  <renderer-v2 type="singleSymbol">
    <symbols><symbol type="marker"/></symbols>
  </renderer-v2>
</qgis>"""
        conn = sqlite3.connect(gpkg_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS layer_styles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                f_table_catalog TEXT,
                f_table_schema TEXT,
                f_table_name TEXT,
                f_geometry_column TEXT,
                styleName TEXT,
                styleQML TEXT,
                styleSLD TEXT,
                useAsDefault INTEGER,
                description TEXT,
                owner TEXT,
                ui TEXT
            )
        """)
        c.execute("""
            INSERT INTO layer_styles (f_table_name, styleName, styleQML, useAsDefault)
            VALUES (?, ?, ?, 1)
        """, ("insar_ps_points", "默认沉降散点样式", test_qml))
        conn.commit()
        conn.close()
        
        print(f"[+] 成功构建测试用多源 GPKG: {gpkg_path}")
        
        # 3. 运行 analyze_gpkg 进行深度扫描
        summary = analyze_gpkg(gpkg_path)
        print(f"[+] 扫描报告:")
        print(f"    文件体积: {summary.file_size_mb:.2f} MB")
        print(f"    主类别: {summary.primary_category}")
        print(f"    总图层数: {len(summary.layers)}")
        print(f"    矢量图层数: {len(summary.vector_layers)}")
        print(f"    内嵌 QML 样式表: {'存在' if summary.has_layer_styles_table else '无'} ({summary.embedded_styles_count} 套样式)")
        
        # 4. 验证断言
        assert len(summary.vector_layers) == 1, "应正确识别出 1 个矢量图层"
        v_layer = summary.vector_layers[0]
        print(f"    矢量图层名: {v_layer.table_name}")
        print(f"    几何类型: {v_layer.geom_type}")
        print(f"    要素行数: {v_layer.feature_count}")
        print(f"    字段列表: {v_layer.fields}")
        print(f"    坐标系: {v_layer.srs_desc}")
        print(f"    内嵌 QML: {'已成功提取' if v_layer.has_embedded_qml else '未找到'}")
        
        assert v_layer.geom_type == "POINT", "几何类型应为 POINT"
        assert v_layer.feature_count == 50, "要素行数应为 50"
        assert "velocity_mm_yr" in v_layer.fields, "应包含 velocity_mm_yr 字段"
        assert v_layer.is_wgs84 is True, "应识别为 WGS84"
        assert v_layer.has_embedded_qml is True, "应自动提取内嵌 QML"
        assert "<renderer-v2" in v_layer.embedded_qml_content, "QML 内容应完整提取"
        
        brief = summary.get_brief_description()
        print(f"[+] 界面紧凑回显: {brief}")
        assert "矢量POINT(50条)" in brief, "紧凑回显应包含矢量POINT(50条)"
        assert "[内置QML]" in brief, "紧凑回显应标记[内置QML]"
        
        print("\n[SUCCESS] GPKG 智能内容感知与样式提取引擎验证 100% 通过！")


if __name__ == "__main__":
    test_gpkg_content_perception()
