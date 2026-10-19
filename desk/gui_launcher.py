"""Graphical launcher for Desk (AnyDesk alternative).
Provides a user-friendly GUI to either share this screen or control a remote machine.
"""
from __future__ import annotations
import asyncio
import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from .config import Config
from .capture import Capture
from .injector import Injector
from .server import DeskServer
from .client import GuiClient
from .cli import get_local_ips

log = logging.getLogger("desk.launcher")


class DeskLauncherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Desk - Remote Desktop")
        self.root.geometry("520x460")
        self.root.resizable(False, False)

        # Style configuration
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self.server: DeskServer | None = None
        self.server_thread: threading.Thread | None = None
        self.server_loop: asyncio.AbstractEventLoop | None = None
        self.server_running = False

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # Header
        header_frame = tk.Frame(self.root, bg="#1e222d", height=65)
        header_frame.pack(fill=tk.X)

        title_label = tk.Label(
            header_frame,
            text="DESK REMOTE",
            font=("Segoe UI", 16, "bold"),
            fg="#ffffff",
            bg="#1e222d",
        )
        title_label.pack(side=tk.LEFT, padx=18, pady=12)

        subtitle_label = tk.Label(
            header_frame,
            text="Python Remote Desktop Alternative",
            font=("Segoe UI", 9),
            fg="#a0aab8",
            bg="#1e222d",
        )
        subtitle_label.pack(side=tk.LEFT, pady=18)

        # Main notebook/tabs container
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Tab 1: Share this screen (Server)
        self.tab_share = ttk.Frame(notebook)
        notebook.add(self.tab_share, text=" Share This Computer (Host) ")
        self._build_share_tab(self.tab_share)

        # Tab 2: Control remote screen (Client)
        self.tab_control = ttk.Frame(notebook)
        notebook.add(self.tab_control, text=" Control Remote PC (Client) ")
        self._build_control_tab(self.tab_control)

        # Status Bar
        self.status_var = tk.StringVar(value="Ready.")
        status_bar = tk.Label(
            self.root,
            textvariable=self.status_var,
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=("Segoe UI", 9),
            bg="#f0f2f5",
            padx=8,
            pady=3,
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _build_share_tab(self, parent: ttk.Frame):
        pad_frame = ttk.Frame(parent, padding=14)
        pad_frame.pack(fill=tk.BOTH, expand=True)

        desc = ttk.Label(
            pad_frame,
            text="Allow another computer to view and control your desktop.",
            font=("Segoe UI", 10),
        )
        desc.pack(anchor=tk.W, pady=(0, 10))

        # Local Addresses box
        addr_box = ttk.LabelFrame(pad_frame, text="Your Connection Address", padding=10)
        addr_box.pack(fill=tk.X, pady=(0, 12))

        self.local_ips = get_local_ips()
        primary_ip = self.local_ips[0] if self.local_ips else "127.0.0.1"
        self.addr_var = tk.StringVar(value=f"{primary_ip}:8765")

        addr_row = ttk.Frame(addr_box)
        addr_row.pack(fill=tk.X)

        self.addr_entry = ttk.Entry(addr_row, textvariable=self.addr_var, font=("Consolas", 11), state="readonly")
        self.addr_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        copy_btn = ttk.Button(addr_row, text="Copy", width=7, command=self._copy_address)
        copy_btn.pack(side=tk.RIGHT)

        # Options: Port, FPS, Quality
        opts_frame = ttk.Frame(pad_frame)
        opts_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(opts_frame, text="Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=4)
        self.port_var = tk.StringVar(value="8765")
        port_entry = ttk.Entry(opts_frame, textvariable=self.port_var, width=8)
        port_entry.grid(row=0, column=1, padx=(0, 16), pady=4)

        ttk.Label(opts_frame, text="FPS:").grid(row=0, column=2, sticky=tk.W, padx=(0, 4), pady=4)
        self.fps_var = tk.StringVar(value="30")
        fps_combo = ttk.Combobox(opts_frame, textvariable=self.fps_var, values=["15", "30", "60"], width=6, state="readonly")
        fps_combo.grid(row=0, column=3, padx=(0, 16), pady=4)

        ttk.Label(opts_frame, text="Quality:").grid(row=0, column=4, sticky=tk.W, padx=(0, 4), pady=4)
        self.qual_var = tk.StringVar(value="80")
        qual_combo = ttk.Combobox(opts_frame, textvariable=self.qual_var, values=["60", "75", "80", "90"], width=6, state="readonly")
        qual_combo.grid(row=0, column=5, pady=4)

        # Start / Stop Button
        self.btn_server_toggle = tk.Button(
            pad_frame,
            text="Start Sharing",
            font=("Segoe UI", 11, "bold"),
            bg="#0066cc",
            fg="#ffffff",
            activebackground="#0052a3",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            height=2,
            command=self._toggle_server,
        )
        self.btn_server_toggle.pack(fill=tk.X, pady=(6, 0))

    def _build_control_tab(self, parent: ttk.Frame):
        pad_frame = ttk.Frame(parent, padding=14)
        pad_frame.pack(fill=tk.BOTH, expand=True)

        desc = ttk.Label(
            pad_frame,
            text="Connect to a remote computer to view screen and control inputs.",
            font=("Segoe UI", 10),
        )
        desc.pack(anchor=tk.W, pady=(0, 14))

        # Remote target box
        target_box = ttk.LabelFrame(pad_frame, text="Remote Address", padding=12)
        target_box.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(target_box, text="Enter the IP and port of the remote computer:").pack(anchor=tk.W, pady=(0, 6))

        self.remote_addr_var = tk.StringVar(value="")
        self.remote_entry = ttk.Entry(target_box, textvariable=self.remote_addr_var, font=("Consolas", 11))
        self.remote_entry.pack(fill=tk.X, pady=(0, 4))
        self.remote_entry.focus_set()

        hint = ttk.Label(
            target_box,
            text="Examples: 192.168.1.50:8765  or  ws://10.0.0.12:8765",
            font=("Segoe UI", 8),
            foreground="#666666",
        )
        hint.pack(anchor=tk.W)

        # Connect Button
        self.btn_connect = tk.Button(
            pad_frame,
            text="Connect to Remote Computer",
            font=("Segoe UI", 11, "bold"),
            bg="#28a745",
            fg="#ffffff",
            activebackground="#218838",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            height=2,
            command=self._connect_client,
        )
        self.btn_connect.pack(fill=tk.X, pady=(10, 0))

    def _copy_address(self):
        val = self.addr_var.get()
        self.root.clipboard_clear()
        self.root.clipboard_append(val)
        self.status_var.set(f"Copied '{val}' to clipboard.")

    def _toggle_server(self):
        if not self.server_running:
            self._start_server()
        else:
            self._stop_server()

    def _start_server(self):
        try:
            port = int(self.port_var.get().strip())
            fps = int(self.fps_var.get().strip())
            quality = int(self.qual_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numeric values for Port, FPS and Quality.")
            return

        cfg = Config(host="0.0.0.0", port=port, fps=fps, quality=quality)
        capture = Capture(fps=fps, quality=quality)
        injector = Injector()
        self.server = DeskServer(cfg, capture, injector)

        primary_ip = self.local_ips[0] if self.local_ips else "127.0.0.1"
        self.addr_var.set(f"{primary_ip}:{port}")

        self.server_running = True
        self.btn_server_toggle.config(text="Stop Sharing", bg="#dc3545", activebackground="#c82333")
        self.status_var.set(f"Server LISTENING on port {port}. Ready for connections.")

        def run():
            self.server_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.server_loop)
            try:
                self.server_loop.run_until_complete(self.server.run())
            except Exception as ex:
                log.debug("Server stopped: %s", ex)
            finally:
                self.server_loop.close()

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()

    def _stop_server(self):
        self.status_var.set("Stopping server...")
        if self.server:
            asyncio.run_coroutine_threadsafe(self.server.stop(), self.server_loop)
        self.server_running = False
        self.btn_server_toggle.config(text="Start Sharing", bg="#0066cc", activebackground="#0052a3")
        self.status_var.set("Server stopped. Ready.")

    def _connect_client(self):
        target = self.remote_addr_var.get().strip()
        if not target:
            messagebox.showwarning("Missing Address", "Please enter a remote address to connect to.")
            return

        if not target.startswith("ws://") and not target.startswith("wss://"):
            if ":" in target:
                target = f"ws://{target}"
            else:
                target = f"ws://{target}:8765"

        self.status_var.set(f"Connecting to {target}...")

        def launch_gui():
            cfg = Config()
            gui = GuiClient(cfg, target)
            gui.start()
            self.root.after(0, lambda: self.status_var.set("Session ended."))

        t = threading.Thread(target=launch_gui, daemon=True)
        t.start()

    def _on_close(self):
        if self.server_running:
            self._stop_server()
        self.root.destroy()


def start_gui():
    root = tk.Tk()
    app = DeskLauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    start_gui()
