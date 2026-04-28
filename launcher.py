#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import logging
import ctypes
import hashlib
import platform
import threading
import subprocess
import urllib.request
import ssl
from pathlib import Path
from collections import deque
from datetime import datetime

import psutil

from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWebEngineWidgets import QWebEngineView

# ----------------------------------------------------------------------
#  CONFIGURATION
# ----------------------------------------------------------------------
APP_TITLE = "HexLauncher"
STEALTH_TITLE = "Runtime Broker"
MODULE_DIR = "modules"
CONFIG_FILE = "config.json"
ICON_FILE = "icon.png"
SPLASH_FILE = "splash.png"
LOG_DIR = "logs"
VERSION = "2.2.0"
LICENSE_FILE = "license.bin"

LICENSE_SERVER_URL = "https://hex-launcher-license.vercel.app/api/validate"

MAX_FREE_MODULES = 3
UPDATE_URL = ""

# ----------------------------------------------------------------------
#  THEMES
# ----------------------------------------------------------------------
DARK_THEME = {
    "bg_main": "#1a1a1a",
    "bg_sidebar": "#2d2d2d",
    "bg_panel": "#1a1a1a",
    "accent": "#ff4444",
    "accent_hover": "#cc3333",
    "text_main": "#e0e0e0",
    "text_muted": "#a0a0a0",
    "combo_text": "#ffb347",
    "success": "#ff4444",
    "error": "#ff4444",
    "warning": "#ffaa00",
    "card_gradient_start": "#2d2d2d",
    "card_gradient_end": "#1a1a1a"
}

LIGHT_THEME = {
    "bg_main": "#ffffff",
    "bg_sidebar": "#f0ecff",
    "bg_panel": "#ffffff",
    "accent": "#0066cc",
    "accent_hover": "#0052a3",
    "text_main": "#0066cc",
    "text_muted": "#555555",
    "combo_text": "#0066cc",
    "success": "#0066cc",
    "error": "#cc3333",
    "warning": "#ff8800",
    "card_gradient_start": "#f8f5ff",
    "card_gradient_end": "#ffffff"
}

# ----------------------------------------------------------------------
#  LOGGING
# ----------------------------------------------------------------------
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, f"launcher_{datetime.now().strftime('%Y%m%d')}.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("HexLauncher")

# ----------------------------------------------------------------------
#  WIN32 / MICA
# ----------------------------------------------------------------------
user32 = ctypes.windll.user32

class WinMica:
    @staticmethod
    def enable_mica(hwnd: int):
        try:
            DWMWA_SYSTEMBACKDROP_TYPE = 38
            DWMSBT_MAINWINDOW = 2
            dwmapi = ctypes.windll.dwmapi
            value = ctypes.c_int(DWMSBT_MAINWINDOW)
            dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(DWMWA_SYSTEMBACKDROP_TYPE),
                ctypes.byref(value),
                ctypes.sizeof(value)
            )
        except Exception:
            pass

# ----------------------------------------------------------------------
#  LICENSE MANAGER (FIXED SSL)
# ----------------------------------------------------------------------
class LicenseManager:
    def __init__(self):
        self.is_pro = False
        self.hardware_id = self._get_hardware_id()
        self._load_license()

    def _get_hardware_id(self):
        try:
            import wmi
            c = wmi.WMI()
            for item in c.Win32_ComputerSystemProduct():
                uuid = item.UUID
                break
            else:
                uuid = "unknown"
        except:
            uuid = platform.node()
        return hashlib.sha256(f"{uuid}{platform.processor()}".encode()).hexdigest()[:16]

    def _load_license(self):
        if os.path.exists(LICENSE_FILE):
            try:
                with open(LICENSE_FILE, "r") as f:
                    data = json.load(f)
                    if data.get("key") and data.get("hwid") == self.hardware_id:
                        self.is_pro = True
            except:
                pass

    def validate_key(self, key, parent_widget=None):
        try:
            url = f"{LICENSE_SERVER_URL}?key={key}"
            # Force SSL context to use system certificates (fix for PyInstaller)
            ssl_context = ssl.create_default_context()
            https_handler = urllib.request.HTTPSHandler(context=ssl_context)
            opener = urllib.request.build_opener(https_handler)
            with opener.open(url, timeout=10) as response:
                data = json.loads(response.read().decode())
                if data.get("valid") and data.get("pro"):
                    self.is_pro = True
                    with open(LICENSE_FILE, "w") as f:
                        json.dump({"key": key, "hwid": self.hardware_id}, f)
                    return True, "Pro features unlocked! Please restart the launcher."
                else:
                    return False, "Invalid license key."
        except Exception as e:
            return False, f"Network error: {e}"

    def show_activation_dialog(self, parent=None):
        dlg = QDialog(parent)
        dlg.setWindowTitle("Activate Pro")
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Enter your license key:"))
        key_edit = QLineEdit()
        layout.addWidget(key_edit)
        btn = QPushButton("Activate")
        layout.addWidget(btn)
        result_label = QLabel("")
        layout.addWidget(result_label)

        def do_activate():
            ok, msg = self.validate_key(key_edit.text())
            result_label.setText(msg)
            if ok:
                QMessageBox.information(dlg, "Success", msg)
                dlg.accept()
        btn.clicked.connect(do_activate)
        dlg.exec()

