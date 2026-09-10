import os
import sys
import tempfile
from typing import Callable, Optional
from osgeo import gdal, osr

# 启用 GDAL 异常抛出，便于精确捕获错误
gdal.UseExceptions()


def setup_gdal_env():
    """
    自适应初始化 GDAL 和 PROJ 环境变量。
    兼容开发环境与 PyInstaller 打包环境 (_MEIPASS)。
    """
    if getattr(sys, 'frozen', False):
        # 打包环境
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        # 开发环境
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # 常见 PROJ 和 GDAL 数据目录候选项
    candidates_proj = [
        os.path.join(base_dir, 'proj_data'),
        os.path.join(base_dir, 'share', 'proj'),
        os.path.join(base_dir, 'Library', 'share', 'proj'),
        os.path.join(sys.prefix, 'Library', 'share', 'proj'),
        os.path.join(sys.prefix, 'share', 'proj'),
    ]
    candidates_gdal = [
        os.path.join(base_dir, 'gdal_data'),
        os.path.join(base_dir, 'share', 'gdal'),
        os.path.join(base_dir, 'Library', 'share', 'gdal'),
        os.path.join(sys.prefix, 'Library', 'share', 'gdal'),
        os.path.join(sys.prefix, 'share', 'gdal'),
    ]

    for p in candidates_proj:
        if os.path.exists(p):
            os.environ['PROJ_LIB'] = p
            os.environ['PROJ_DATA'] = p
            break

    for g in candidates_gdal:
        if os.path.exists(g):
            os.environ['GDAL_DATA'] = g
            break


def is_wgs84(dataset: gdal.Dataset) -> bool:
    """检查数据集是否已经是 WGS84 经纬度坐标系 (EPSG:4326)"""
    proj_wkt = dataset.GetProjection()
    if not proj_wkt:
        return False
    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj_wkt)
    # EPSG:4326 为地理坐标系，AuthCode 为 4326
    if srs.IsGeographic() and (srs.GetAuthorityCode(None) == '4326' or srs.GetAttrValue('GEOGCS') == 'WGS 84'):
        return True
    return False


def convert_tif_to_kmz(
    input_tif: str,
    output_kmz: str,
    auto_reproject: bool = True,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None
) -> bool:
    """
    将 GeoTIFF 转换为 KML SuperOverlay KMZ。
    等效于: gdal_translate -of KMLSUPEROVERLAY -co FORMAT=PNG input.tif output.kmz

    :param input_tif: 输入 TIF 路径
    :param output_kmz: 输出 KMZ 路径
    :param auto_reproject: 若非 EPSG:4326 是否自动重投影
    :param progress_callback: 进度回调函数 callback(ratio 0.0~1.0, message)
    :param cancel_check: 中止检测函数 check() -> bool
    :return: 是否成功
    """
    setup_gdal_env()

    if not os.path.exists(input_tif):
        raise FileNotFoundError(f"输入文件不存在: {input_tif}")

    out_dir = os.path.dirname(os.path.abspath(output_kmz))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    def gdal_progress(complete, message, user_data):
        if cancel_check and cancel_check():
            return 0  # 返回 0 中止 GDAL 执行
        if progress_callback:
            # complete 范围为 0.0 到 1.0
            msg = message if message else f"正在切片中... {int(complete * 100)}%"
            progress_callback(complete, msg)
        return 1  # 返回 1 继续

    src_ds = gdal.Open(input_tif, gdal.GA_ReadOnly)
    if src_ds is None:
        raise RuntimeError(f"无法读取栅格文件: {input_tif}")

    warp_temp_ds = None
    vsimem_path = f"/vsimem/warp_temp_{os.getpid()}.tif"

    try:
        working_ds = src_ds

        # 检查是否需要重投影
        need_reproject = auto_reproject and not is_wgs84(src_ds)
        if need_reproject:
            if progress_callback:
                progress_callback(0.05, "检测到非 EPSG:4326 投影，正在进行坐标纠正 (Warp)...")

            warp_options = gdal.WarpOptions(
                dstSRS="EPSG:4326",
                resampleAlg=gdal.GRA_Bilinear,
                format="GTiff"
            )
            warp_temp_ds = gdal.Warp(vsimem_path, src_ds, options=warp_options)
            if warp_temp_ds is None:
                raise RuntimeError("自动重投影 (EPSG:4326) 失败")
            working_ds = warp_temp_ds

        # 执行 Translate 切片 SuperOverlay
        if progress_callback:
            progress_callback(0.1, "开始生成 KML SuperOverlay 金字塔瓦片 (PNG)...")

        translate_options = gdal.TranslateOptions(
            format="KMLSUPEROVERLAY",
            creationOptions=["FORMAT=PNG"],
            callback=gdal_progress
        )

        out_ds = gdal.Translate(output_kmz, working_ds, options=translate_options)
        if out_ds is None:
            raise RuntimeError("KMZ 生成失败，请检查数据完整性或是否手动中止。")

        # 显式释放并关闭数据集，确保文件写入完毕
        out_ds = None

        if progress_callback:
            progress_callback(1.0, "切片完成，KMZ 文件已生成。")
        return True

    finally:
        # 清理内存与句柄
        if warp_temp_ds is not None:
            warp_temp_ds = None
            gdal.Unlink(vsimem_path)
        if src_ds is not None:
            src_ds = None
