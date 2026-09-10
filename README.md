# GeoTIFF to KMZ SuperOverlay Converter 🌍

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![GDAL](https://img.shields.io/badge/GDAL-3.8%2B-brightgreen.svg)](https://gdal.org/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)](https://doc.qt.io/qtforpython/)


一个基于 **Python + GDAL + PySide6** 的高性能遥感影像金字塔切片与 Google Earth KMZ 转换工具。

该项目完整实现了 QGIS / OSGeo4W Shell 命令的等效功能：
```bash
gdal_translate -of KMLSUPEROVERLAY -co FORMAT=PNG input.tif output.kmz
```

---

## 项目核心特性

-  **100% 官方等效**：原生调用 `osgeo.gdal.Translate`，采用 `KMLSUPEROVERLAY` 驱动与四叉树（Quadtree LOD）金字塔切片机制。
-  **投影智能校准**：Google Earth 严格基于 WGS84 经纬度（EPSG:4326）。工具内置自动投影检测与内存流重投影（`gdal.Warp`），避免非 4326 投影（如 UTM、高斯克吕格）在 Google Earth 中错位。
-  **现代双模交互**：
  - **GUI 桌面模式**：支持文件拖拽、实时进度条（0%~100%）、异步多线程防卡死、转换完毕一键定位。
  - **CLI 批处理模式**：支持终端直接传参，便于脚本自动化集成。
-  **免安装便携化打包**：自带 `build.py`，内置解决 GDAL C++ 运行时及 PROJ 数据字典打包丢失的痛点。

---

##  极速环境复现（一键安装）

由于 GDAL 含有大量底层 C/C++ 动态链接库，直接使用 `pip install gdal` 极易出现编译失败。**强烈推荐使用 Conda-forge 一键复现全部环境**：

```bash
# 1. 克隆本项目
git clone https://github.com/你的用户名/tif_kmz.git
cd tif_kmz

# 2. 从配置文件一键创建并安装完整环境 (包含 GDAL + PySide6 + PyInstaller)
conda env create -f environment.yml

# 3. 激活虚拟环境
conda activate tif_kmz
```

---

##  运行使用

### 1. 桌面图形界面 (GUI)
```bash
python main.py
```
> 直接拖拽 `.tif` 或 `.tiff` 栅格文件进窗口，点击 **开始转换** 即可。

### 2. 命令行批处理 (CLI)
```bash
# 单文件转换
python main.py -i input.tif -o output.kmz

# 若输入影像已经是 EPSG:4326，可禁用自动重投影加速转换
python main.py -i input.tif -o output.kmz --no-warp
```

---

##  打包为独立可执行程序 (EXE)

在已激活的虚拟环境中运行：
```bash
python build.py
```
打包完成后，可在 `dist/tif2kmz/` 目录下得到 `tif2kmz.exe`。该目录为**绿色免安装文件夹**，可直接打包拷贝到任何没有安装 Python、QGIS 或 Conda 的 Windows 机器上直接运行。

---

## 项目结构

```text
tif_kmz/
├── .gitignore          # Git 忽略配置（过滤 dist/build、缓存、大体积栅格数据）
├── LICENSE             # MIT 开源许可证
├── environment.yml     # Conda 环境一键复现声明（保证跨机器 100% 可复现）
├── requirements.txt    # Pip 依赖清单与备用说明
├── README.md           # 项目详细说明文档
├── converter.py        # 核心转换引擎（GDAL Translate + Warp 投影纠正）
├── main.py             # 程序主入口（PySide6 现代桌面界面 + CLI 兼容模式）
└── build.py            # 自动化打包脚本（处理 GDAL / PROJ 依赖注入）
```

---


