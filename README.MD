# 🔲 HexLauncher

[![Version](https://img.shields.io/badge/version-2.2.0-blue)](https://github.com/OneArmedJack/HexLauncher)
[![License](https://img.shields.io/badge/license-Commercial-red)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)

A professional, stealth‑capable module manager for running scripts in any language (Python, Node, Go, Rust, etc.).  
Designed for background automation, tool orchestration, and commercial distribution.

---

## ✨ Features

| Feature | Free | Pro |
|---------|:----:|:---:|
| **Module management** (start/stop/logs) | ✅ | ✅ |
| **Built‑in code editor** (with syntax highlighting) | ✅ | ✅ |
| **Embedded terminal** per module | ✅ | ✅ |
| **Stealth mode** (hide window, alt+tab, rename to `Runtime Broker`) | ✅ | ✅ |
| **System tray** (grey dot, no logo) | ✅ | ✅ |
| **Resource monitoring** (CPU / RAM per module) | ✅ | ✅ |
| **Activity feed** with log file | ✅ | ✅ |
| **External editor integration** (VS Code, Notepad++, etc.) | ✅ | ✅ |
| **Maximum modules** | 3 | Unlimited |
| **Themes** (Dark only) | Dark | Dark + Light |
| **No ads** | ❌ | ✅ |
| **Priority support** | ❌ | ✅ |

---

## 🚀 Quick Start (End Users)

1. **Download** the latest `RuntimeBroker.exe` from [Releases](https://github.com/OneArmedJack/HexLauncher/releases).
2. **Place** the `.exe` anywhere (no installation required).
3. **Double‑click** to launch.
4. **Activate Pro** (optional) via the Dashboard → "Activate Pro" button.

> **Note**: The executable is portable – it creates a `modules/` folder next to itself.  
> All settings are stored in `config.json` and logs in `logs/`.

---

## 🛠️ For Developers (Building from source)

### Prerequisites
- Python 3.11 or higher
- Git

### Clone and install

```bash
git clone https://github.com/OneArmedJack/HexLauncher.git
cd HexLauncher
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
```

### Run from source

```bash
python launcher.py
```

### Build executable (PyInstaller)

```bash
pip install pyinstaller
pyinstaller launcher.spec --clean --onefile
```

The executable will be in `dist/RuntimeBroker.exe`.

---

## 📦 How to Create a Module

Modules are placed in the `modules/` folder, each in its own subfolder.

### Option A: Simple Python module

```
modules/
└── MyScript/
    └── script.py
```

The launcher auto‑detects `script.py` and runs it with the same Python interpreter.

### Option B: Any language using `module.json`

```
modules/
└── MyNodeModule/
    ├── module.json
    └── server.js
```

**`module.json` example:**

```json
{
    "name": "My Node Server",
    "executable": "node",
    "args": ["server.js"],
    "working_dir": ".",
    "env": {}
}
```

The launcher supports any executable (Node, Go, Rust, etc.).  
Use `stopped` status to control the process.

---

## 🔑 License & Activation

- **Free version** – limited to 3 modules, Dark theme only, no ads.
- **Pro version** – unlimited modules, Light theme, no ads.

**To activate Pro**, click the “Activate Pro” button on the Dashboard and enter a valid license key.  
The launcher verifies the key online (via Vercel). After successful activation, restart the launcher.

---

## 🛡️ Stealth Mode

- Renames window title to `Runtime Broker`
- Removes window from Alt+Tab (`WS_EX_TOOLWINDOW`)
- Hides main window (can be recalled by right‑clicking tray icon → “Show”)
- Changes executable description to mimic `RuntimeBroker.exe` (if you modify the EXE metadata with Resource Hacker)

> **Note**: The process will still appear in Task Manager, but with the name `RuntimeBroker.exe` (especially if you rename the `.exe` and edit its version info).

---

## 📁 File Structure (after first run)

```
.
├── RuntimeBroker.exe         # (or launcher.py source)
├── config.json               # user settings
├── license.bin               # encrypted license info
├── logs/                     # launcher log files
└── modules/                  # user’s modules (each in its own folder)
```

---

## 🤝 Contributing

Pull requests are welcome. Please follow the existing code style and keep the launcher compatible with both free and pro editions.

---

## 📄 License

Commercial license – see [LICENSE](LICENSE) or contact the author.

---

## 👤 Author

**OneArmedJack**  
[GitHub](https://github.com/OneArmedJack)

---

## 🙏 Acknowledgements

- Built with [PySide6](https://pypi.org/project/PySide6/) (Qt for Python)
- Icons: standard Qt icons
- Stealth techniques via Win32 API and Mica effect for Windows 11

---

## ⚠️ Disclaimer

This software is provided “as is”. The author is not responsible for any misuse or damage caused by this tool. Use at your own risk.
```

Save this as `README.md` in your repository root. You can customise the GitHub links, version number, and any additional details.
