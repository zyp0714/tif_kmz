import os
import sys
import tempfile
from typing import Callable, Optional, Dict, Any, List
from osgeo import gdal, osr

from qml_parser import parse_qml_color_ramp, generate_gdal_color_file, get_default_qml_path
from gpkg_analyzer import analyze_gpkg

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


def get_raster_metadata(input_tif: str) -> Dict[str, Any]:
    """
    获取栅格基础元数据信息（波段数、坐标系、数据类型等）
    """
    setup_gdal_env()
    info = {
        "band_count": 0,
        "srs_desc": "未知坐标系",
        "is_wgs84": False,
        "width": 0,
        "height": 0
    }
    try:
        ds = gdal.Open(input_tif, gdal.GA_ReadOnly)
        if ds:
            info["band_count"] = ds.RasterCount
            info["width"] = ds.RasterXSize
            info["height"] = ds.RasterYSize
            info["is_wgs84"] = is_wgs84(ds)

            proj = ds.GetProjection()
            if proj:
                srs = osr.SpatialReference()
                srs.ImportFromWkt(proj)
                auth_code = srs.GetAuthorityCode(None)
                srs_name = srs.GetName() or srs.GetAttrValue('AUTHORITY', 0)
                info["srs_desc"] = f"EPSG:{auth_code}" if auth_code else srs_name
            ds = None
    except Exception:
        pass
    return info


