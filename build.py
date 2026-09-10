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

def build(onedir=True):
    """
    执行 PyInstaller 自动化打包
    :param onedir: 默认为 True（便携文件夹，推荐，启动最快、最稳定），False 为单文件 EXE
    """
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
        "--windowed",  # 默认不显示黑色控制台黑框，双击直接出 UI
        "--collect-all=osgeo",   # 自动收集 osgeo 所有的 c/c++ dll 和数据
        "--collect-all=PySide6", # 自动收集 PySide6 插件及依赖
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
    print("\n打包过程可能需要 1~3 分钟，请稍候...\n")

    ret = subprocess.run(cmd)
    if ret.returncode == 0:
        print("\n" + "=" * 60)
        print("🎉 打包成功！")
        dist_path = os.path.abspath(os.path.join("dist", "tif2kmz"))
        print(f"输出目录: {dist_path}")
        print("=" * 60)
    else:
        print("\n❌ 打包过程中出现错误，请检查上方日志。")

if __name__ == "__main__":
    # 推荐使用 onedir 模式，避免每次双击单文件解压卡顿
    build(onedir=True)
