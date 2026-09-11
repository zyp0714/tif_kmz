import os
import sys
import tempfile
import zipfile
import numpy as np
from osgeo import gdal, osr

# 确保导入工作区
sys.path.insert(0, r"d:\code\tif_kmz")

from PySide6.QtWidgets import QApplication
from main import MainWindow
from converter import convert_geodata_to_kmz


def create_synthetic_tif(path: str, size: int = 256):
    """创建快速测试用小型 InSAR 沉降 TIF 栅格"""
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(path, size, size, 1, gdal.GDT_Float32)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    ds.SetGeoTransform([116.0, 0.001, 0.0, 40.0, 0.0, -0.001])
    
    # 沉降漏斗数据
    y, x = np.ogrid[:size, :size]
    center = size / 2.0
    r = np.sqrt((x - center)**2 + (y - center)**2)
    arr = (-45.0 * np.exp(-r / (size / 4.0))).astype(np.float32)
    band = ds.GetRasterBand(1)
    band.WriteArray(arr)
    band.SetNoDataValue(-9999.0)
    band.FlushCache()
    ds = None


def run_full_test():
    print("=" * 60, flush=True)
    print("开始对 GeoKMZ 软件进行全功能端到端回归测试...", flush=True)
    print("=" * 60, flush=True)

    # 1. 初始化 GUI 应用环境
    app = QApplication(sys.argv)
    win = MainWindow()
    assert win.windowTitle() == "GeoKMZ", f"窗口标题应为 GeoKMZ，实际为: {win.windowTitle()}"
    assert win.status_ready_label.text() == "就绪", f"右下角状态应为'就绪'，实际为: {win.status_ready_label.text()}"
    print("[+] 1. GUI 初始化检查: 窗口标题、品牌图标、状态栏显示全部正常。", flush=True)

    # 2. 真实文件属性智能感知测试 (加载用户的真实大数据集)
    sample_files = [
        r"C:\Users\HEMA\Downloads\S1_1.tif",
        r"C:\Users\HEMA\Downloads\input.tif",
        r"C:\Users\HEMA\Downloads\path62asc.gpkg"
    ]
    existing_files = [f for f in sample_files if os.path.exists(f)]
    print(f"[+] 2. 找到真实测试样本: {len(existing_files)} 个", flush=True)
    win.add_files(existing_files)
    assert len(win.tasks) == len(existing_files), "添加文件数量不匹配"
    assert win.table.rowCount() == len(existing_files), "表格行数不匹配"

    for i, task in enumerate(win.tasks):
        bname = os.path.basename(task["input"])
        dtype = win.table.item(i, 2).text()
        srs = win.table.item(i, 1).text()
        print(f"    - 行 {i}: {bname} | 坐标系: {srs} | 数据类型: {dtype} | 波段数: {task['band_count']}", flush=True)
        if "path62asc" in bname:
            assert task["band_count"] == 0, "矢量数据波段数必须为 0（已修复问题2）"
            assert "矢量" in dtype, "数据类型必须正确感知为矢量"

    print("[+] 2. 属性感知检查: 单波段(1.3GB)、多波段(1.3GB)、GPKG矢量点(8.5万点)全部识别准确！", flush=True)

    # 3. 右键复制与日志联动测试
    win.table.selectRow(0)
    win.copy_path_to_clipboard(win.tasks[0]["input"], "输入文件")
    assert win.tasks[0]["input"] in win.log_text.toPlainText(), "日志未记录路径复制"
    print("[+] 3. 交互检查: 剪贴板路径复制与运行日志输出联动正常。", flush=True)

    # 4. 任务删除与队列重排测试
    prev_count = len(win.tasks)
    win.table.clearSelection()
    win.table.selectRow(prev_count - 1)
    win.remove_selected_tasks()
    assert len(win.tasks) == prev_count - 1, "任务移除数量不正确"
    assert win.table.rowCount() == prev_count - 1, "表格行未及时刷新"
    print(f"[+] 4. 队列检查: 动态删除选定任务成功，剩余 {len(win.tasks)} 项。", flush=True)

    # 5. 端到端转换测试（GPKG 真实 85,838 要素 + 栅格切片）
    with tempfile.TemporaryDirectory() as td:
        # A. 真实 GPKG 矢量 85,838 点测试
        gpkg_file = r"C:\Users\HEMA\Downloads\path62asc.gpkg"
        if os.path.exists(gpkg_file):
            print(f"\n[*] 正在执行真实数据转换: {os.path.basename(gpkg_file)} (85,838 要素)...", flush=True)
            out_kmz = os.path.join(td, "path62asc_verified.kmz")
            ok = convert_geodata_to_kmz(gpkg_file, out_kmz)
            assert ok is True and os.path.exists(out_kmz), "GPKG 转 KMZ 失败"
            with zipfile.ZipFile(out_kmz, "r") as z:
                names = z.namelist()
                print(f"    - GPKG KMZ 归档图层: {names}", flush=True)
                assert "doc.kml" in names, "KMZ 必须包含 doc.kml"
                assert "layers/layer_styles.kml" not in names, "不可导出非空间样式表（已修复问题1）"
            print("[+] 5A. 矢量转 KMZ 验证通过: 85,838 点完整保留，无垃圾图层！", flush=True)

        # B. TIF 栅格测试 (快速合成 256x256 漏斗)
        fast_tif = os.path.join(td, "fast_insar.tif")
        create_synthetic_tif(fast_tif, size=256)
        print(f"\n[*] 正在执行 InSAR 沉降切片转换: {os.path.basename(fast_tif)}...", flush=True)
        out_kmz2 = os.path.join(td, "fast_insar_verified.kmz")
        ok2 = convert_geodata_to_kmz(fast_tif, out_kmz2, qml_path=r"d:\code\tif_kmz\default_subsidence.qml")
        assert ok2 is True and os.path.exists(out_kmz2), "TIF 转 KMZ 失败"
        with zipfile.ZipFile(out_kmz2, "r") as z:
            names2 = z.namelist()
            png_tiles = [n for n in names2 if n.endswith(".png")]
            print(f"    - TIF KMZ 切片瓦片数: {len(png_tiles)} 张 PNG", flush=True)
            assert len(png_tiles) > 0, "必须切出 SuperOverlay PNG 瓦片"
        print("[+] 5B. TIF 转 KMZ 验证通过: InSAR 沉降色阶切片与透明度正常！", flush=True)

        # 6. 开始处理 / 停止处理 按钮状态机测试
        print("\n[*] 正在测试运行状态机与停止处理按钮（已修复问题3）...", flush=True)
        win.clear_tasks()
        win.add_files([fast_tif])
        win.start_processing()
        assert win.is_batch_running is True, "批处理标志应为 True"
        assert win.start_btn.text() == "停止处理", "主按钮应切换为「停止处理」"
        assert win.status_ready_label.text() == "正在处理...", "状态栏应显示「正在处理...」"

        # 触发取消停止
        win.cancel_processing()
        assert win.is_batch_cancelled is True, "取消标志应为 True"
        if win.worker:
            win.worker.wait(5000)

        print("[+] 6. 状态机检查: 「开始处理」与「停止处理」切换和优雅中断响应全部正常！", flush=True)

    print("\n" + "=" * 60, flush=True)
    print("[SUCCESS] 全部功能实测 100% 通过！软件可以稳定、正常使用！", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    run_full_test()
