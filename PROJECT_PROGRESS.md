# GeoTIFF / GPKG to KMZ 项目开发进度与技术交接文档

> **创建时间**：2026-09-10  
> **代码仓库**：[https://github.com/zyp0714/tif_kmz.git](https://github.com/zyp0714/tif_kmz.git) (分支: `main`)  
> **运行环境**：Conda 虚拟环境 `tif_kmz` (Python 3.12, GDAL 3.13.3, PySide6 6.11.2, PyInstaller 6.22.2)  
> **环境路径**：`D:\Miniconda3\envs\tif_kmz\python.exe`  
> **核心硬性规范**：
> 1. **代码保存与同步**：每一次修改完代码后，必须保存到本地仓库并立即 `git push` 到 GitHub `origin/main`。
> 2. **UI 风格与视觉**：严禁出现任何 Emoji 表情符号，采用工业级浅色卡片风格；Windows 10/11 窗口强制浅色/白底标题栏（通过 DWMAPI 与 `QT_QPA_PLATFORM="windows:darkmode=0"` 注入）。

---

## 一、项目已完成工作 (Milestone 1：目标一已完结)

### 1. 单波段 InSAR 沉降 TIF + QML 自动着色切片管道
- **脱离 QGIS 平台**：实现了单波段栅格在纯 Python + GDAL 环境下的全自动色彩渲染与 SuperOverlay 切片，无需启动 QGIS。
- **内存流渲染 (`converter.py`)**：
  - 单波段栅格感知：自动检测 `RasterCount == 1`；
  - 虚拟内存文件 (`/vsimem/`)：调用 `gdal.DEMProcessing(..., processing="color-relief")` 直接生成带透明度（Alpha）的 4 通道 RGBA 影像，不产生中间磁盘大文件；
  - 自动投影纠正：遇到非 EPSG:4326（如 UTM、高斯克吕格投影），自动通过 `gdal.Warp` 流式重投影至 WGS84；
  - 金字塔瓦片生成：调用 `gdal.Translate(..., format="KMLSUPEROVERLAY", creationOptions=["FORMAT=PNG"])`，生成四叉树 LOD 金字塔与 `doc.kml`，空值区域（NoData）完全透明无黑边。

### 2. QML 样式解析与离散阶梯映射 (`qml_parser.py`)
- **XML 原生解析**：解析 QGIS 样式中的 `<colorrampshader>` 节点。
- **离散阶梯色标支持 (Discrete)**：
  - 自动识别 `colorRampType="DISCRETE"`，自动生成微步长区间分界（`eps=0.0001`），避免渐变过渡模糊，100% 还原 QGIS 离散分段色块效果；
  - 同时向下兼容 `INTERPOLATED`（平滑渐变插值）。
- **去重与边界防护**：
  - 自动在主着色管道 `<pipe>` 提取完毕后中断遍历，防止重复解析 QGIS 历史记录 `<originalStyle>`；
  - 兼容 `value="inf"`（正无穷大）作为抬升极大值。

### 3. 内置专业沉降色标 (`default_subsidence.qml`)
- 已 100% 采用真实的 Sentinel-1 InSAR 沉降业务标准（源自 `沉降.qml`）：
  - `<= -40 mm`：洋红/深紫 (`#aa0058`, alpha=178)
  - `-40 ~ -10 mm`：红橙、金黄、黄绿梯度沉降 (`#cb3801`, `#eccd00`, `#b9f90f`)
  - **`-10 ~ +10 mm`（稳定区）**：**浅薄荷绿 (`#2de598`)，设置半透明 `alpha="89"`（约 35% 不透明度）**。在 Google Earth 叠加时可清晰看透下方卫星航拍底图，体验极佳。
  - `+10 ~ +40 mm`：青绿、明蓝、宝蓝梯度抬升 (`#14ddc7`, `#0790f3`, `#101ced`)
  - `> +40 mm`：深藏青 (`#00007f`, alpha=255)

### 4. 工业级桌面客户端 (`main.py`)
- **QML 样式选择器**：支持三种模式：
  1. `[默认] InSAR 地表沉降标准色标 (-40mm ~ +40mm)`；
  2. `自定义 QML 样式文件...`（提供文件选择弹窗与路径回填）；
  3. `无 (单波段不进行伪彩色渲染)`。
- **栅格智能感知**：表格实时回显文件的波段数（单波段/多波段）、原始坐标系及格式标签。
- **统一输出目录与结果定位**：支持自定义输出目录，双击结果行一键定位成果文件。
- **CLI 命令行兼容**：支持 `python main.py -i <input.tif> -o <output.kmz> [-q style.qml] [--no-warp]`。

### 5. 便携独立打包与体积瘦身 (`build.py`)
- **依赖注入**：通过 `--add-data` 自动封装 PROJ 数据字典、GDAL 数据字典及 `default_subsidence.qml`。
- **Intel MKL 深度剔除**：打包后自动清除无用的 MKL / TBB 动态链接库，**将包体积从 751 MB 深度缩减至 132 MB**。

### 6. 自动化测试套件 (`tests/test_insar_e2e.py`)
- 自动生成合成单波段 Float32 沉降漏斗栅格，执行全套切片，并对 KMZ 解包校验内部 4 通道 RGBA PNG 瓦片与透明度。

---

## 二、未完成工作与下一步开发路线 (Milestone 2 & 3)

### 目标二：GPKG（GeoPackage）智能感知与双轨制 KMZ 转换引擎（当前主线）

#### 1. GPKG 智能内容感知分析引擎
- [ ] **多类型深度扫描**：
  - 扫描 SQLite 元数据表 `gpkg_contents`；
  - 识别 `tiles` / `2d-gridded-coverage` -> 标记为 **[GPKG 栅格图层]**；
  - 识别 `features` -> 标记为 **[GPKG 矢量图层]**（点、线、面）；
  - 识别 `attributes` -> 标记为 **[非空间属性/时序表]**。
- [ ] **内嵌 QML 样式自动拾取**：
  - 查询 GPKG 内部是否存在 `layer_styles` 表；
  - 若存在，自动提取其中保存的 QML 样式并优先应用，实现“零手动配置”。

#### 2. GPKG 栅格切片轨道（轨道 A）
- [ ] 通过 GDAL 的 GPKG 驱动打开栅格图层；
- [ ] 对接现有转换引擎（QML 着色 -> 重投影 -> KML SuperOverlay 切片）。

#### 3. GPKG 矢量要素转换轨道（轨道 B）
- [ ] **InSAR PS 点 / 沉降监测点 / 等值线矢量转换**：
  - 调用 `osgeo.ogr` 读取矢量要素几何与属性；
  - 坐标自动重投影至 WGS84（EPSG:4326）；
  - 将矢量要素转换为 Google Earth 原生 KML `<Placemark>`；
  - **点击信息弹窗 (Popup Balloon)**：利用 `<ExtendedData>` 或 HTML `<description>`，在 Google Earth 中点击散点时弹出专业信息卡（显示点编号、经纬度、年均沉降速率、累计形变量等）。
  - **矢量样式自动着色**：根据沉降速率字段（如 `velocity`）的值大小，自动使用色标赋予点要素红/黄/绿不同颜色的圆点图标。

#### 4. GUI 与交互扩展
- [ ] 文件过滤增加 `*.gpkg`；
- [ ] 拖入 GPKG 时，表格智能显示图层详情（如 `GPKG: 矢量点 (18,200点)` 或 `GPKG: 栅格金字塔`）；
- [ ] 多图层 GPKG 时弹窗允许用户勾选需要导出的图层。

---

### 目标三：扩展与生产级打磨（远期规划）

1. **KMZ 屏幕图例叠加 (ScreenOverlay)**：
   - 转换单波段时，自动在 KMZ 中生成一个沉降色标尺图片，固定悬浮在 Google Earth 屏幕左下角。
2. **多文件高并发并行切片队列**：
   - 支持多进程/多线程批量并行转换，充分利用多核 CPU。
3. **其他格式支持**：
   - Shapefile (`.shp`) 矢量转 KMZ、GeoJSON 转 KMZ。

---

## 三、常用测试与运行命令速查

```bash
# 1. 启动桌面客户端
D:\Miniconda3\envs\tif_kmz\python.exe main.py

# 2. 运行单波段 InSAR + QML 端到端全自动测试
D:\Miniconda3\envs\tif_kmz\python.exe tests/test_insar_e2e.py

# 3. 命令行转换测试
D:\Miniconda3\envs\tif_kmz\python.exe main.py -i input.tif -o output.kmz -q default_subsidence.qml

# 4. 执行独立可执行程序打包与深度瘦身
D:\Miniconda3\envs\tif_kmz\python.exe build.py

# 5. Git 提交与同步规范 (每次代码改动后必跑)
git add -A
git commit -m "feat/fix/refactor: 你的修改描述"
git push origin main
```
