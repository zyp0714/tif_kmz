import os
import sys
import argparse
import subprocess
from typing import Optional
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QProgressBar, QTextEdit,
    QFileDialog, QCheckBox, QMessageBox, QGroupBox, QFrame
)
from PySide6.QtGui import QFont, QIcon, QDragEnterEvent, QDropEvent

# 导入核心转换逻辑
from converter import convert_tif_to_kmz


class ConvertWorker(QThread):
    """后台转换线程，防止界面无响应"""
    progress_changed = Signal(float, str)
    finished_signal = Signal(bool, str)

    def __init__(self, input_tif: str, output_kmz: str, auto_reproject: bool):
        super().__init__()
        self.input_tif = input_tif
        self.output_kmz = output_kmz
        self.auto_reproject = auto_reproject
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            success = convert_tif_to_kmz(
                input_tif=self.input_tif,
                output_kmz=self.output_kmz,
                auto_reproject=self.auto_reproject,
                progress_callback=lambda ratio, msg: self.progress_changed.emit(ratio, msg),
                cancel_check=lambda: self._is_cancelled
            )
            if success:
                self.finished_signal.emit(True, "转换成功完成！")
            else:
                self.finished_signal.emit(False, "转换已中止或未完成。")
        except Exception as e:
            self.finished_signal.emit(False, f"转换出错: {str(e)}")


