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

def build(onedir=False):
    """
    执行 PyInstaller 自动化打包与深度瘦身
    :param onedir: True 为文件夹目录，False 为极致轻量化单文件可执行程序 (单个 GeoKMZ.exe)
    """
    # 1. 确保之前运行的测试进程已关闭，防止文件写入冲突
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/f", "/im", "GeoKMZ.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["taskkill", "/f", "/im", "tif2kmz.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    base_prefix = sys.prefix
    library_bin = os.path.join(base_prefix, 'Library', 'bin')
    conda_paths = [
        base_prefix,
        os.path.join(base_prefix, 'Library', 'mingw-w64', 'bin'),
        os.path.join(base_prefix, 'Library', 'usr', 'bin'),
        library_bin,
        os.path.join(base_prefix, 'Scripts'),
        os.path.join(base_prefix, 'bin')
    ]
    # 确保 Conda DLL 路径注入到当前进程 PATH 中
    existing_path = os.environ.get("PATH", "")
    for cp in reversed(conda_paths):
        if os.path.exists(cp) and cp.lower() not in existing_path.lower():
            existing_path = cp + os.pathsep + existing_path
    os.environ["PATH"] = existing_path

    proj_dir, gdal_dir = find_data_dirs()
    print("=" * 60)
    mode_desc = "单文件独立绿色可执行程序 (Single File EXE)" if not onedir else "便携文件夹 (OneDir)"
    print(f"正在准备打包 GeoKMZ 转换工具 [{mode_desc}]...")
    print(f"[*] Python 路径: {sys.executable}")
    print(f"[*] Conda Library 路径: {library_bin}")
    print(f"[*] PROJ 数据目录: {proj_dir if proj_dir else '未找到'}")
    print(f"[*] GDAL 数据目录: {gdal_dir if gdal_dir else '未找到'}")
    print("=" * 60)

    # 格式化路径给 spec 文件使用
    library_bin_spec = library_bin.replace('\\', '/')
    proj_dir_spec = proj_dir.replace('\\', '/') if proj_dir else ""
    gdal_dir_spec = gdal_dir.replace('\\', '/') if gdal_dir else ""

    datas_list = [
        ("default_subsidence.qml", "."),
        ("logo.ico", "."),
        ("logo.png", "."),
        ("logo.svg", "."),
    ]
    if proj_dir_spec:
        datas_list.append((proj_dir_spec, "share/proj"))
    if gdal_dir_spec:
        datas_list.append((gdal_dir_spec, "share/gdal"))

    # 动态生成经过精细裁剪、彻底剔除冗余依赖的 Spec 文件
    # 彻底杜绝 Intel MKL (500MB+)、TBB、Tkinter、OpenBLAS 等无关库被压缩进单文件
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_all

datas = {repr(datas_list)}
binaries = []
hiddenimports = []
binaries += collect_dynamic_libs('shiboken6')
binaries += collect_dynamic_libs('PySide6')
tmp_ret = collect_all('osgeo')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# 深度白名单/黑名单过滤：彻底剔除不需要的冗余动态库 (MKL, TBB, Tkinter, MPI 等 500MB+ 冗余)
bloat_prefixes = (
    'mkl_', 'mkl.', 'tbb', 'tbbmalloc',
    'msmpi', 'impi', 'tk86', 'tcl86',
    'libblas', 'libcblas', 'liblapack'
)
binaries = [b for b in binaries if not any(os.path.basename(b[0]).lower().startswith(p) for p in bloat_prefixes)]

a = Analysis(
    ['main.py'],
    pathex=['{library_bin_spec}'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.Qt3DCore', 'PySide6.QtDesigner',
        'PySide6.QtBluetooth', 'PySide6.QtSensors', 'PySide6.QtNfc', 'PySide6.QtPositioning',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtSpatialAudio',
        'PySide6.QtQuickWidgets', 'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtCharts',
        'numpy', 'osgeo.gdalnumeric', 'scipy', 'matplotlib', 'pandas',
        'mkl', 'mkl_fft', 'mkl_random',
        'tkinter', '_tkinter', 'turtle', 'doctest', 'unittest', 'test'
    ],
    noarchive=False,
    optimize=1,
)

# 二次深度清洗 Analysis 阶段可能通过其他模块间接引入的冗余二进制文件
a.binaries = [b for b in a.binaries if not any(os.path.basename(b[0]).lower().startswith(p) for p in bloat_prefixes)]

pyz = PYZ(a.pure)
'''

    if not onedir:
        # 单文件打包架构 (Single EXE)
        spec_content += '''
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GeoKMZ',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo.ico'],
)
'''
    else:
        # 文件夹打包架构 (OneDir)
        spec_content += '''
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GeoKMZ',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GeoKMZ',
)
'''

    with open("GeoKMZ.spec", "w", encoding="utf-8") as f:
        f.write(spec_content)

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "GeoKMZ.spec"]
    print("\n执行精简打包命令:")
    print(" ".join(cmd))
    print("\n打包中，请稍候 1~2 分钟...\n")

    ret = subprocess.run(cmd)
    if ret.returncode == 0:
        if not onedir:
            out_exe = os.path.abspath(os.path.join("dist", "GeoKMZ.exe"))
            exe_size_mb = os.path.getsize(out_exe) / (1024 * 1024) if os.path.exists(out_exe) else 0
            print("\n" + "=" * 60)
            print("[SUCCESS] 单文件可执行程序打包成功！")
            print(f"[+] 目标单文件: {out_exe}")
            print(f"[+] 单文件总大小: {exe_size_mb:.2f} MB (已剔除所有无关库与 500MB+ MKL 冗余)")
            print("=" * 60)
        else:
            dist_path = os.path.abspath(os.path.join("dist", "GeoKMZ"))
            print("\n正在执行自动体积瘦身检查...")
            purged_mb = purge_bloat_libraries(dist_path)
            final_mb = calculate_dir_size_mb(dist_path)
            if purged_mb > 0:
                print(f"[+] 成功剔除 Intel MKL / TBB 冗余计算库: 节省 {purged_mb:.2f} MB 空间！")
            print(f"[+] 最终瘦身文件夹体积: {final_mb:.2f} MB")
            print("\n" + "=" * 60)
            print("[SUCCESS] 便携文件夹打包成功！")
            print(f"输出目录: {dist_path}")
            print("=" * 60)
    else:
        print("\n[ERROR] 打包过程中出现错误，请检查上方日志。")

if __name__ == "__main__":
    # 用户指定打包成单文件 (onefile=True) 并删除所有不必要的库
    build(onedir=False)