# ----------------------------------------------------------------------
#  MODULE ENTRY (unchanged from your original)
# ----------------------------------------------------------------------
class ModuleEntry(QObject):
    status_changed = Signal(str, str)
    log_line = Signal(str, str)
    stats_updated = Signal(str, float, float)

    def __init__(self, folder_path):
        super().__init__()
        self.folder = Path(folder_path)
        self.manifest = self._load_manifest()
        self.name = self.manifest.get("name", self.folder.name)
        self.proc = None
        self._log_thread = None
        self._log_queue = deque(maxlen=1000)

    def _load_manifest(self):
        manifest_path = self.folder / "module.json"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "executable" not in data:
                py_files = list(self.folder.glob("*.py"))
                if py_files:
                    data["executable"] = sys.executable
                    data["args"] = [str(py_files[0])]
            return data
        py_files = list(self.folder.glob("*.py"))
        if py_files:
            return {
                "name": self.folder.name,
                "executable": sys.executable,
                "args": [str(py_files[0])],
                "working_dir": str(self.folder)
            }
        raise FileNotFoundError(f"No module.json or .py file in {self.folder}")

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        exe = self.manifest["executable"]
        args = self.manifest.get("args", [])
        cwd = self.manifest.get("working_dir", str(self.folder))
        env = os.environ.copy()
        env.update(self.manifest.get("env", {}))
        try:
            self.proc = subprocess.Popen(
                [exe] + args,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            self._log_thread = threading.Thread(target=self._read_logs, daemon=True)
            self._log_thread.start()
            self.status_changed.emit(self.name, "running")
            logger.info(f"Module started: {self.name}")
        except Exception as e:
            error_msg = str(e)
            self.status_changed.emit(self.name, f"failed: {error_msg}")
            logger.error(f"Module {self.name} failed to start: {error_msg}")

    def stop(self, timeout=3):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None
            self.status_changed.emit(self.name, "stopped")
            logger.info(f"Module stopped: {self.name}")

    def _read_logs(self):
        if not self.proc or not self.proc.stdout:
            return
        for line in iter(self.proc.stdout.readline, ''):
            if line:
                self._log_queue.append(line.rstrip())
                self.log_line.emit(self.name, line.rstrip())
            if self.proc.poll() is not None:
                break

    def get_logs(self):
        return list(self._log_queue)

    def update_resource_usage(self):
        if self.proc and self.proc.poll() is None:
            try:
                p = psutil.Process(self.proc.pid)
                cpu = p.cpu_percent(interval=0)
                mem = p.memory_info().rss / (1024 * 1024)
                self.stats_updated.emit(self.name, cpu, mem)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    @property
    def status(self):
        if not self.proc:
            return "stopped"
        code = self.proc.poll()
        if code is None:
            return "running"
        return f"exit {code}"

# ----------------------------------------------------------------------
#  CODE EDITOR & TERMINAL
# ----------------------------------------------------------------------
class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569CD6"))
        keyword_format.setFontWeight(QFont.Bold)
        keywords = ["def", "class", "import", "from", "if", "else", "elif", "while", "for", "return", "True", "False", "None"]
        for word in keywords:
            pattern = QRegularExpression(f"\\b{word}\\b")
            self.highlighting_rules.append((pattern, keyword_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.highlighting_rules:
            match = pattern.match(text)
            while match.hasMatch():
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)
                match = pattern.match(text, match.capturedEnd())

class CodeEditor(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = Path(file_path)
        self.setWindowTitle(f"Edit – {self.file_path.name}")
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        self.editor = QPlainTextEdit()
        with open(self.file_path, "r", encoding="utf-8") as f:
            self.editor.setPlainText(f.read())
        self.editor.setFont(QFont("Consolas", 10))
        if self.file_path.suffix == ".py":
            PythonHighlighter(self.editor.document())
        layout.addWidget(self.editor)
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.save)
        layout.addWidget(btn_save)

    def save(self):
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(self.editor.toPlainText())
        QMessageBox.information(self, "Saved", "File saved.")
        self.accept()

class TerminalWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 10))
        layout.addWidget(self.text_edit)
        self.input_line = QLineEdit()
        self.input_line.returnPressed.connect(self.execute_command)
        layout.addWidget(self.input_line)
        self.start_shell()

    def start_shell(self):
        if sys.platform == "win32":
            self.process.start("cmd.exe")
        else:
            self.process.start("/bin/bash")
        self.process.waitForStarted()

    def execute_command(self):
        cmd = self.input_line.text()
        if not cmd:
            return
        self.input_line.clear()
        self.process.write(f"{cmd}\n".encode())
        self.process.waitForBytesWritten()

    def handle_stdout(self):
        data = self.process.readAllStandardOutput()
        self.text_edit.appendPlainText(data.data().decode(errors='replace'))

    def handle_stderr(self):
        data = self.process.readAllStandardError()
        self.text_edit.appendPlainText(data.data().decode(errors='replace'))

