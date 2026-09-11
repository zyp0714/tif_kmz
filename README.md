# GeoKMZ - 地理数据转 KMZ SuperOverlay 转换工具

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![GDAL](https://img.shields.io/badge/GDAL-3.8%2B-brightgreen.svg)](https://gdal.org/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)](https://doc.qt.io/qtforpython/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**GeoKMZ** 是一个基于 **Python + GDAL + PySide6** 的高性能地理数据（TIF 影像栅格 / GPKG 矢量点面）与 Google Earth KMZ 金字塔/多层级矢量转换工具。

该项目完整实现了 QGIS / OSGeo4W Shell 命令的等效功能：
```bash
gdal_translate -of KMLSUPEROVERLAY -co FORMAT=PNG input.tif output.kmz
```

---

## 项目核心特性

- **100% 官方等效**：原生调用 `osgeo.gdal.Translate`，采用 `KMLSUPEROVERLAY` 驱动与四叉树（Quadtree LOD）金字塔切片机制。
- **单波段 InSAR 沉降自动着色（脱离 QGIS）**：
  - 支持单波段浮点/整型栅格数据（如 InSAR 年均沉降速率、形变量、DEM 高程）。
  - 内置标准 Sentinel-1 InSAR 沉降色阶（`-40mm` 至 `>+40mm`，`[-10, 10]` 稳定区浅绿，深红沉降，深蓝抬升）。
  - 支持直接加载 QGIS 导出的自定义 `.qml` 样式文件。
  - 通过 `gdal.DEMProcessing` 在内存流中直接生成带 Alpha 通道的 RGBA 彩图，切片并保留 NoData 完全透明。
- **投影智能校准**：Google Earth 严格基于 WGS84 经纬度（EPSG:4326）。工具内置自动投影检测与内存流重投影（`gdal.Warp`），避免非 4326 投影在 Google Earth 中错位。
- **工业级桌面交互**：
  - 支持单文件或批量多选/拖拽排队切片。
  - 栅格属性智能感知（自动检测单波段/多波段、坐标系）。
  - 支持自定义统一输出目录，内置严格去重保护。
  - 异步多线程防界面卡死，双击结果行一键定位成果文件。
- **免安装便携化打包**：自带 `build.py`，内置解决 GDAL C++ 运行时、PROJ 数据字典及 Intel MKL 深度瘦身（包体积优化 500MB+）。

---

## 极速环境复现（一键安装）

由于 GDAL 含有大量底层 C/C++ 动态链接库，直接使用 `pip install gdal` 极易出现编译失败。**强烈推荐使用 Conda-forge 一键复现全部环境**：

```bash
# 1. 克隆本项目
git clone https://github.com/zyp0714/tif_kmz.git
cd tif_kmz

# 2. 从配置文件一键创建并安装完整环境 (包含 GDAL + PySide6 + PyInstaller)
conda env create -f environment.yml

# 3. 激活虚拟环境
conda activate tif_kmz
```

---

## 运行使用

### 1. 桌面图形界面 (GUI)
```bash
python main.py
```
> 点击「添加文件」或直接批量拖拽 `.tif` / `.tiff` 文件进入列表。单波段沉降数据可选择「[默认] InSAR 沉降标准色标」或「自定义 QML 样式文件」，设定输出目录后点击 **开始处理** 即可。

### 2. 命令行批处理 (CLI)
```bash
# 单文件转换（单波段默认自动启用内置 InSAR 沉降色标）
python main.py -i input.tif -o output.kmz

# 指定自定义 QGIS QML 样式文件
python main.py -i input.tif -o output.kmz -q my_style.qml

# 若输入影像已经是 EPSG:4326，可禁用自动重投影加速转换
python main.py -i input.tif -o output.kmz --no-warp
```

---

## 打包为独立可执行程序 (EXE)

在已激活的虚拟环境中运行：
```bash
python build.py
```
打包完成后，可在 `dist/GeoKMZ/` 目录下得到 `GeoKMZ.exe` 绿色免安装运行文件夹，可直接打包拷贝到任何没有安装 Python、QGIS 或 Conda 的 Windows 机器上直接运行。

---

## 项目结构

```text
tif_kmz/
├── .gitignore               # Git 忽略配置（过滤 dist/build、缓存、大体积栅格数据）
├── LICENSE                  # MIT 开源许可证
├── environment.yml          # Conda 环境一键复现声明（保证跨机器 100% 可复现）
├── requirements.txt         # Pip 依赖清单与备用说明
├── README.md                # 项目详细说明文档
├── default_subsidence.qml   # 内置 Sentinel-1 InSAR 标准沉降色标 (-40mm ~ +40mm)
├── qml_parser.py            # QGIS .qml 样式解析器与 GDAL 颜色映射转换引擎
├── converter.py             # 核心转换引擎（GDAL Translate + Warp + QML 伪彩色着色）
├── main.py                  # 程序主入口（PySide6 现代桌面界面 + CLI 兼容模式）
└── build.py                 # 自动化打包脚本（处理 GDAL / PROJ 依赖注入与 MKL 瘦身）
```
