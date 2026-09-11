import os
import sys
import time
import tempfile
import unittest
from PySide6.QtWidgets import QApplication
from osgeo import gdal, osr
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import MainWindow
from converter import setup_gdal_env

setup_gdal_env()

def create_sample_raster(filepath: str, width: int = 400, height: int = 400):
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(filepath, width, height, 1, gdal.GDT_Float32)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    ds.SetGeoTransform([116.0, 0.0001, 0, 39.0, 0, -0.0001])
    arr = np.linspace(-30.0, 30.0, width * height, dtype=np.float32).reshape((height, width))
    ds.GetRasterBand(1).WriteArray(arr)
    ds = None


class TestFourCoreParallel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_four_core_parallel_concurrency(self):
        print("\n[4核并发测试] 验证 4 个文件同时启动、并行切片与完成...")
        window = MainWindow()

        with tempfile.TemporaryDirectory() as td:
            files = []
            for i in range(4):
                fp = os.path.join(td, f"para_test_{i}.tif")
                create_sample_raster(fp, 500, 500)
                files.append(fp)

            window.add_files(files)
            self.assertEqual(len(window.tasks), 4)

            # 启动批处理
            window.start_processing()
            self.app.processEvents()

            # 验证当前活跃并发任务数达到了 4 (4核并行)
            print(f"  -> 当前活跃并发任务数: {len(window.active_workers)} (期望: 4)")
            self.assertEqual(len(window.active_workers), 4, "4核并发池应同时启动全部 4 个任务")

            # 等待所有任务处理完成
            max_wait = 25.0
            start_t = time.time()
            while window.is_batch_running and time.time() - start_t < max_wait:
                self.app.processEvents()
                time.sleep(0.05)

            self.assertFalse(window.is_batch_running, "所有任务应在规定时间内处理完毕")
            self.assertEqual(len(window.active_workers), 0, "全部工作线程应已回收")

            for i in range(4):
                self.assertEqual(window.tasks[i].get("status"), "成功", f"任务 {i} 应处理成功")
                out_kmz = window.tasks[i]["output"]
                self.assertTrue(os.path.exists(out_kmz), f"KMZ 应已生成: {out_kmz}")
                self.assertGreater(os.path.getsize(out_kmz), 0, "KMZ 文件大小应大于 0")

            print("  [PASS] 4 核并发测试通过！4 个文件同时启动并全量成功生成 KMZ。")


if __name__ == "__main__":
    unittest.main()