# ----------------------------------------------------------------------
#  MODULE CARD
# ----------------------------------------------------------------------
class ModuleCard(QFrame):
    def __init__(self, module: ModuleEntry, theme_provider, parent=None):
        super().__init__(parent)
        self.module = module
        self.theme_provider = theme_provider
        self.setObjectName("ModuleCard")
        self.setFixedHeight(110)
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(16)
        self.shadow.setOffset(0, 4)
        self.setGraphicsEffect(self.shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        self.name_label = QLabel(module.name)
        self.name_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        top.addWidget(self.name_label)
        top.addStretch()
        self.status_label = QLabel(module.status)
        self.status_label.setMinimumWidth(80)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.status_label)
        layout.addLayout(top)

        mid = QHBoxLayout()
        self.cpu_label = QLabel("⚡ CPU: --")
        self.mem_label = QLabel("💾 RAM: --")
        mid.addWidget(self.cpu_label)
        mid.addWidget(self.mem_label)
        mid.addStretch()
        layout.addLayout(mid)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.log_btn = QPushButton("📋 Logs")
        self.start_btn = QPushButton("▶ Start")
        self.stop_btn = QPushButton("■ Stop")
        self.edit_btn = QPushButton("✎ Edit")
        self.terminal_btn = QPushButton("💻 Terminal")
        for btn in (self.log_btn, self.start_btn, self.stop_btn, self.edit_btn, self.terminal_btn):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(80, 32)
            btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

        self.log_btn.clicked.connect(self._show_logs)
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.edit_btn.clicked.connect(self._on_edit)
        self.terminal_btn.clicked.connect(self._open_terminal)

        module.status_changed.connect(self._update_status)
        module.stats_updated.connect(self._update_stats)

        self._update_status(module.name, module.status)
        self._apply_theme()

    def _apply_theme(self):
        t = self.theme_provider.get_current_theme()
        self.shadow.setColor(QColor(0, 0, 0, 40))
        self.setStyleSheet(f"""
            #ModuleCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {t['card_gradient_start']}, stop:1 {t['card_gradient_end']});
                border-radius: 20px;
                margin: 8px;
                border: 1px solid {t['accent']}50;
            }}
            QPushButton {{
                background: {t['bg_panel']};
                color: {t['text_main']};
                border-radius: 12px;
                font-weight: bold;
                border: 1px solid {t['accent']}50;
            }}
            QPushButton:hover {{
                background: {t['accent']};
                color: {t['bg_main']};
            }}
        """)
        color = t['success'] if self.module.status == "running" else t['error']
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _update_status(self, name, status):
        if name == self.module.name:
            self.status_label.setText(status)
            t = self.theme_provider.get_current_theme()
            color = t['success'] if status == "running" else t['error']
            self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _update_stats(self, name, cpu, mem):
        if name == self.module.name:
            self.cpu_label.setText(f"⚡ CPU: {cpu:.1f}%")
            self.mem_label.setText(f"💾 RAM: {mem:.1f} MB")

    def _show_logs(self):
        logs = self.module.get_logs()
        dlg = LogDialog(self.module.name, logs, self)
        dlg.exec()

    def _on_start(self):
        self.module.start()

    def _on_stop(self):
        self.module.stop()

    def _on_edit(self):
        editor = self.theme_provider.get_selected_editor()
        manifest_path = self.module.folder / "module.json"
        if manifest_path.exists():
            if editor == "builtin":
                dlg = CodeEditor(manifest_path, self)
                dlg.exec()
            else:
                subprocess.Popen([editor, str(manifest_path)])
        else:
            QMessageBox.information(self, "Edit Module", "No editable manifest found.")

    def _open_terminal(self):
        term = TerminalWidget()
        term.setWindowTitle(f"Terminal – {self.module.name}")
        term.resize(800, 500)
        term.show()

