import os
import sys
import zipfile
import numpy as np
from osgeo import gdal, osr

# Ensure workspace is in sys.path
sys.path.insert(0, r"d:\code\tif_kmz")

from converter import convert_tif_to_kmz, get_raster_metadata
from qml_parser import get_default_qml_path

import tempfile

def test_single_band_insar_kmz():
    with tempfile.TemporaryDirectory() as temp_dir:
        tif_path = os.path.join(temp_dir, "synthetic_insar_subsidence.tif")
        kmz_path = os.path.join(temp_dir, "synthetic_insar_subsidence.kmz")
        
        # 1. 创建合成 InSAR 沉降数据 (512x512, float32, -50mm ~ +30mm)
        width = 512
        height = 512
        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(tif_path, width, height, 1, gdal.GDT_Float32)
        
        # 坐标范围: 经度 116.0 ~ 116.5, 纬度 39.5 ~ 40.0 (北京附近 WGS84)
        ds.SetGeoTransform([116.0, 0.5 / width, 0, 40.0, 0, -0.5 / height])
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        ds.SetProjection(srs.ExportToWkt())
        
        # 生成梯度沉降漏斗 (中心严重沉降 -45mm, 外围稳定 0mm, 右上抬升 +25mm)
        x = np.linspace(-1, 1, width)
        y = np.linspace(-1, 1, height)
        xx, yy = np.meshgrid(x, y)
        r = np.sqrt(xx**2 + yy**2)
        
        # 沉降漏斗: -45 * exp(-3*r^2) + 抬升项 20 * xx
        data = -45.0 * np.exp(-3 * (r**2)) + 20.0 * xx
        
        # 边缘加入 NoData (-9999.0)
        nodata_val = -9999.0
        data[r > 0.95] = nodata_val
        
        band = ds.GetRasterBand(1)
        band.SetNoDataValue(nodata_val)
        band.WriteArray(data.astype(np.float32))
        band.FlushCache()
        ds = None
        
        print(f"[+] 成功生成模拟单波段 InSAR 栅格: {tif_path}")
        print(f"    数值范围: {np.min(data[data != nodata_val]):.1f} mm ~ {np.max(data[data != nodata_val]):.1f} mm")
        
        # 2. 检查元数据
        meta = get_raster_metadata(tif_path)
        print(f"[+] 栅格元数据: 波段数={meta['band_count']}, 坐标系={meta['srs_desc']}, 尺寸={meta['width']}x{meta['height']}")
        assert meta['band_count'] == 1, "应该为单波段数据"
        
        # 3. 执行转换并加载默认 QML 色标
        default_qml = get_default_qml_path()
        print(f"[+] 使用内置 QML 样式文件: {default_qml}")
        assert os.path.exists(default_qml), "内置 QML 文件必须存在"
        
        def log_progress(ratio, msg):
            print(f"    [Progress {int(ratio*100)}%] {msg}")
            
        success = convert_tif_to_kmz(
            input_tif=tif_path,
            output_kmz=kmz_path,
            auto_reproject=True,
            qml_path=default_qml,
            progress_callback=log_progress
        )
        
        assert success, "convert_tif_to_kmz 必须返回 True"
        assert os.path.exists(kmz_path), "输出 KMZ 文件必须存在"
        kmz_size = os.path.getsize(kmz_path)
        print(f"[+] KMZ 成功生成! 文件大小: {kmz_size / 1024:.2f} KB")
        
        # 4. 验证 KMZ 内部结构
        with zipfile.ZipFile(kmz_path, 'r') as z:
            file_list = z.namelist()
            print(f"[+] KMZ 内部包含 {len(file_list)} 个文件/瓦片")
            assert "doc.kml" in file_list, "KMZ 必须包含根 doc.kml"
            png_tiles = [f for f in file_list if f.endswith('.png')]
            print(f"[+] KMZ 包含 {len(png_tiles)} 个 PNG 瓦片: {png_tiles[:5]}...")
            assert len(png_tiles) > 0, "KMZ 必须包含渲染切片 PNG 瓦片"
            
        print("\n[SUCCESS] 目标一：单波段 InSAR 沉降 TIF + QML 自动着色切片全链路验证通过！")

if __name__ == "__main__":
    test_single_band_insar_kmz()
