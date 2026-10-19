# Desk - Python Remote Desktop (AnyDesk Alternative)

A self-contained remote desktop and screen-sharing system written in Python, modelled on the architecture of AnyDesk (separation between Host/Server controlled side and Client/Controller side) over a high-throughput binary frame protocol on top of WebSockets.

---

## 🚀 Key Features

- **Real-Time Screen Streaming**: Accelerated native capture using `mss` (multi-monitor support, Windows per-monitor DPI awareness) with automatic fallback to `PIL.ImageGrab`.
- **Native Input Injection**: Absolute mouse coordinates ($0$ to $65535$) and keyboard simulation via Win32 `SendInput` (supporting Unicode text, standard VK codes, and mouse buttons) with complete fallback to `pynput` on non-Windows platforms.
- **Local Network Auto-Discovery (Nearby Desks)**: Automatic host detection via lightweight UDP broadcast beacons (no IP typing or network scanning required).
- **Optional Password Protection**: End-to-end access validation for secure port forwarding and LAN connections with built-in PIN generator.
- **Interactive Graphical Launcher (Tkinter)**: Clean English graphical interface to easily switch between sharing your screen or controlling a remote PC.
- **Remote Display Window (Pygame)**: Interactive, letterboxed/pillarboxed resizable display client with smooth rendering and thread-safe event forwarding.
- **Batch Script Launchers**: Quick one-click execution via `start.bat` using the local virtual environment.
- **Headless Mode**: Scriptable and automated testing without opening any GUI window.

---

## 📦 Requirements & Installation

The project uses the dependencies specified in `pyproject.toml`.

Ensure your virtual environment is activated:

```powershell
# In Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Install package with GUI and development dependencies:
pip install -e .[gui,dev]
```

*(Note: On Python 3.14+, `pygame-ce` is supported and installed for SDL2 GUI rendering).*

---

## 🖥️ How to Run

### Method 1: Using Script Launchers (Recommended)

- **On Windows:** Double-click or run from command prompt:
  ```cmd
  start.bat
  ```

- **On macOS / Linux:** Make executable and run:
  ```bash
  chmod +x start.sh
  ./start.sh
  ```

This automatically locates your virtual environment (`.venv`) and opens the **Desk Graphical Launcher** in English, where you can select whether you want to **Share This Computer (Host)** or **Control a Remote PC (Client)**.

---

## 🍏 macOS Setup & Required Permissions

If your **Mac is the Host (the machine being controlled and sharing its screen)**, macOS privacy protections require granting two permissions:

1. **Screen Recording Permission** (Allows streaming your desktop):
   - Open **System Settings** (or System Preferences) $\to$ **Privacy & Security** $\to$ **Screen Recording**.
   - Enable the toggle for **Terminal** (or **iTerm2** / Python / your IDE).
   - If prompted, restart Terminal.

2. **Accessibility Permission** (Allows simulating mouse clicks and keystrokes):
   - Open **System Settings** $\to$ **Privacy & Security** $\to$ **Accessibility**.
   - Enable the toggle for **Terminal** (or your terminal application).

*(If your Mac is only connecting as a **Client** to control another PC, no special system permissions are required).*

---

### Method 2: Command Line (CLI)

#### A. Graphical Interface
```powershell
python -m desk
# or
python -m desk gui
```

#### B. Start as Server / Host (Machine to be controlled)
```powershell
# Default settings (Port 8765, 30 FPS, Quality 80%, No password):
python -m desk server

# With Password Protection (recommended for port forwarding / public access):
python -m desk server --password "YourSecretPINOrPass"

# Custom settings:
python -m desk server --port 8765 --password "secret123" --fps 60 --quality 85
```
The console will display your active local IP addresses for easy remote connection within your LAN or VPN (e.g. Tailscale, ZeroTier).

#### C. Start as Client / Controller (Machine controlling the remote PC)
```powershell
# Connect to host without password:
python -m desk client 192.168.1.50:8765

# Connect to a password-protected host:
python -m desk client 192.168.1.50:8765 -p "YourSecretPINOrPass"

# Or with full WebSocket URI:
python -m desk client ws://192.168.1.50:8765 -p "secret123"

# Headless mode (no GUI window):
python -m desk client 192.168.1.50:8765 -p "secret123" --headless
```

---

## 🎮 Controller Session Controls

While connected to a remote desktop:
- **Mouse**: Move, click, drag, right-click, and scroll on the remote machine.
- **Keyboard**: Sends keystrokes and text directly to the remote active window.
- **Exit Session**: Press **Shift + ESC** or close the Pygame window.

---

## 🧪 Running Unit & Integration Tests

To run the complete test suite:
```powershell
pytest
```

The tests verify:
- Binary protocol frame encoding, decoding, partial frames, and stream fragmentation.
- Bidirectional client $\leftrightarrow$ server WebSocket communication over loopback.
- Mouse movement, button clicks, keyboard presses, and text injection into fake injectors.
- Video frame and screen dimension negotiation (`SCREEN` and `FRAME`).
- Command-line parsing and local IP discovery.