class LogDialog(QDialog):
    def __init__(self, module_name, logs, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Logs – {module_name}")
        self.resize(800, 500)
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText("\n".join(logs))
        self.text.setFont(QFont("Consolas", 10))
        layout.addWidget(self.text)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

# ----------------------------------------------------------------------
#  MAIN WINDOW
# ----------------------------------------------------------------------
class HexLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.license = LicenseManager()
        self._stealth = False
        self._theme = "Dark"
        self._modules: dict[str, ModuleEntry] = {}
        self._activity = deque(maxlen=100)
        self._start_time = time.time()
        self._selected_editor = "builtin"
        self._load_config()
        self._build_ui()
        self._load_modules()
        self._setup_tray()
        self._start_metrics_timer()
        self._start_resource_monitor()
        self._apply_stealth_window_flags()
        hwnd = int(self.winId())
        WinMica.enable_mica(hwnd)
        self._log("HexLauncher started")

    def get_selected_editor(self):
        return self._selected_editor

    def _load_config(self):
        self.config = {"stealth": False, "theme": "Dark", "geometry": None, "auto_start": {}, "external_editor": "builtin"}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.config.update(data)
            except:
                pass
        self._stealth = self.config.get("stealth", False)
        self._theme = self.config.get("theme", "Dark")
        self._selected_editor = self.config.get("external_editor", "builtin")

    def _save_config(self):
        self.config["stealth"] = self._stealth
        self.config["theme"] = self._theme
        self.config["geometry"] = {
            "x": self.x(), "y": self.y(),
            "width": self.width(), "height": self.height()
        }
        self.config["auto_start"] = {
            name: (mod.status == "running") for name, mod in self._modules.items()
        }
        self.config["external_editor"] = self._selected_editor
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=2)

    def get_current_theme(self):
        if not self.license.is_pro:
            return DARK_THEME
        return LIGHT_THEME if self._theme == "Light" else DARK_THEME

    def _apply_stylesheet(self):
        t = self.get_current_theme()
        self.setStyleSheet(f"""
            * {{
                font-family: "Segoe UI", "Inter", -apple-system, BlinkMacSystemFont;
            }}
            QMainWindow {{
                background: {t['bg_main']};
                border-radius: 20px;
            }}
            QStackedWidget {{
                background: {t['bg_main']};
            }}
            QLabel {{
                color: {t['text_main']};
                font-size: 13px;
            }}
            QCheckBox, QCheckBox::indicator {{
                color: {t['text_main']};
            }}
            QPushButton {{
                background: {t['bg_panel']};
                color: {t['text_main']};
                border-radius: 12px;
                padding: 8px 16px;
                font-weight: 500;
                border: 1px solid {t['accent']}50;
            }}
            QPushButton:hover {{
                background: {t['accent']};
                color: {t['bg_main']};
            }}
            QListWidget {{
                background: {t['bg_sidebar']};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 12px 20px;
                border-radius: 12px;
                margin: 4px 12px;
                color: {t['text_main']};
            }}
            QListWidget::item:selected {{
                background: {t['accent']};
                color: {t['bg_main']};
            }}
            QListWidget::item:hover {{
                background: {t['accent_hover']};
                color: {t['bg_main']};
            }}
            QFrame#Panel {{
                background: {t['bg_panel']};
                border-radius: 24px;
                border: 2px solid {t['accent']};
            }}
            QLineEdit, QPlainTextEdit {{
                background: {t['bg_panel']};
                color: {t['text_main']};
                border: 1px solid {t['accent']};
                border-radius: 12px;
                padding: 8px 12px;
                selection-background-color: {t['accent']};
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {t['bg_sidebar']};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['accent']};
                border-radius: 5px;
                min-height: 40px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t['accent_hover']};
            }}
            QScrollBar:horizontal {{
                background: {t['bg_sidebar']};
                height: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:horizontal {{
                background: {t['accent']};
                border-radius: 5px;
                min-width: 40px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {t['accent_hover']};
            }}
            QComboBox {{
                background: {t['bg_panel']};
                color: #ffb347;
                border: 1px solid {t['accent']};
                border-radius: 12px;
                padding: 4px 8px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background: {t['bg_panel']};
                color: #ffb347;
                selection-background-color: {t['accent']};
                selection-color: {t['bg_main']};
            }}
            QComboBox QLineEdit {{
                color: #ffb347;
            }}
        """)

        self._titlebar.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {t['accent']}, stop:1 {t['accent_hover']});
            border-top-left-radius: 20px;
            border-top-right-radius: 20px;
        """)

        self.sidebar.setStyleSheet(f"""
            QListWidget {{
                background: {t['bg_sidebar']};
                border: none;
                font-size: 14px;
                outline: none;
            }}
        """)

        for i in range(self.modules_layout.count()):
            card = self.modules_layout.itemAt(i).widget()
            if card and isinstance(card, ModuleCard):
                card._apply_theme()

    def _create_icon(self, standard_icon):
        return self.style().standardIcon(standard_icon)

    def _build_ui(self):
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        if self.config.get("geometry"):
            geo = self.config["geometry"]
            self.setGeometry(geo["x"], geo["y"], geo["width"], geo["height"])
        else:
            self.resize(1280, 760)
            self.setMinimumSize(1000, 600)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._titlebar = QWidget()
        self._titlebar.setFixedHeight(52)
        title_layout = QHBoxLayout(self._titlebar)
        title_layout.setContentsMargins(20, 0, 16, 0)
        self.title_label = QLabel(APP_TITLE)
        self.title_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold; background: transparent;")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        btn_min = QPushButton("–")
        btn_min.setFixedSize(32, 32)
        btn_min.clicked.connect(self.showMinimized)
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(32, 32)
        btn_close.clicked.connect(self.close)
        for btn in (btn_min, btn_close):
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.2);
                    color: white;
                    border-radius: 16px;
                    font-size: 16px;
                    font-weight: bold;
                    border: none;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.4);
                }
            """)
            btn.setCursor(Qt.PointingHandCursor)
            title_layout.addWidget(btn)

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(260)
        self.sidebar.setIconSize(QSize(24, 24))
        items = [
            (QStyle.SP_ComputerIcon, "Dashboard"),
            (QStyle.SP_DirIcon, "Modules"),
            (QStyle.SP_FileDialogDetailedView, "Settings"),
            (QStyle.SP_MessageBoxInformation, "About")
        ]
        for std_icon, text in items:
            item = QListWidgetItem(text)
            item.setIcon(self._create_icon(std_icon))
            self.sidebar.addItem(item)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._dashboard_page())
        self.stack.addWidget(self._modules_page())
        self.stack.addWidget(self._settings_page())
        self.stack.addWidget(self._about_page())
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self._titlebar)
        left_layout.addWidget(self.sidebar)
        left_wrapper = QWidget()
        left_wrapper.setLayout(left_layout)
        left_wrapper.setFixedWidth(260)

        main_layout.addWidget(left_wrapper)
        main_layout.addWidget(self.stack, 1)

        self._titlebar.mousePressEvent = self._start_move
        self._titlebar.mouseMoveEvent = self._move_window
        self._apply_stylesheet()

    def _dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        columns = QHBoxLayout()
        left = QFrame()
        left.setObjectName("Panel")
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(16)
        left_layout.addWidget(QLabel("📊 SYSTEM STATUS"))
        self.lbl_stealth = QLabel(f"Stealth: {'ON' if self._stealth else 'OFF'}")
        self.lbl_pro = QLabel(f"Edition: {'Pro' if self.license.is_pro else 'Free'}")
        left_layout.addWidget(self.lbl_stealth)
        left_layout.addWidget(self.lbl_pro)
        left_layout.addWidget(QLabel("📈 METRICS"))
        self.lbl_cpu = QLabel("CPU: --")
        self.lbl_ram = QLabel("RAM: --")
        self.lbl_uptime = QLabel("Uptime: --")
        left_layout.addWidget(self.lbl_cpu)
        left_layout.addWidget(self.lbl_ram)
        left_layout.addWidget(self.lbl_uptime)
        left_layout.addStretch()
        columns.addWidget(left, 1)

        right = QFrame()
        right.setObjectName("Panel")
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("📋 ACTIVITY FEED"))
        self.activity_feed = QTextEdit()
        self.activity_feed.setReadOnly(True)
        self.activity_feed.setStyleSheet("background: transparent; border: none; font-family: monospace; font-size: 12px;")
        self.activity_feed.setWordWrapMode(QTextOption.WrapAnywhere)
        right_layout.addWidget(self.activity_feed)
        columns.addWidget(right, 1)

        layout.addLayout(columns)

        activation_row = QHBoxLayout()
        activation_row.addStretch()
        if not self.license.is_pro:
            btn_activate = QPushButton("✨ Activate Pro")
            btn_activate.setFixedWidth(150)
            btn_activate.clicked.connect(lambda: self.license.show_activation_dialog(self))
            activation_row.addWidget(btn_activate)
        else:
            licensed_label = QLabel("✓ Licensed")
            licensed_label.setStyleSheet("color: #a3ff00; font-weight: bold;")
            activation_row.addWidget(licensed_label)
        layout.addLayout(activation_row)

        return page

    def _modules_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("📦 MODULES"))
        toolbar.addStretch()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Filter modules...")
        self.search_bar.textChanged.connect(self._filter_modules)
        toolbar.addWidget(self.search_bar)
        btn_rescan = QPushButton("⟳ Rescan")
        btn_rescan.setFixedWidth(110)
        btn_rescan.clicked.connect(self._load_modules)
        toolbar.addWidget(btn_rescan)
        btn_start_all = QPushButton("▶ Start All")
        btn_start_all.clicked.connect(self._start_all_modules_confirmed)
        toolbar.addWidget(btn_start_all)
        btn_stop_all = QPushButton("■ Stop All")
        btn_stop_all.clicked.connect(self._stop_all_modules_confirmed)
        toolbar.addWidget(btn_stop_all)
        layout.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        self.modules_container = QWidget()
        self.modules_layout = QVBoxLayout(self.modules_container)
        self.modules_layout.setAlignment(Qt.AlignTop)
        self.modules_layout.setSpacing(8)
        scroll.setWidget(self.modules_container)
        layout.addWidget(scroll)
        return page

    def _settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self.chk_stealth = QCheckBox("🕶️ Stealth mode")
        self.chk_stealth.setChecked(self._stealth)
        self.chk_stealth.stateChanged.connect(self._toggle_stealth)
        layout.addWidget(self.chk_stealth)

        if self.license.is_pro:
            self.theme_combo = QComboBox()
            self.theme_combo.addItems(["Dark", "Light"])
            self.theme_combo.setCurrentText(self._theme)
            self.theme_combo.currentTextChanged.connect(self._change_theme)
            layout.addWidget(QLabel("🎨 Theme"))
            layout.addWidget(self.theme_combo)
        else:
            layout.addWidget(QLabel("🎨 Theme: Dark only (upgrade to Pro for Light theme)"))

        layout.addWidget(QLabel("✏️ Code Editor"))
        self.editor_combo = QComboBox()
        self.editor_combo.addItems(["builtin", "VS Code", "Notepad++", "Sublime Text", "Custom..."])
        current = self._selected_editor
        if current == "builtin":
            self.editor_combo.setCurrentIndex(0)
        elif "code" in current.lower():
            self.editor_combo.setCurrentIndex(1)
        elif "notepad++" in current.lower():
            self.editor_combo.setCurrentIndex(2)
        elif "sublime" in current.lower():
            self.editor_combo.setCurrentIndex(3)
        else:
            self.editor_combo.setCurrentIndex(4)
        self.editor_combo.currentIndexChanged.connect(self._editor_changed)
        layout.addWidget(self.editor_combo)

        layout.addStretch()
        return page

    def _editor_changed(self, idx):
        if idx == 0:
            self._selected_editor = "builtin"
        elif idx == 1:
            self._selected_editor = "code"
        elif idx == 2:
            self._selected_editor = "notepad++"
        elif idx == 3:
            self._selected_editor = "sublime_text"
        else:
            path = QFileDialog.getOpenFileName(self, "Select Editor Executable", "", "*.exe")
            if path[0]:
                self._selected_editor = path[0]
        self._save_config()

    def _about_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        about_text = QLabel(f"""
            <h2>HexLauncher</h2>
            <p>Version {VERSION}<br>
            A lightweight, stealth‑capable module manager.<br>
            Launch and control scripts written in any language.</p>
            <p><b>Edition: {'Pro' if self.license.is_pro else 'Free'}</b></p>
            <hr>
            <p>Created by <b>OneArmedJack</b></p>
        """)
        about_text.setWordWrap(True)
        layout.addWidget(about_text)
        layout.addStretch()
        return page

    def _load_modules(self):
        if not os.path.exists(MODULE_DIR):
            os.makedirs(MODULE_DIR)
        self._modules.clear()
        all_modules = []
        for entry in os.listdir(MODULE_DIR):
            path = os.path.join(MODULE_DIR, entry)
            if os.path.isdir(path):
                try:
                    mod = ModuleEntry(path)
                    all_modules.append(mod)
                except Exception as e:
                    self._log(f"Failed to load {entry}: {e}", to_file=True)

        if not self.license.is_pro and len(all_modules) > MAX_FREE_MODULES:
            all_modules = all_modules[:MAX_FREE_MODULES]
            self._log(f"Free version: only {MAX_FREE_MODULES} modules loaded. Upgrade to Pro for unlimited.", to_file=True)

        for mod in all_modules:
            self._modules[mod.name] = mod

        self._rebuild_module_ui()
        auto_start = self.config.get("auto_start", {})
        for name, mod in self._modules.items():
            if auto_start.get(name, False):
                mod.start()
        self._log(f"Loaded {len(self._modules)} module(s)")

    def _rebuild_module_ui(self):
        while self.modules_layout.count():
            child = self.modules_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for mod in self._modules.values():
            card = ModuleCard(mod, self, self)
            if not self.search_bar.text() or self.search_bar.text().lower() in mod.name.lower():
                card.show()
            else:
                card.hide()
            self.modules_layout.addWidget(card)

    def _filter_modules(self, text):
        for i in range(self.modules_layout.count()):
            card = self.modules_layout.itemAt(i).widget()
            if card:
                card.setVisible(text.lower() in card.module.name.lower())

    def _start_all_modules_confirmed(self):
        if not self._modules:
            return
        reply = QMessageBox.question(self, "Start All", f"Start all {len(self._modules)} modules?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            for mod in self._modules.values():
                mod.start()
            self._log("Started all modules")

    def _stop_all_modules_confirmed(self):
        if not self._modules:
            return
        reply = QMessageBox.question(self, "Stop All", f"Stop all {len(self._modules)} modules?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            for mod in self._modules.values():
                mod.stop()
            self._log("Stopped all modules")

    def _log(self, msg, to_file=True):
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self._activity.append(entry)
        if hasattr(self, 'activity_feed') and self.activity_feed:
            self.activity_feed.clear()
            self.activity_feed.setText("\n".join(list(self._activity)[-30:]))
        if to_file:
            logger.info(msg)

    def _start_metrics_timer(self):
        self._metrics_timer = QTimer(self)
        self._metrics_timer.timeout.connect(self._update_metrics)
        self._metrics_timer.start(2000)

    def _update_metrics(self):
        cpu = psutil.cpu_percent()
        proc = psutil.Process(os.getpid())
        ram_mb = proc.memory_info().rss / (1024 * 1024)
        uptime = int(time.time() - self._start_time)
        self.lbl_cpu.setText(f"⚡ CPU: {cpu:.1f}%")
        self.lbl_ram.setText(f"💾 RAM: {ram_mb:.1f} MB")
        self.lbl_uptime.setText(f"⏱️ Uptime: {uptime}s")

    def _start_resource_monitor(self):
        self._res_timer = QTimer(self)
        self._res_timer.timeout.connect(self._update_module_resources)
        self._res_timer.start(3000)

    def _update_module_resources(self):
        for mod in self._modules.values():
            mod.update_resource_usage()

    def _change_theme(self, theme_name):
        if not self.license.is_pro and theme_name != "Dark":
            QMessageBox.warning(self, "Pro Feature", "Light theme is only available in Pro version.")
            return
        self._theme = theme_name
        self._apply_stylesheet()
        self._save_config()

    def _apply_stealth_window_flags(self):
        hwnd = int(self.winId())
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.show()
        if self._stealth:
            new_title = STEALTH_TITLE
            self.setWindowTitle(new_title)
            user32.SetWindowTextW(hwnd, new_title)
            self.title_label.setText(new_title)
            ex_style = user32.GetWindowLongW(hwnd, -20)
            ex_style |= 0x80
            user32.SetWindowLongW(hwnd, -20, ex_style)
            user32.ShowWindow(hwnd, 0)
        else:
            self.setWindowTitle(APP_TITLE)
            user32.SetWindowTextW(hwnd, APP_TITLE)
            self.title_label.setText(APP_TITLE)
            ex_style = user32.GetWindowLongW(hwnd, -20)
            ex_style &= ~0x80
            user32.SetWindowLongW(hwnd, -20, ex_style)
            user32.ShowWindow(hwnd, 5)
            self.showNormal()
            self.raise_()
            self.activateWindow()
        if self.tray_icon:
            self.tray_icon.setToolTip(STEALTH_TITLE if self._stealth else APP_TITLE)

    def _toggle_stealth(self, state):
        self._stealth = bool(state)
        self._save_config()
        self._apply_stealth_window_flags()
        self.lbl_stealth.setText(f"Stealth: {'ON' if self._stealth else 'OFF'}")
        self._log("Stealth " + ("enabled" if self._stealth else "disabled"))

    def _create_generic_tray_icon(self):
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(128, 128, 128))
        return QIcon(pixmap)

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self._create_generic_tray_icon(), self)
        menu = QMenu()
        show_action = QAction("Show", self)
        hide_action = QAction("Hide", self)
        quit_action = QAction("Quit", self)
        show_action.triggered.connect(lambda: self._set_stealth_from_tray(False))
        hide_action.triggered.connect(lambda: self._set_stealth_from_tray(True))
        quit_action.triggered.connect(self.close)
        menu.addAction(show_action)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.setToolTip(APP_TITLE)
        self.tray_icon.show()

    def _set_stealth_from_tray(self, stealth):
        self._stealth = stealth
        self._save_config()
        self._apply_stealth_window_flags()
        self.chk_stealth.setChecked(stealth)

    def _start_move(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def _move_window(self, event):
        if event.buttons() & Qt.LeftButton:
            diff = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + diff)
            self._drag_pos = event.globalPosition().toPoint()

    def closeEvent(self, event):
        self._save_config()
        for mod in self._modules.values():
            mod.stop()
        if self.tray_icon:
            self.tray_icon.hide()
        QApplication.quit()
        event.accept()

# ----------------------------------------------------------------------
#  ENTRY POINT
# ----------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    splash_pix = None
    if os.path.exists(SPLASH_FILE):
        splash_pix = QPixmap(SPLASH_FILE)
    elif os.path.exists(ICON_FILE):
        splash_pix = QPixmap(ICON_FILE)

    splash = None
    if splash_pix:
        splash = QSplashScreen(splash_pix)
        splash.show()
        app.processEvents()
        time.sleep(1.0)

    win = HexLauncher()
    win.show()

    if splash:
        splash.finish(win)
        splash.deleteLater()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()