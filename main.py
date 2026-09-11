import os
import sys
import argparse
import subprocess
from datetime import datetime
from typing import Optional, List, Dict

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QCheckBox,
    QMessageBox, QFrame, QStatusBar, QLineEdit, QComboBox
)
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent, QIcon, QPixmap
from osgeo import gdal, osr

from converter import convert_tif_to_kmz, is_wgs84, setup_gdal_env, get_raster_metadata, convert_geodata_to_kmz
from qml_parser import get_default_qml_path
from gpkg_analyzer import analyze_gpkg


def get_app_icon() -> QIcon:
    """获取程序主图标（兼容开发环境与 PyInstaller 打包环境）"""
    if getattr(sys, 'frozen', False):
        base_candidates = [
            getattr(sys, '_MEIPASS', ''),
            os.path.dirname(sys.executable),
            os.path.join(os.path.dirname(sys.executable), '_internal')
        ]
    else:
        base_candidates = [
            os.path.dirname(os.path.abspath(__file__))
        ]

    for b in base_candidates:
        if not b:
            continue
        for name in ("logo.ico", "logo.png", "logo.svg"):
            p = os.path.join(b, name)
            if os.path.exists(p):
                icon = QIcon(p)
                if not icon.isNull():
                    return icon
    return QIcon()