def convert_tif_to_kmz(
    input_tif: str,
    output_kmz: str,
    auto_reproject: bool = True,
    qml_path: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None
) -> bool:
    """
    将 GeoTIFF 转换为 KML SuperOverlay KMZ。
    支持：若为单波段 TIF，可结合 QML 样式自动内存流式着色为 RGBA 彩图后再切片。

    :param input_tif: 输入 TIF 路径
    :param output_kmz: 输出 KMZ 路径
    :param auto_reproject: 若非 EPSG:4326 是否自动重投影
    :param qml_path: 可选的 QML 样式文件路径（对单波段生效）
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
            msg = message if message else f"正在切片中... {int(complete * 100)}%"
            progress_callback(complete, msg)
        return 1  # 返回 1 继续

    src_ds = gdal.Open(input_tif, gdal.GA_ReadOnly)
    if src_ds is None:
        raise RuntimeError(f"无法读取栅格文件: {input_tif}")

    colored_ds = None
    colored_vsi_path = f"/vsimem/colored_{os.getpid()}.tif"
    temp_color_file = None

    warp_temp_ds = None
    vsimem_path = f"/vsimem/warp_temp_{os.getpid()}.tif"
    out_ds = None

    try:
        working_ds = src_ds

        # 1. 检查是否需要应用 QML 进行单波段伪彩色着色
        if src_ds.RasterCount == 1 and qml_path and os.path.exists(qml_path):
            if cancel_check and cancel_check():
                return False

            if progress_callback:
                progress_callback(0.04, f"检测到单波段数据，正在应用 QML 色标渲染: {os.path.basename(qml_path)}...")

            color_entries, ramp_type = parse_qml_color_ramp(qml_path)
            fd, temp_color_file = tempfile.mkstemp(suffix="_color.txt")
            os.close(fd)
            generate_gdal_color_file(color_entries, temp_color_file, ramp_type=ramp_type)

            dem_opts = gdal.DEMProcessingOptions(
                colorFilename=temp_color_file,
                format="GTiff",
                addAlpha=True,
                callback=gdal_progress
            )
            colored_ds = gdal.DEMProcessing(
                colored_vsi_path,
                src_ds,
                processing="color-relief",
                options=dem_opts
            )
            if cancel_check and cancel_check():
                return False
            if colored_ds is None:
                raise RuntimeError(f"QML 样式伪彩色渲染失败，请检查样式与数据是否匹配。")

            working_ds = colored_ds

        # 2. 检查是否需要重投影
        if cancel_check and cancel_check():
            return False

        need_reproject = auto_reproject and not is_wgs84(working_ds)
        if need_reproject:
            if progress_callback:
                progress_callback(0.08, "检测到非 EPSG:4326 投影，正在进行坐标纠正 (Warp)...")

            warp_options = gdal.WarpOptions(
                dstSRS="EPSG:4326",
                resampleAlg=gdal.GRA_Bilinear,
                format="GTiff",
                callback=gdal_progress
            )
            warp_temp_ds = gdal.Warp(vsimem_path, working_ds, options=warp_options)
            if cancel_check and cancel_check():
                return False
            if warp_temp_ds is None:
                raise RuntimeError("自动重投影 (EPSG:4326) 失败")
            working_ds = warp_temp_ds

        # 3. 执行 Translate 切片 SuperOverlay
        if cancel_check and cancel_check():
            return False

        if progress_callback:
            progress_callback(0.12, "开始生成 KML SuperOverlay 金字塔瓦片 (PNG)...")

        translate_options = gdal.TranslateOptions(
            format="KMLSUPEROVERLAY",
            creationOptions=["FORMAT=PNG"],
            callback=gdal_progress
        )

        out_ds = gdal.Translate(output_kmz, working_ds, options=translate_options)
        if cancel_check and cancel_check():
            return False
        if out_ds is None:
            raise RuntimeError("KMZ 生成失败，请检查数据完整性或是否手动中止。")

        # 显式释放并关闭数据集，确保文件写入完毕
        out_ds = None

        if progress_callback:
            progress_callback(1.0, "切片完成，KMZ 文件已生成。")
        return True

    finally:
        # 清理临时内存与句柄
        out_ds = None
        working_ds = None
        if warp_temp_ds is not None:
            warp_temp_ds = None
            gdal.Unlink(vsimem_path)
        if colored_ds is not None:
            colored_ds = None
            gdal.Unlink(colored_vsi_path)
        if temp_color_file and os.path.exists(temp_color_file):
            try:
                os.remove(temp_color_file)
            except Exception:
                pass
        if src_ds is not None:
            src_ds = None

        # 若中途手动中止，自动清理未完成的残余文件
        if cancel_check and cancel_check() and os.path.exists(output_kmz):
            try:
                os.remove(output_kmz)
            except Exception:
                pass


def convert_vector_to_kmz(
    input_vector: str,
    output_kmz: str,
    auto_reproject: bool = True,
    layers: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None
) -> bool:
    """
    将矢量空间数据（如 InSAR PS 散点、等值线、GPKG 矢量要素）转换为 Google Earth 矢量 KMZ。
    支持：
    - 自动空间坐标纠偏并重投影至 EPSG:4326 (WGS84)；
    - 完整保留全部业务属性字段（点编号、沉降速率、历史形变序列等）；
    - 在 Google Earth 中点击要素自动弹出属性表格（Schema / ExtendedData 卡片）；
    - 支持通过 layers 参数仅导出真实空间要素图层，自动过滤 QML 元数据表 (如 layer_styles)；
    - 支持 cancel_check 秒级平滑中断。
    """
    setup_gdal_env()

    if not os.path.exists(input_vector):
        raise FileNotFoundError(f"输入文件不存在: {input_vector}")

    if cancel_check and cancel_check():
        return False

    out_dir = os.path.dirname(os.path.abspath(output_kmz))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    if progress_callback:
        progress_callback(0.1, "正在初始化 OGR 矢量转换引擎...")

    def ogr_progress(complete, message, user_data):
        if cancel_check and cancel_check():
            return 0
        if progress_callback:
            percent = int(complete * 100)
            msg = message if message else f"正在导出矢量要素至 KMZ... {percent}%"
            progress_callback(0.1 + complete * 0.85, msg)
        return 1

    vt_options = gdal.VectorTranslateOptions(
        format="LIBKML",
        dstSRS="EPSG:4326" if auto_reproject else None,
        reproject=auto_reproject,
        layers=layers,
        callback=ogr_progress
    )

    out_ds = None
    try:
        out_ds = gdal.VectorTranslate(output_kmz, input_vector, options=vt_options)
        if cancel_check and cancel_check():
            return False
        if out_ds is None:
            raise RuntimeError(f"矢量数据转换为 KMZ 失败: {os.path.basename(input_vector)}")
        out_ds = None

        if progress_callback:
            progress_callback(1.0, "矢量要素导出完成，KMZ 文件已生成。")
        return True
    finally:
        out_ds = None
        if cancel_check and cancel_check() and os.path.exists(output_kmz):
            try:
                os.remove(output_kmz)
            except Exception:
                pass


def convert_geodata_to_kmz(
    input_file: str,
    output_kmz: str,
    auto_reproject: bool = True,
    qml_path: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None
) -> bool:
    """
    通用空间数据转 KMZ 调度入口。
    自动感知文件类型（GeoTIFF / GPKG 矢量 / GPKG 栅格）：
    - 矢量数据（如 InSAR PS 点、等值线）：调用矢量转换管道（LIBKML），保留全部属性弹窗；
    - 栅格数据（如 TIF、GPKG 栅格）：调用栅格切片管道（QML 伪彩着色 + SuperOverlay LOD 金字塔）。
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"输入文件不存在: {input_file}")

    ext = os.path.splitext(input_file)[1].lower()

    # 如果是 GeoPackage 数据库文件，通过分析引擎自动分流
    if ext == ".gpkg":
        summary = analyze_gpkg(input_file)
        spatial_layers = [vl.table_name for vl in summary.vector_layers] if summary.vector_layers else None

        if summary.primary_category == "vector":
            count = summary.vector_layers[0].feature_count if summary.vector_layers else 0
            if progress_callback:
                progress_callback(0.05, f"检测到 GPKG 矢量要素图层 (共 {count} 条)，分流至矢量管道...")
            return convert_vector_to_kmz(
                input_vector=input_file,
                output_kmz=output_kmz,
                auto_reproject=auto_reproject,
                layers=spatial_layers,
                progress_callback=progress_callback,
                cancel_check=cancel_check
            )
        elif summary.primary_category == "raster":
            # 如果存在内置 QML 样式且用户未指定外部样式，优先使用内置样式
            eff_qml = qml_path
            temp_qml_file = None
            if not eff_qml and summary.raster_layers and summary.raster_layers[0].has_embedded_qml:
                qml_text = summary.raster_layers[0].embedded_qml_content
                if qml_text:
                    fd, temp_qml_file = tempfile.mkstemp(suffix="_embedded.qml")
                    os.close(fd)
                    with open(temp_qml_file, 'w', encoding='utf-8') as f:
                        f.write(qml_text)
                    eff_qml = temp_qml_file
            try:
                if progress_callback:
                    progress_callback(0.05, "检测到 GPKG 栅格图层，分流至金字塔切片管道...")
                return convert_tif_to_kmz(
                    input_tif=input_file,
                    output_kmz=output_kmz,
                    auto_reproject=auto_reproject,
                    qml_path=eff_qml,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check
                )
            finally:
                if temp_qml_file and os.path.exists(temp_qml_file):
                    try:
                        os.remove(temp_qml_file)
                    except Exception:
                        pass
        elif summary.primary_category == "mixed":
            return convert_vector_to_kmz(
                input_vector=input_file,
                output_kmz=output_kmz,
                auto_reproject=auto_reproject,
                layers=spatial_layers,
                progress_callback=progress_callback,
                cancel_check=cancel_check
            )
        else:
            raise ValueError(f"GPKG 文件中未找到可转换的有效图层: {os.path.basename(input_file)}")

    # 默认作为栅格文件处理 (GeoTIFF 等)
    return convert_tif_to_kmz(
        input_tif=input_file,
        output_kmz=output_kmz,
        auto_reproject=auto_reproject,
        qml_path=qml_path,
        progress_callback=progress_callback,
        cancel_check=cancel_check
    )