class DropAreaWidget(QFrame):
    """支持拖拽文件的区域"""
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #3b82f6;
                border-radius: 10px;
                background-color: #f8fafc;
                min-height: 80px;
            }
            QFrame:hover {
                background-color: #eff6ff;
                border-color: #2563eb;
            }
        """)
        layout = QVBoxLayout(self)
        self.label = QLabel("📥 将 .tif / .tiff 栅格文件直接拖拽至此处", self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #475569; font-size: 14px; font-weight: 500;")
        layout.addWidget(self.label)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith(('.tif', '.tiff')):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            self.file_dropped.emit(file_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: Optional[ConvertWorker] = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("TIF 转 KMZ SuperOverlay 工具 (GDAL)")
        self.resize(680, 560)
        self.setMinimumSize(580, 480)

        # 整体现代浅蓝灰优雅质感 QSS
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f1f5f9;
            }
            QLabel {
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
                color: #1e293b;
            }
            QLineEdit {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 10px;
                background-color: #ffffff;
                font-size: 13px;
                color: #0f172a;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
            }
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-weight: 600;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
            QPushButton:disabled {
                background-color: #94a3b8;
            }
            QPushButton#browseBtn {
                background-color: #e2e8f0;
                color: #334155;
                font-weight: 500;
            }
            QPushButton#browseBtn:hover {
                background-color: #cbd5e1;
            }
            QProgressBar {
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                text-align: center;
                background-color: #e2e8f0;
                height: 20px;
                font-weight: bold;
                color: #1e293b;
            }
            QProgressBar::chunk {
                background-color: #10b981;
                border-radius: 5px;
            }
            QTextEdit {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #ffffff;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 12px;
                color: #334155;
            }
            QCheckBox {
                font-size: 13px;
                color: #334155;
            }
        """)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # 拖拽区域
        self.drop_area = DropAreaWidget(self)
        self.drop_area.file_dropped.connect(self.set_input_file)
        main_layout.addWidget(self.drop_area)

        # 输入文件选择
        in_layout = QHBoxLayout()
        in_label = QLabel("输入 TIF:", self)
        in_label.setFixedWidth(70)
        self.input_edit = QLineEdit(self)
        self.input_edit.setPlaceholderText("请选择或拖入 .tif / .tiff 栅格影像文件")
        self.input_edit.textChanged.connect(self.auto_set_output)
        in_browse = QPushButton("浏览...", self)
        in_browse.setObjectName("browseBtn")
        in_browse.clicked.connect(self.browse_input)
        in_layout.addWidget(in_label)
        in_layout.addWidget(self.input_edit)
        in_layout.addWidget(in_browse)
        main_layout.addLayout(in_layout)

        # 输出文件选择
        out_layout = QHBoxLayout()
        out_label = QLabel("输出 KMZ:", self)
        out_label.setFixedWidth(70)
        self.output_edit = QLineEdit(self)
        self.output_edit.setPlaceholderText("输出 .kmz 路径 (自动填充)")
        out_browse = QPushButton("浏览...", self)
        out_browse.setObjectName("browseBtn")
        out_browse.clicked.connect(self.browse_output)
        out_layout.addWidget(out_label)
        out_layout.addWidget(self.output_edit)
        out_layout.addWidget(out_browse)
        main_layout.addLayout(out_layout)

        # 参数选项
        opt_layout = QHBoxLayout()
        self.chk_reproject = QCheckBox("自动校准为 WGS84 (EPSG:4326) 投影 (推荐开启，Google Earth 必须)", self)
        self.chk_reproject.setChecked(True)
        opt_layout.addWidget(self.chk_reproject)
        main_layout.addLayout(opt_layout)

        # 进度条与状态
        self.status_label = QLabel("就绪", self)
        self.status_label.setStyleSheet("color: #64748b; font-size: 12px;")
        main_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # 操作按钮区
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("🚀 开始转换 (KML SuperOverlay)", self)
        self.start_btn.setFixedHeight(38)
        self.start_btn.clicked.connect(self.start_conversion)

        self.open_dir_btn = QPushButton("📁 打开输出目录", self)
        self.open_dir_btn.setObjectName("browseBtn")
        self.open_dir_btn.setFixedHeight(38)
        self.open_dir_btn.setEnabled(False)
        self.open_dir_btn.clicked.connect(self.open_output_folder)

        btn_layout.addWidget(self.start_btn, 2)
        btn_layout.addWidget(self.open_dir_btn, 1)
        main_layout.addLayout(btn_layout)

        # 日志控制台
        log_label = QLabel("运行日志:", self)
        log_label.setStyleSheet("font-weight: 600; color: #475569;")
        main_layout.addWidget(log_label)

        self.log_edit = QTextEdit(self)
        self.log_edit.setReadOnly(True)
        main_layout.addWidget(self.log_edit)

        self.log("程序就绪。底层调用 GDAL KMLSUPEROVERLAY 驱动生成瓦片金字塔。")

    def log(self, text: str):
        self.log_edit.append(text)

    def set_input_file(self, file_path: str):
        self.input_edit.setText(file_path)

    def auto_set_output(self, in_path: str):
        if in_path and not self.output_edit.text():
            base, _ = os.path.splitext(in_path)
            self.output_edit.setText(f"{base}.kmz")

    def browse_input(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 TIF 栅格影像", "", "GeoTIFF 栅格 (*.tif *.tiff);;所有文件 (*.*)"
        )
        if file_path:
            self.input_edit.setText(file_path)
            base, _ = os.path.splitext(file_path)
            self.output_edit.setText(f"{base}.kmz")

    def browse_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "设置输出 KMZ 文件", self.output_edit.text(), "Google Earth KMZ (*.kmz)"
        )
        if file_path:
            if not file_path.lower().endswith('.kmz'):
                file_path += '.kmz'
            self.output_edit.setText(file_path)

    def start_conversion(self):
        in_file = self.input_edit.text().strip()
        out_file = self.output_edit.text().strip()

        if not in_file or not os.path.exists(in_file):
            QMessageBox.warning(self, "提示", "请选择有效的输入 TIF 文件！")
            return

        if not out_file:
            QMessageBox.warning(self, "提示", "请指定输出 KMZ 路径！")
            return

        self.start_btn.setEnabled(False)
        self.open_dir_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在准备转换...")
        self.log(f"\n--- 开始转换 ---\n输入: {in_file}\n输出: {out_file}")

        self.worker = ConvertWorker(
            input_tif=in_file,
            output_kmz=out_file,
            auto_reproject=self.chk_reproject.isChecked()
        )
        self.worker.progress_changed.connect(self.on_progress)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def on_progress(self, ratio: float, msg: str):
        val = int(ratio * 100)
        self.progress_bar.setValue(val)
        self.status_label.setText(msg)
        if msg:
            self.log(f"[{val}%] {msg}")

    def on_finished(self, success: bool, msg: str):
        self.start_btn.setEnabled(True)
        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText("转换完成！")
            self.open_dir_btn.setEnabled(True)
            self.log(f"✅ {msg}")
            QMessageBox.information(self, "完成", "KMZ 生成成功！可直接拖入 Google Earth 浏览。")
        else:
            self.status_label.setText("转换失败")
            self.log(f"❌ {msg}")
            QMessageBox.critical(self, "错误", msg)

    def open_output_folder(self):
        out_file = self.output_edit.text().strip()
        if out_file and os.path.exists(os.path.dirname(os.path.abspath(out_file))):
            target_dir = os.path.dirname(os.path.abspath(out_file))
            if sys.platform == 'win32':
                subprocess.Popen(f'explorer /select,"{os.path.abspath(out_file)}"')
            else:
                subprocess.Popen(['xdg-open', target_dir])


def run_cli(args):
    """CLI 命令行运行模式"""
    print(f"[*] 模式: 命令行模式")
    print(f"[*] 输入文件: {args.input}")
    print(f"[*] 输出文件: {args.output}")
    print(f"[*] 自动重投影: {not args.no_warp}")

    def cli_progress(ratio, msg):
        percent = int(ratio * 100)
        bar = ('=' * (percent // 2)).ljust(50)
        print(f"\r[{bar}] {percent}% - {msg}", end="", flush=True)

    try:
        convert_tif_to_kmz(
            input_tif=args.input,
            output_kmz=args.output,
            auto_reproject=not args.no_warp,
            progress_callback=cli_progress
        )
        print("\n[√] 转换成功完成！")
    except Exception as e:
        print(f"\n[×] 发生错误: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="TIF 转 KMZ SuperOverlay 工具 (基于 GDAL)")
    parser.add_argument("-i", "--input", help="输入 .tif 路径")
    parser.add_argument("-o", "--output", help="输出 .kmz 路径")
    parser.add_argument("--no-warp", action="store_true", help="禁用自动重投影 EPSG:4326")

    args = parser.parse_args()

    # 如果指定了命令行输入参数，走 CLI 模式
    if args.input and args.output:
        run_cli(args)
    else:
        # 否则启动 GUI 界面
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