class TaskWorker(QThread):
    """后台单任务转换线程"""
    progress_signal = Signal(float, str)
    finished_signal = Signal(bool, str)

    def __init__(self, input_tif: str, output_kmz: str, auto_reproject: bool, qml_path: Optional[str] = None):
        super().__init__()
        self.input_tif = input_tif
        self.output_kmz = output_kmz
        self.auto_reproject = auto_reproject
        self.qml_path = qml_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            success = convert_geodata_to_kmz(
                input_file=self.input_tif,
                output_kmz=self.output_kmz,
                auto_reproject=self.auto_reproject,
                qml_path=self.qml_path,
                progress_callback=lambda ratio, msg: self.progress_signal.emit(ratio, msg),
                cancel_check=lambda: self._is_cancelled
            )
            if success:
                self.finished_signal.emit(True, "处理完成")
            else:
                self.finished_signal.emit(False, "任务已中止")
        except Exception as e:
            self.finished_signal.emit(False, f"错误: {str(e)}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: Optional[TaskWorker] = None
        self.tasks: List[Dict[str, Any]] = []
        self.current_task_idx = 0
        self.is_batch_running = False

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("GeoTIFF to KMZ Processor")
        self.setWindowIcon(get_app_icon())
        self.resize(1000, 700)
        self.setMinimumSize(880, 600)
        self.setAcceptDrops(True)

        # 工业专业风 QSS 样式表
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8fafc;
            }
            QWidget {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
            }
            QFrame#cardFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
            }
            QLabel#headerTitle {
                font-size: 20px;
                font-weight: 700;
                color: #0f172a;
            }
            QLabel#headerSubTitle {
                font-size: 12px;
                color: #64748b;
            }
            QLabel#sectionTitle {
                font-size: 13px;
                font-weight: 600;
                color: #1e293b;
            }
            QLabel#statusTag {
                font-size: 12px;
                color: #64748b;
            }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
                color: #1e293b;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
                color: #1e293b;
                min-width: 280px;
            }
            QComboBox:focus {
                border-color: #3b82f6;
            }
            QPushButton#primaryBtn {
                background-color: #3b82f6;
                color: #ffffff;
                font-size: 13px;
                font-weight: 500;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                min-height: 20px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #2563eb;
            }
            QPushButton#primaryBtn:pressed {
                background-color: #1d4ed8;
            }
            QPushButton#primaryBtn:disabled {
                background-color: #94a3b8;
            }
            QPushButton#secondaryBtn {
                background-color: #ffffff;
                color: #475569;
                font-size: 12px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #f1f5f9;
                color: #1e293b;
            }
            QProgressBar {
                border: 1px solid #e2e8f0;
                border-radius: 3px;
                background-color: #edf2f7;
                height: 10px;
                text-align: center;
                font-size: 9px;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 2px;
            }
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 4px;
                gridline-color: #f1f5f9;
                font-size: 12px;
                color: #334155;
            }
            QTableWidget::item {
                padding: 4px 8px;
            }
            QTableWidget::item:selected {
                background-color: #eff6ff;
                color: #1e40af;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #475569;
                font-size: 12px;
                font-weight: 600;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 6px 8px;
            }
            QTextEdit#logBox {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 4px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                color: #475569;
                padding: 6px;
            }
            QCheckBox {
                font-size: 12px;
                color: #475569;
            }
            QStatusBar {
                background-color: #ffffff;
                border-top: 1px solid #e2e8f0;
                font-size: 11px;
                color: #64748b;
            }
        """)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(14)

        # 1. 顶栏 (Header Section)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        # 软件品牌 Logo 图标
        logo_icon = get_app_icon()
        if not logo_icon.isNull():
            logo_label = QLabel(self)
            logo_pix = logo_icon.pixmap(36, 36)
            logo_label.setPixmap(logo_pix)
            logo_label.setFixedSize(36, 36)
            header_layout.addWidget(logo_label)

        title_layout = QVBoxLayout()
        title_label = QLabel("GeoTIFF to KMZ Processor", self)
        title_label.setObjectName("headerTitle")
        title_layout.addWidget(title_label)

        action_layout = QVBoxLayout()
        action_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        version_label = QLabel("Version 1.0.0", self)
        version_label.setObjectName("headerSubTitle")
        version_label.setAlignment(Qt.AlignRight)

        btn_row = QHBoxLayout()
        self.add_file_btn = QPushButton("添加文件", self)
        self.add_file_btn.setObjectName("secondaryBtn")
        self.add_file_btn.clicked.connect(self.choose_files)

        self.start_btn = QPushButton("开始处理", self)
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.clicked.connect(self.start_processing)

        btn_row.addWidget(self.add_file_btn)
        btn_row.addWidget(self.start_btn)

        action_layout.addWidget(version_label)
        action_layout.addLayout(btn_row)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        header_layout.addLayout(action_layout)
        main_layout.addLayout(header_layout)

        # 2. 当前任务卡片 (Current Task Card)
        task_frame = QFrame(self)
        task_frame.setObjectName("cardFrame")
        task_layout = QVBoxLayout(task_frame)
        task_layout.setContentsMargins(16, 12, 16, 12)
        task_layout.setSpacing(8)

        task_top_row = QHBoxLayout()
        task_title = QLabel("当前任务", task_frame)
        task_title.setObjectName("sectionTitle")
        self.task_status_tag = QLabel("等待开始", task_frame)
        self.task_status_tag.setObjectName("statusTag")
        task_top_row.addWidget(task_title)
        task_top_row.addStretch()
        task_top_row.addWidget(self.task_status_tag)
        task_layout.addLayout(task_top_row)

        self.progress_bar = QProgressBar(task_frame)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        task_layout.addWidget(self.progress_bar)

        task_bottom_row = QHBoxLayout()
        self.task_detail_label = QLabel("选择文件或拖拽 .tif / .gpkg 文件到列表中开始处理", task_frame)
        self.task_detail_label.setObjectName("statusTag")
        self.progress_ratio_label = QLabel("0 / 0 · 0.0%", task_frame)
        self.progress_ratio_label.setObjectName("statusTag")
        task_bottom_row.addWidget(self.task_detail_label)
        task_bottom_row.addStretch()
        task_bottom_row.addWidget(self.progress_ratio_label)
        task_layout.addLayout(task_bottom_row)

        main_layout.addWidget(task_frame)

        # 3. 处理结果表格卡片 (Results Section)
        result_frame = QFrame(self)
        result_frame.setObjectName("cardFrame")
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(16, 12, 16, 12)
        result_layout.setSpacing(8)

        table_header_layout = QHBoxLayout()
        table_title = QLabel("处理结果", result_frame)
        table_title.setObjectName("sectionTitle")
        self.chk_reproject = QCheckBox("自动校准为 WGS84 (EPSG:4326) 坐标系", result_frame)
        self.chk_reproject.setChecked(True)

        self.clear_table_btn = QPushButton("清空列表", result_frame)
        self.clear_table_btn.setObjectName("secondaryBtn")
        self.clear_table_btn.clicked.connect(self.clear_tasks)

        table_header_layout.addWidget(table_title)
        table_header_layout.addStretch()
        table_header_layout.addWidget(self.chk_reproject)
        table_header_layout.addWidget(self.clear_table_btn)
        result_layout.addLayout(table_header_layout)

        # 输出目录配置行
        out_dir_layout = QHBoxLayout()
        out_dir_label = QLabel("输出目录:", result_frame)
        out_dir_label.setObjectName("sectionTitle")
        out_dir_label.setFixedWidth(65)

        self.out_dir_edit = QLineEdit(result_frame)
        self.out_dir_edit.setPlaceholderText("默认保存至源文件所在目录 (可点击右侧按钮指定统一输出目录)")
        self.out_dir_edit.textChanged.connect(self.on_output_dir_changed)

        self.select_out_dir_btn = QPushButton("选择目录", result_frame)
        self.select_out_dir_btn.setObjectName("secondaryBtn")
        self.select_out_dir_btn.clicked.connect(self.choose_output_dir)

        self.open_out_dir_btn = QPushButton("打开目录", result_frame)
        self.open_out_dir_btn.setObjectName("secondaryBtn")
        self.open_out_dir_btn.clicked.connect(self.open_current_output_dir)

        out_dir_layout.addWidget(out_dir_label)
        out_dir_layout.addWidget(self.out_dir_edit)
        out_dir_layout.addWidget(self.select_out_dir_btn)
        out_dir_layout.addWidget(self.open_out_dir_btn)
        result_layout.addLayout(out_dir_layout)

        # QML 样式配置行 (专为单波段沉降/DEM 伪彩色上色)
        qml_layout = QHBoxLayout()
        qml_label = QLabel("QML 样式:", result_frame)
        qml_label.setObjectName("sectionTitle")
        qml_label.setFixedWidth(65)

        self.qml_combo = QComboBox(result_frame)
        self.qml_combo.addItem("[默认] InSAR 地表沉降标准色标 (-40mm ~ +40mm)", "DEFAULT")
        self.qml_combo.addItem("自定义 QML 样式文件...", "CUSTOM")
        self.qml_combo.addItem("无 (单波段不进行伪彩色渲染)", "NONE")
        self.qml_combo.currentIndexChanged.connect(self.on_qml_mode_changed)

        self.qml_path_edit = QLineEdit(result_frame)
        self.qml_path_edit.setPlaceholderText("请选择自定义 .qml 文件路径")
        self.qml_path_edit.setVisible(False)

        self.select_qml_btn = QPushButton("浏览 QML", result_frame)
        self.select_qml_btn.setObjectName("secondaryBtn")
        self.select_qml_btn.setVisible(False)
        self.select_qml_btn.clicked.connect(self.choose_custom_qml)

        qml_layout.addWidget(qml_label)
        qml_layout.addWidget(self.qml_combo)
        qml_layout.addWidget(self.qml_path_edit, 1)
        qml_layout.addWidget(self.select_qml_btn)
        result_layout.addLayout(qml_layout)

        # 表格控件
        self.table = QTableWidget(result_frame)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["文件名", "原始坐标系", "格式选项", "状态", "详细信息"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.on_table_double_clicked)
        result_layout.addWidget(self.table)

        main_layout.addWidget(result_frame, 3)

        # 4. 运行日志卡片 (Log Section)
        log_frame = QFrame(self)
        log_frame.setObjectName("cardFrame")
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(16, 12, 16, 12)
        log_layout.setSpacing(8)

        log_header_layout = QHBoxLayout()
        log_title = QLabel("运行日志", log_frame)
        log_title.setObjectName("sectionTitle")
        self.clear_log_btn = QPushButton("清空日志", log_frame)
        self.clear_log_btn.setObjectName("secondaryBtn")
        self.clear_log_btn.clicked.connect(self.clear_logs)
        log_header_layout.addWidget(log_title)
        log_header_layout.addStretch()
        log_header_layout.addWidget(self.clear_log_btn)
        log_layout.addLayout(log_header_layout)

        self.log_text = QTextEdit(log_frame)
        self.log_text.setObjectName("logBox")
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(95)
        log_layout.addWidget(self.log_text)

        main_layout.addWidget(log_frame, 1)

        # 5. 底部状态栏
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_info_label = QLabel("目录: 未选择", self)
        self.status_ready_label = QLabel("Ready", self)
        self.status_bar.addWidget(self.status_info_label, 1)
        self.status_bar.addPermanentWidget(self.status_ready_label)

        self.append_log("系统环境初始化完成，GDAL KMLSuperOverlay 驱动就绪。")
        self.append_log("内置 InSAR 沉降色阶 (-40mm ~ +40mm) 样式已就绪。")

    # 日志输出
    def append_log(self, msg: str):
        now_str = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{now_str}] {msg}")

    def clear_logs(self):
        self.log_text.clear()

    # QML 样式选择事件
    def on_qml_mode_changed(self, index: int):
        mode = self.qml_combo.currentData()
        is_custom = (mode == "CUSTOM")
        self.qml_path_edit.setVisible(is_custom)
        self.select_qml_btn.setVisible(is_custom)

        if mode == "DEFAULT":
            self.append_log("已选择: [默认] InSAR 地表沉降标准色标 (-40mm ~ +40mm)")
        elif mode == "NONE":
            self.append_log("已停用 QML 伪彩色渲染 (单波段将以原生灰度输出)")

    def choose_custom_qml(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 QGIS QML 样式文件", "", "QGIS 图层样式 (*.qml);;所有文件 (*.*)"
        )
        if file_path:
            self.qml_path_edit.setText(file_path)
            self.append_log(f"已载入自定义 QML: {os.path.basename(file_path)}")

    def get_effective_qml_path(self) -> Optional[str]:
        """获取当前生效的 QML 样式路径"""
        mode = self.qml_combo.currentData()
        if mode == "DEFAULT":
            default_p = get_default_qml_path()
            return default_p if os.path.exists(default_p) else None
        elif mode == "CUSTOM":
            custom_p = self.qml_path_edit.text().strip()
            return custom_p if custom_p and os.path.exists(custom_p) else None
        return None

    # 拖拽文件支持
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        files = [u.toLocalFile() for u in urls if u.toLocalFile().lower().endswith(('.tif', '.tiff', '.gpkg'))]
        if files:
            self.add_files(files)

    def choose_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择地理空间数据文件", "", "地理空间数据 (*.tif *.tiff *.gpkg);;GeoTIFF 栅格 (*.tif *.tiff);;GeoPackage 数据库 (*.gpkg);;所有文件 (*.*)"
        )
        if file_paths:
            self.add_files(file_paths)

    def choose_output_dir(self):
        cur_dir = self.out_dir_edit.text().strip()
        target_dir = QFileDialog.getExistingDirectory(self, "选择输出保存目录", cur_dir if os.path.isdir(cur_dir) else "")
        if target_dir:
            self.out_dir_edit.setText(target_dir)

    def open_current_output_dir(self):
        target_dir = self.out_dir_edit.text().strip()
        if not target_dir or not os.path.exists(target_dir):
            if self.tasks:
                target_dir = os.path.dirname(self.tasks[0]["output"])
        if target_dir and os.path.exists(target_dir):
            if sys.platform == "win32":
                subprocess.Popen(f'explorer "{os.path.abspath(target_dir)}"')
            else:
                subprocess.Popen(["xdg-open", target_dir])
        else:
            QMessageBox.information(self, "提示", "尚未选择有效的输出目录，或尚未添加处理任务。")

    def on_output_dir_changed(self, text: str):
        target_dir = text.strip()
        has_custom = bool(target_dir and os.path.isdir(target_dir))
        for t in self.tasks:
            base_name = os.path.basename(t["input"])
            name_no_ext = os.path.splitext(base_name)[0]
            if has_custom:
                t["output"] = os.path.join(target_dir, f"{name_no_ext}.kmz")
            else:
                t["output"] = os.path.join(os.path.dirname(t["input"]), f"{name_no_ext}.kmz")

        if has_custom:
            self.status_info_label.setText(f"输出目录: {target_dir}")
            self.append_log(f"输出目录已变更为: {target_dir}")
        elif self.tasks:
            self.status_info_label.setText("输出目录: 与源文件同目录")

    def add_files(self, file_paths: List[str]):
        setup_gdal_env()
        custom_dir = self.out_dir_edit.text().strip()
        has_custom = bool(custom_dir and os.path.isdir(custom_dir))

        for fp in file_paths:
            abs_fp = os.path.abspath(fp)
            norm_fp = os.path.normcase(abs_fp)

            base_name = os.path.basename(fp)
            name_no_ext = os.path.splitext(base_name)[0]
            dir_name = custom_dir if has_custom else os.path.dirname(abs_fp)
            out_kmz = os.path.join(dir_name, f"{name_no_ext}.kmz")
            norm_out = os.path.normcase(os.path.abspath(out_kmz))

            # 1. 输入源文件去重拦截
            if any(os.path.normcase(t['input']) == norm_fp for t in self.tasks):
                self.append_log(f"重复文件已自动过滤: {base_name}")
                continue

            # 2. 目标输出 KMZ 去重拦截
            if any(os.path.normcase(t['output']) == norm_out for t in self.tasks):
                self.append_log(f"目标输出已存在于任务列表中，已自动去重: {os.path.basename(out_kmz)}")
                continue

            is_gpkg = abs_fp.lower().endswith('.gpkg')
            gpkg_summary = None

            if is_gpkg:
                try:
                    gpkg_summary = analyze_gpkg(abs_fp)
                    format_desc = gpkg_summary.get_brief_description()
                    srs_desc = "未知坐标系"
                    if gpkg_summary.layers:
                        srs_desc = gpkg_summary.layers[0].srs_desc
                    band_count = 1
                    if gpkg_summary.raster_layers:
                        band_count = gpkg_summary.raster_layers[0].band_count
                    detail_text = f"包含 {len(gpkg_summary.layers)} 个图层"
                    if gpkg_summary.embedded_styles_count > 0:
                        detail_text += " (含内置QML)"
                    self.append_log(f"已载入 GPKG: {base_name} | {format_desc} | {srs_desc}")
                except Exception as e:
                    format_desc = "GPKG (解析失败)"
                    srs_desc = "未知坐标系"
                    band_count = 0
                    detail_text = f"错误: {e}"
                    self.append_log(f"GPKG 解析异常 [{base_name}]: {e}")
            else:
                # 探测栅格元数据
                meta = get_raster_metadata(abs_fp)
                band_count = meta.get("band_count", 1)
                srs_desc = meta.get("srs_desc", "未知坐标系")
                format_desc = "单波段 QML着色" if band_count == 1 else "多波段 PNG切片"
                detail_text = "-"
                band_info = f"单波段({band_count}波段)" if band_count == 1 else f"多波段({band_count}波段)"
                self.append_log(f"已载入: {base_name} | {band_info} | {srs_desc}")

            task = {
                "input": abs_fp,
                "output": out_kmz,
                "srs": srs_desc,
                "band_count": band_count,
                "is_gpkg": is_gpkg,
                "gpkg_summary": gpkg_summary,
                "status": "等待处理",
                "detail": detail_text
            }
            self.tasks.append(task)

            # 插入表格
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(base_name))
            self.table.setItem(row, 1, QTableWidgetItem(srs_desc))
            self.table.setItem(row, 2, QTableWidgetItem(format_desc))
            self.table.setItem(row, 3, QTableWidgetItem("等待处理"))
            self.table.setItem(row, 4, QTableWidgetItem(detail_text))

        total = len(self.tasks)
        self.progress_ratio_label.setText(f"0 / {total} · 0.0%")
        if has_custom:
            self.status_info_label.setText(f"输出目录: {custom_dir}")
        elif file_paths:
            self.status_info_label.setText(f"目录: {os.path.dirname(file_paths[0])}")

    def clear_tasks(self):
        if self.is_batch_running:
            QMessageBox.warning(self, "警告", "正在执行转换任务，请等待完成。")
            return
        self.tasks.clear()
        self.table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.task_status_tag.setText("等待开始")
        self.task_detail_label.setText("选择文件或拖拽 .tif / .gpkg 文件到列表中开始处理")
        self.progress_ratio_label.setText("0 / 0 · 0.0%")

    def start_processing(self):
        if not self.tasks:
            QMessageBox.information(self, "提示", "请先添加待处理的 GeoTIFF 或 GeoPackage 文件。")
            return

        if self.is_batch_running:
            return

        self.is_batch_running = True
        self.start_btn.setEnabled(False)
        self.add_file_btn.setEnabled(False)
        self.clear_table_btn.setEnabled(False)
        self.current_task_idx = 0
        self.status_ready_label.setText("Processing")

        self.process_next_task()

    def process_next_task(self):
        if self.current_task_idx >= len(self.tasks):
            # 所有任务完成
            self.is_batch_running = False
            self.start_btn.setEnabled(True)
            self.add_file_btn.setEnabled(True)
            self.clear_table_btn.setEnabled(True)
            self.progress_bar.setValue(100)
            self.task_status_tag.setText("全部处理完成")
            self.task_detail_label.setText("所有文件转换完成")
            self.status_ready_label.setText("Ready")
            total = len(self.tasks)
            self.progress_ratio_label.setText(f"{total} / {total} · 100.0%")
            self.append_log(f"批处理完成，共计 {total} 个文件。")
            return

        task = self.tasks[self.current_task_idx]
        total = len(self.tasks)
        current_num = self.current_task_idx + 1

        self.task_status_tag.setText(f"正在处理 ({current_num}/{total})")
        base_name = os.path.basename(task['input'])
        self.task_detail_label.setText(f"正在转换: {base_name}")
        self.table.setItem(self.current_task_idx, 3, QTableWidgetItem("正在处理"))
        self.table.setItem(self.current_task_idx, 4, QTableWidgetItem("切片生成中..."))

        # 决定当前任务的生效 QML
        effective_qml = None
        if task.get("band_count", 1) == 1:
            effective_qml = self.get_effective_qml_path()
            if effective_qml:
                self.append_log(f"应用样式: {os.path.basename(effective_qml)} -> {base_name}")

        self.append_log(f"开始切片: {base_name} -> {os.path.basename(task['output'])}")

        self.worker = TaskWorker(
            input_tif=task['input'],
            output_kmz=task['output'],
            auto_reproject=self.chk_reproject.isChecked(),
            qml_path=effective_qml
        )
        self.worker.progress_signal.connect(self.on_task_progress)
        self.worker.finished_signal.connect(self.on_task_finished)
        self.worker.start()

    def on_task_progress(self, ratio: float, msg: str):
        task_percent = int(ratio * 100)
        total = len(self.tasks)
        overall_ratio = (self.current_task_idx + ratio) / total
        overall_percent = overall_ratio * 100

        self.progress_bar.setValue(int(overall_percent))
        self.progress_ratio_label.setText(f"{self.current_task_idx} / {total} · {overall_percent:.1f}%")
        self.table.setItem(self.current_task_idx, 4, QTableWidgetItem(f"{msg} ({task_percent}%)"))

    def on_task_finished(self, success: bool, msg: str):
        row = self.current_task_idx
        if success:
            self.table.setItem(row, 3, QTableWidgetItem("成功"))
            self.table.setItem(row, 4, QTableWidgetItem("已生成 KMZ"))
            self.append_log(f"处理完成: {os.path.basename(self.tasks[row]['input'])}")
        else:
            self.table.setItem(row, 3, QTableWidgetItem("失败"))
            self.table.setItem(row, 4, QTableWidgetItem(msg))
            self.append_log(f"处理失败: {os.path.basename(self.tasks[row]['input'])}, 原因: {msg}")

        self.current_task_idx += 1
        self.process_next_task()

    def on_table_double_clicked(self, index):
        """双击表格行自动打开对应的 KMZ 所在目录并高亮选中"""
        row = index.row()
        if row < len(self.tasks):
            out_file = self.tasks[row]["output"]
            if os.path.exists(out_file):
                if sys.platform == "win32":
                    subprocess.Popen(f'explorer /select,"{os.path.abspath(out_file)}"')
                else:
                    subprocess.Popen(["xdg-open", os.path.dirname(os.path.abspath(out_file))])

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_light_title_bar()

    def apply_light_title_bar(self):
        """调用 Windows DWM API，将系统标题栏强制设为纯白/浅色"""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import c_int, byref, sizeof
                hwnd = int(self.winId())

                # 1. 禁用 Windows 沉浸式深色模式
                false_val = c_int(0)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(false_val), sizeof(false_val))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, byref(false_val), sizeof(false_val))

                # 2. Windows 11: 强制设置标题栏背景色为纯白 (COLORREF: 0x00FFFFFF)
                caption_color = c_int(0x00FFFFFF)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(caption_color), sizeof(caption_color))

                # 3. Windows 11: 标题栏文字颜色设为深灰黑
                text_color = c_int(0x003B291E)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, byref(text_color), sizeof(text_color))
            except Exception:
                pass


def run_cli(args):
    """CLI 命令行运行模式"""
    print(f"[*] 模式: 命令行批处理")
    print(f"[*] 输入文件: {args.input}")
    print(f"[*] 输出文件: {args.output}")
    print(f"[*] 自动重投影: {not args.no_warp}")

    qml_file = args.qml
    if not qml_file:
        default_qml = get_default_qml_path()
        if os.path.exists(default_qml):
            qml_file = default_qml
            print(f"[*] 自动启用默认 QML 沉降样式: {os.path.basename(qml_file)}")

    def cli_progress(ratio, msg):
        percent = int(ratio * 100)
        bar = ('=' * (percent // 2)).ljust(50)
        print(f"\r[{bar}] {percent}% - {msg}", end="", flush=True)

    try:
        convert_geodata_to_kmz(
            input_file=args.input,
            output_kmz=args.output,
            auto_reproject=not args.no_warp,
            qml_path=qml_file,
            progress_callback=cli_progress
        )
        print("\n[OK] 转换完成。")
    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="GeoTIFF to KMZ Processor (GDAL KML SuperOverlay)")
    parser.add_argument("-i", "--input", help="输入 .tif 路径")
    parser.add_argument("-o", "--output", help="输出 .kmz 路径")
    parser.add_argument("-q", "--qml", help="可选 QML 样式文件路径 (对单波段生效，留空默认使用内置沉降色标)")
    parser.add_argument("--no-warp", action="store_true", help="禁用自动重投影 EPSG:4326")

    args = parser.parse_args()

    if args.input and args.output:
        run_cli(args)
    else:
        # 设置 Windows 任务栏应用组 ID，保证任务栏正确显示自定义图标
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("geobridge.tif2kmz.app.1.0")
            except Exception:
                pass

        # 强制 Qt Windows 平台不启用深色模式
        os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=0"
        app = QApplication(sys.argv)
        app.setWindowIcon(get_app_icon())
        window = MainWindow()
        window.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
