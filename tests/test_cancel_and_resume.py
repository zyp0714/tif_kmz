import os
import sys
import time
import tempfile
import numpy as np
from osgeo import gdal, osr

# 设置环境变量与导入
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from converter import convert_geodata_to_kmz, setup_gdal_env
from PySide6.QtWidgets import QApplication
from main import MainWindow

setup_gdal_env()

def create_test_raster(path: str, width: int = 2000, height: int = 2000):
    """创建一个较大的测试栅格，以便观察中断是否秒级生效"""
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(path, width, height, 1, gdal.GDT_Float32)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    ds.SetGeoTransform([116.0, 0.001, 0, 39.0, 0, -0.001])
    band = ds.GetRasterBand(1)
    data = np.linspace(-50, 50, width * height, dtype=np.float32).reshape((height, width))
    band.WriteArray(data)
    band.FlushCache()
    ds = None

def test_instant_cancellation():
    print("\n--- 测试 1: 验证 GDAL 中断响应时间 (< 1秒) ---")
    with tempfile.TemporaryDirectory() as temp_dir:
        tif_path = os.path.join(temp_dir, "large_test.tif")
        kmz_path = os.path.join(temp_dir, "large_test.kmz")
        create_test_raster(tif_path, 3000, 3000)

        is_cancelled = False
        start_time = None
        cancel_time = None
        stop_time = None

        def cancel_check():
            nonlocal is_cancelled
            return is_cancelled

        def progress(ratio, msg):
            nonlocal is_cancelled, cancel_time
            if ratio > 0.15 and not is_cancelled:
                print(f"    [触发取消] 进度达到 {ratio*100:.1f}%: {msg}，立即触发取消...")
                cancel_time = time.time()
                is_cancelled = True

        start_time = time.time()
        success = convert_geodata_to_kmz(
            input_file=tif_path,
            output_kmz=kmz_path,
            auto_reproject=True,
            progress_callback=progress,
            cancel_check=cancel_check
        )
        stop_time = time.time()

        assert not success, "取消后函数应返回 False"
        assert not os.path.exists(kmz_path), "取消后未完成的 KMZ 成果文件应被自动清理"
        assert cancel_time is not None, "应触发了取消回调"

        elapsed_after_cancel = stop_time - cancel_time
        print(f"    [结果] 从触发取消到完全停止耗时: {elapsed_after_cancel:.3f} 秒")
        assert elapsed_after_cancel < 1.5, f"取消耗时过长: {elapsed_after_cancel}s"
        print("    [PASS] 中断响应测试通过！秒级平滑退出并完成资源回收。")

def test_breakpoint_resume():
    print("\n--- 测试 2: 验证断点续传 (跳过已成功文件，从中止处继续) ---")
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()

    with tempfile.TemporaryDirectory() as temp_dir:
        t1 = os.path.join(temp_dir, "t1.tif")
        t2 = os.path.join(temp_dir, "t2.tif")
        t3 = os.path.join(temp_dir, "t3.tif")
        create_test_raster(t1, 300, 300)
        create_test_raster(t2, 300, 300)
        create_test_raster(t3, 300, 300)

        window.add_files([t1, t2, t3])
        assert len(window.tasks) == 3

        # 模拟场景：第 0 个任务已成功完成，第 1 个任务被中止，第 2 个任务等待处理
        window.tasks[0]["status"] = "成功"
        window.table.setItem(0, 3, window.table.item(0, 3).__class__("成功"))
        window.table.setItem(0, 4, window.table.item(0, 4).__class__("已生成 KMZ"))

        window.tasks[1]["status"] = "已中止"
        window.table.setItem(1, 3, window.table.item(1, 3).__class__("已中止"))
        window.table.setItem(1, 4, window.table.item(1, 4).__class__("用户手动停止"))

        window.tasks[2]["status"] = "等待处理"

        print(f"    初始状态: [0]={window.tasks[0]['status']}, [1]={window.tasks[1]['status']}, [2]={window.tasks[2]['status']}")

        # 启动处理
        window.start_processing()

        # 验证 window.current_task_idx 是否精准定位到 1，跳过了 0
        print(f"    当前启动执行的任务索引: {window.current_task_idx} (期望: 1)")
        assert window.current_task_idx == 1, f"断点续传失败：当前任务索引应为 1，实际为 {window.current_task_idx}"

        # 等待后台任务全部执行完成
        max_wait = 15.0
        start = time.time()
        while window.is_batch_running and time.time() - start < max_wait:
            app.processEvents()
            time.sleep(0.05)

        print(f"    执行后状态: [0]={window.tasks[0]['status']}, [1]={window.tasks[1]['status']}, [2]={window.tasks[2]['status']}")
        assert window.tasks[0]["status"] == "成功", "任务 0 仍应保持成功"
        assert window.tasks[1]["status"] == "成功", "任务 1 应已断点续传并成功"
        assert window.tasks[2]["status"] == "成功", "任务 2 应已成功"
        assert not window.is_batch_running, "批处理应已完成退出"
        assert window.progress_bar.value() == 100, "进度条应为 100%"
        print("    [PASS] 断点续传测试通过！已完成文件无缝跳过，未完成任务从中止处继续成功。")

if __name__ == "__main__":
    test_instant_cancellation()
    test_breakpoint_resume()
    print("\n============================================================")
    print("[ALL TESTS PASSED] 暂停秒级停止与断点续传验证 100% 成功！")
    print("============================================================")
