import os
import sys
import subprocess
import shutil

def find_data_dirs():
    """自动检测当前 Conda 或 Python 环境中的 gdal-data 与 proj-data 目录"""
    base_prefix = sys.prefix
    
    # 查找 PROJ 目录
    proj_candidates = [
        os.path.join(base_prefix, 'Library', 'share', 'proj'),
        os.path.join(base_prefix, 'share', 'proj'),
        os.path.join(base_prefix, 'Lib', 'site-packages', 'pyproj', 'proj_dir', 'share', 'proj')
    ]
    proj_dir = None
    for p in proj_candidates:
        if os.path.exists(p) and (os.path.exists(os.path.join(p, 'proj.db')) or os.path.exists(os.path.join(p, 'epsg'))):
            proj_dir = p
            break

    # 查找 GDAL 目录
    gdal_candidates = [
        os.path.join(base_prefix, 'Library', 'share', 'gdal'),
        os.path.join(base_prefix, 'share', 'gdal'),
        os.path.join(base_prefix, 'Lib', 'site-packages', 'osgeo', 'data', 'gdal')
    ]
    gdal_dir = None
    for g in gdal_candidates:
        if os.path.exists(g):
            gdal_dir = g
            break

    return proj_dir, gdal_dir

def purge_bloat_libraries(target_dir):
    """
    深度瘦身：自动扫描并移除被打包进来的冗余 Intel MKL 与 TBB 数学计算库 (500MB+)
    """
    internal_dir = os.path.join(target_dir, "_internal")
    scan_dir = internal_dir if os.path.exists(internal_dir) else target_dir

    if not os.path.exists(scan_dir):
        return 0

    removed_size = 0
    removed_count = 0

    # 需要剔除的冗余库前缀列表 (本项目纯做影像切片与重投影，完全不需要深度矩阵计算)
    bloat_prefixes = ("mkl_", "mkl.", "tbb", "tbbmalloc")

    for root, _, files in os.walk(scan_dir):
        for f in files:
            f_lower = f.lower()
            if f_lower.endswith(".dll") and any(f_lower.startswith(p) for p in bloat_prefixes):
                full_path = os.path.join(root, f)
                try:
                    f_size = os.path.getsize(full_path)
                    os.remove(full_path)
                    removed_size += f_size
                    removed_count += 1
                except Exception:
                    pass

    return removed_size / (1024 * 1024)

def calculate_dir_size_mb(path):
    """计算文件夹总大小 (MB)"""
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except Exception:
                pass
    return total / (1024 * 1024)

def build(onedir=True):
    """
    执行 PyInstaller 自动化打包与深度瘦身
    :param onedir: 默认为 True（便携文件夹，推荐，启动最快、最稳定），False 为单文件 EXE
    """
    # 1. 确保之前运行的测试进程已关闭，防止文件写入冲突
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/f", "/im", "tif2kmz.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    proj_dir, gdal_dir = find_data_dirs()
    print("=" * 60)
    print("正在准备打包 TIF 转 KMZ SuperOverlay 工具...")
    print(f"[*] Python 路径: {sys.executable}")
    print(f"[*] PROJ 数据目录: {proj_dir if proj_dir else '未找到(将尝试使用默认系统配置)'}")
    print(f"[*] GDAL 数据目录: {gdal_dir if gdal_dir else '未找到(将尝试使用默认系统配置)'}")
    print("=" * 60)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name=tif2kmz",
        "--windowed",            # 默认不显示黑色控制台黑框，双击直接出 UI
        "--collect-all=osgeo",   # 自动收集 osgeo 所有的 c/c++ dll 和数据
        # 排除无用的 Qt 大模块 (瘦身约 100MB)
        "--exclude-module=PySide6.QtWebEngineCore",
        "--exclude-module=PySide6.QtWebEngineWidgets",
        "--exclude-module=PySide6.QtWebEngineQuick",
        "--exclude-module=PySide6.QtQml",
        "--exclude-module=PySide6.QtQuick",
        "--exclude-module=PySide6.Qt3DCore",
        # 排除无用的科学计算包 (避免拉取 MKL)
        "--exclude-module=scipy",
        "--exclude-module=matplotlib",
        "--exclude-module=pandas",
        "--exclude-module=mkl",
        "--exclude-module=mkl_fft",
        "--exclude-module=mkl_random",
        "main.py"
    ]

    # 添加数据文件夹映射
    if proj_dir and os.path.exists(proj_dir):
        cmd.append(f"--add-data={proj_dir};share/proj")
    if gdal_dir and os.path.exists(gdal_dir):
        cmd.append(f"--add-data={gdal_dir};share/gdal")

    if onedir:
        cmd.append("--onedir")
    else:
        cmd.append("--onefile")

    print("\n执行打包命令:")
    print(" ".join(cmd))
    print("\n打包中，请稍候 1~2 分钟...\n")

    ret = subprocess.run(cmd)
    if ret.returncode == 0:
        dist_path = os.path.abspath(os.path.join("dist", "tif2kmz"))

        # 执行针对 Intel MKL 的深度瘦身规则
        if onedir and os.path.exists(dist_path):
            print("\n正在执行自动体积瘦身检查...")
            purged_mb = purge_bloat_libraries(dist_path)
            final_mb = calculate_dir_size_mb(dist_path)
            if purged_mb > 0:
                print(f"[+] 成功剔除 Intel MKL / TBB 冗余计算库: 节省 {purged_mb:.2f} MB 空间！")
            print(f"[+] 最终瘦身文件夹体积: {final_mb:.2f} MB")

        print("\n" + "=" * 60)
        print("🎉 打包成功！")
        print(f"输出目录: {dist_path}")
        print("=" * 60)
    else:
        print("\n❌ 打包过程中出现错误，请检查上方日志。")

if __name__ == "__main__":
    # 推荐使用 onedir 模式，避免每次双击单文件解压卡顿
    build(onedir=True)
