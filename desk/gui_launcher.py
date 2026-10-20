"""Graphical launcher for Desk (AnyDesk alternative).
Provides a modern, robust, cross-platform GUI to share or control a desktop.
Immune to macOS Dark Mode / Tkinter theme glitches.
"""
from __future__ import annotations
import asyncio
import logging
import random
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from .config import Config
from .capture import Capture
from .injector import Injector
from .server import DeskServer
from .client import GuiClient
from .cli import get_local_ips
from .discovery import BeaconListener

log = logging.getLogger("desk.launcher")

# Cross-platform fonts
FONT_FAMILY = "Helvetica" if sys.platform == "darwin" else "Segoe UI"
FONT_MONO = "SF Mono" if sys.platform == "darwin" else "Consolas"

# Unified sleek modern palette (works identically on Windows, macOS Dark/Light, Linux)
COLOR_BG_ROOT = "#16191f"
COLOR_BG_HEADER = "#0f1115"
COLOR_BG_CARD = "#21252d"
COLOR_BORDER = "#323742"
COLOR_TEXT = "#f1f5f9"
COLOR_TEXT_MUTED = "#94a3b8"

# High-contrast input palette (unmistakable input fields on any OS)
COLOR_INPUT_BG = "#ffffff"
COLOR_INPUT_FG = "#0f172a"
COLOR_INPUT_BORDER = "#475569"

COLOR_BTN_BLUE = "#2563eb"
COLOR_BTN_BLUE_ACTIVE = "#1d4ed8"
COLOR_BTN_GREEN = "#16a34a"
COLOR_BTN_GREEN_ACTIVE = "#15803d"
COLOR_BTN_RED = "#dc2626"
COLOR_BTN_RED_ACTIVE = "#b91c1c"
COLOR_BTN_SEC = "#333842"
COLOR_BTN_SEC_ACTIVE = "#404652"


class DeskLauncherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Desk - Remote Desktop")
        self.root.geometry("620x700")
        self.root.minsize(560, 620)
        self.root.configure(bg=COLOR_BG_ROOT)

        self.server: DeskServer | None = None
        self.server_thread: threading.Thread | None = None
        self.server_loop: asyncio.AbstractEventLoop | None = None
        self.server_running = False

        self._init_ttk_style()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start auto-discovery listener
        self.listener = BeaconListener(on_update=self._on_discovered_devices)
        self.listener.start()

    def _init_ttk_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        # Style treeview for discovered computers
        style.configure(
            "Discovered.Treeview",
            background="#0f1115",
            foreground="#f1f5f9",
            fieldbackground="#0f1115",
            borderwidth=1,
            rowheight=26,
            font=(FONT_FAMILY, 9),
        )
        style.configure(
            "Discovered.Treeview.Heading",
            background=COLOR_BG_CARD,
            foreground="#f1f5f9",
            relief="flat",
            font=(FONT_FAMILY, 9, "bold"),
        )
        style.map("Discovered.Treeview", background=[("selected", COLOR_BTN_BLUE)])

    def _build_ui(self):
        # 1. Header Frame
        header = tk.Frame(self.root, bg=COLOR_BG_HEADER, height=60)
        header.pack(fill=tk.X)

        title = tk.Label(
            header,
            text="DESK REMOTE",
            font=(FONT_FAMILY, 15, "bold"),
            fg=COLOR_TEXT,
            bg=COLOR_BG_HEADER,
        )
        title.pack(side=tk.LEFT, padx=18, pady=12)

        subtitle = tk.Label(
            header,
            text="v1.1 Cross-Platform Remote Desktop",
            font=(FONT_FAMILY, 9),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_BG_HEADER,
        )
        subtitle.pack(side=tk.LEFT, pady=16)

        # 2. Modern Navigation Bar (Uses tk.Label for 100% reliable clicks on macOS)
        nav_frame = tk.Frame(self.root, bg=COLOR_BG_HEADER, height=44)
        nav_frame.pack(fill=tk.X)

        self.tab_nav_share = tk.Label(
            nav_frame,
            text=" 📤 Share This Computer (Host) ",
            font=(FONT_FAMILY, 10, "bold"),
            bg=COLOR_BTN_BLUE,
            fg="#ffffff",
            padx=16,
            pady=8,
            cursor="hand2",
            relief=tk.FLAT,
        )
        self.tab_nav_share.pack(side=tk.LEFT, padx=(18, 6), pady=(0, 6))
        self.tab_nav_share.bind("<Button-1>", lambda e: self._switch_to_share())

        self.tab_nav_client = tk.Label(
            nav_frame,
            text=" 💻 Control Remote PC (Client) ",
            font=(FONT_FAMILY, 10, "bold"),
            bg=COLOR_BTN_SEC,
            fg=COLOR_TEXT_MUTED,
            padx=16,
            pady=8,
            cursor="hand2",
            relief=tk.FLAT,
        )
        self.tab_nav_client.pack(side=tk.LEFT, padx=6, pady=(0, 6))
        self.tab_nav_client.bind("<Button-1>", lambda e: self._switch_to_client())

        # 3. Main Content Container using Grid Stack (tkraise)
        self.container = tk.Frame(self.root, bg=COLOR_BG_ROOT)
        self.container.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        # Tab 1: Share Container
        self.share_container = tk.Frame(self.container, bg=COLOR_BG_ROOT)
        self.share_container.grid(row=0, column=0, sticky="nsew")
        self._build_share_view(self.share_container)

        # Tab 2: Client Container
        self.client_container = tk.Frame(self.container, bg=COLOR_BG_ROOT)
        self.client_container.grid(row=0, column=0, sticky="nsew")
        self._build_client_view(self.client_container)

        # Start on Share view
        self._switch_to_share()

        # 4. Status Bar
        self.status_var = tk.StringVar(value="Ready.")
        status_bar = tk.Label(
            self.root,
            textvariable=self.status_var,
            bd=1,
            relief=tk.FLAT,
            anchor=tk.W,
            font=(FONT_FAMILY, 9),
            bg=COLOR_BG_HEADER,
            fg=COLOR_TEXT_MUTED,
            padx=12,
            pady=6,
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _switch_to_share(self):
        self.share_container.tkraise()
        try:
            self.tab_nav_share.config(bg=COLOR_BTN_BLUE, fg="#ffffff")
            self.tab_nav_client.config(bg=COLOR_BTN_SEC, fg=COLOR_TEXT_MUTED)
        except Exception:
            pass

    def _switch_to_client(self):
        self.client_container.tkraise()
        try:
            self.tab_nav_client.config(bg=COLOR_BTN_BLUE, fg="#ffffff")
            self.tab_nav_share.config(bg=COLOR_BTN_SEC, fg=COLOR_TEXT_MUTED)
        except Exception:
            pass

    def _build_share_view(self, parent: tk.Frame):
        desc = tk.Label(
            parent,
            text="Allow another computer on your network to view and control this screen.",
            font=(FONT_FAMILY, 10),
            bg=COLOR_BG_ROOT,
            fg=COLOR_TEXT_MUTED,
        )
        desc.pack(anchor=tk.W, pady=(0, 8))

        # Box 1: Address
        addr_box = tk.LabelFrame(
            parent,
            text=" 📡 Connection Address (Give this to peer) ",
            font=(FONT_FAMILY, 9, "bold"),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT,
            bd=1,
            relief=tk.SOLID,
            padx=12,
            pady=8,
        )
        addr_box.pack(fill=tk.X, pady=(0, 8))

        self.local_ips = get_local_ips()
        primary_ip = self.local_ips[0] if self.local_ips else "127.0.0.1"
        self.addr_var = tk.StringVar(value=f"{primary_ip}:8765")

        addr_row = tk.Frame(addr_box, bg=COLOR_BG_CARD)
        addr_row.pack(fill=tk.X)

        self.addr_entry = tk.Entry(
            addr_row,
            textvariable=self.addr_var,
            font=(FONT_MONO, 11, "bold"),
            bg=COLOR_INPUT_BG,
            fg=COLOR_INPUT_FG,
            insertbackground="#000000",
            relief=tk.SOLID,
            bd=1,
            state="readonly",
        )
        self.addr_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=3)

        btn_copy = tk.Button(
            addr_row,
            text="Copy",
            width=7,
            bg=COLOR_BTN_SEC,
            fg=COLOR_TEXT,
            relief=tk.FLAT,
            command=self._copy_address,
        )
        btn_copy.pack(side=tk.RIGHT)

        # Box 2: Security & Password/PIN
        sec_box = tk.LabelFrame(
            parent,
            text=" 🔒 Security & Password (Optional) ",
            font=(FONT_FAMILY, 9, "bold"),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT,
            bd=1,
            relief=tk.SOLID,
            padx=12,
            pady=10,
        )
        sec_box.pack(fill=tk.X, pady=(0, 8))

        # Row 1: Input field + Show/Hide + Generate PIN button
        sec_input_row = tk.Frame(sec_box, bg=COLOR_BG_CARD)
        sec_input_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            sec_input_row,
            text="Password / PIN:",
            font=(FONT_FAMILY, 10, "bold"),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.host_pass_var = tk.StringVar(value="")
        self.host_pass_entry = tk.Entry(
            sec_input_row,
            textvariable=self.host_pass_var,
            show="",
            font=(FONT_MONO, 11),
            bg=COLOR_INPUT_BG,
            fg=COLOR_INPUT_FG,
            insertbackground="#000000",
            relief=tk.SOLID,
            bd=1,
            width=14,
        )
        self.host_pass_entry.pack(side=tk.LEFT, padx=(0, 8), ipady=3)

        self.host_show_pass = True

        def toggle_host_pass():
            self.host_show_pass = not self.host_show_pass
            self.host_pass_entry.config(show="" if self.host_show_pass else "*")
            btn_show_host.config(text="Hide" if self.host_show_pass else "Show")

        btn_show_host = tk.Button(
            sec_input_row,
            text="Hide",
            width=5,
            bg=COLOR_BTN_SEC,
            fg=COLOR_TEXT,
            relief=tk.FLAT,
            command=toggle_host_pass,
        )
        btn_show_host.pack(side=tk.LEFT, padx=(0, 8))

        def generate_pin():
            pin = f"{random.randint(100000, 999999)}"
            self.host_pass_var.set(pin)
            self.host_show_pass = True
            self.host_pass_entry.config(show="")
            btn_show_host.config(text="Hide")
            # Update prominent badge
            self.lbl_pin_display.config(
                text=f"🔑 Generated PIN:  {pin}",
                fg="#22c55e",
            )
            self.btn_copy_pin.pack(side=tk.RIGHT)

        btn_pin = tk.Button(
            sec_input_row,
            text="🎲 Generate PIN",
            font=(FONT_FAMILY, 9, "bold"),
            bg=COLOR_BTN_SEC,
            fg=COLOR_TEXT,
            relief=tk.FLAT,
            command=generate_pin,
        )
        btn_pin.pack(side=tk.LEFT)

        # Row 2: Prominent PIN / Password Banner
        pin_banner_frame = tk.Frame(sec_box, bg=COLOR_BG_CARD)
        pin_banner_frame.pack(fill=tk.X, pady=(4, 0))

        self.lbl_pin_display = tk.Label(
            pin_banner_frame,
            text="Leave blank for open access, or type a custom password above.",
            font=(FONT_FAMILY, 9),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT_MUTED,
        )
        self.lbl_pin_display.pack(side=tk.LEFT)

        def copy_pin():
            val = self.host_pass_var.get()
            if val:
                self.root.clipboard_clear()
                self.root.clipboard_append(val)
                self.status_var.set(f"Copied PIN '{val}' to clipboard.")

        self.btn_copy_pin = tk.Button(
            pin_banner_frame,
            text="📋 Copy PIN",
            font=(FONT_FAMILY, 8, "bold"),
            bg=COLOR_BTN_SEC,
            fg=COLOR_TEXT,
            relief=tk.FLAT,
            command=copy_pin,
        )
        # Hidden initially until PIN generated
        self.btn_copy_pin.pack_forget()

        # Box 3: Options (Port, FPS, Quality)
        opts_box = tk.LabelFrame(
            parent,
            text=" ⚙️ Streaming Settings ",
            font=(FONT_FAMILY, 9, "bold"),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT,
            bd=1,
            relief=tk.SOLID,
            padx=12,
            pady=8,
        )
        opts_box.pack(fill=tk.X, pady=(0, 10))

        opts_row = tk.Frame(opts_box, bg=COLOR_BG_CARD)
        opts_row.pack(fill=tk.X)

        tk.Label(opts_row, text="Port:", font=(FONT_FAMILY, 9), bg=COLOR_BG_CARD, fg=COLOR_TEXT_MUTED).pack(side=tk.LEFT, padx=(0, 4))
        self.port_var = tk.StringVar(value="8765")
        port_entry = tk.Entry(
            opts_row,
            textvariable=self.port_var,
            width=6,
            bg=COLOR_INPUT_BG,
            fg=COLOR_INPUT_FG,
            insertbackground="#000000",
            relief=tk.SOLID,
            bd=1,
        )
        port_entry.pack(side=tk.LEFT, padx=(0, 16), ipady=2)

        tk.Label(opts_row, text="FPS:", font=(FONT_FAMILY, 9), bg=COLOR_BG_CARD, fg=COLOR_TEXT_MUTED).pack(side=tk.LEFT, padx=(0, 4))
        self.fps_var = tk.StringVar(value="30")
        fps_combo = ttk.Combobox(opts_row, textvariable=self.fps_var, values=["15", "30", "60"], width=4, state="readonly")
        fps_combo.pack(side=tk.LEFT, padx=(0, 16))

        tk.Label(opts_row, text="Quality:", font=(FONT_FAMILY, 9), bg=COLOR_BG_CARD, fg=COLOR_TEXT_MUTED).pack(side=tk.LEFT, padx=(0, 4))
        self.qual_var = tk.StringVar(value="80")
        qual_combo = ttk.Combobox(opts_row, textvariable=self.qual_var, values=["60", "75", "80", "90"], width=4, state="readonly")
        qual_combo.pack(side=tk.LEFT)

        # Start / Stop Toggle Button
        self.btn_server_toggle = tk.Button(
            parent,
            text="Start Sharing",
            font=(FONT_FAMILY, 12, "bold"),
            bg=COLOR_BTN_BLUE,
            fg="#ffffff",
            relief=tk.FLAT,
            height=2,
            cursor="hand2",
            command=self._toggle_server,
        )
        self.btn_server_toggle.pack(fill=tk.X, pady=(4, 6))

        # Bottom Switcher
        btn_goto_client = tk.Button(
            parent,
            text="👉 Want to control another computer instead? Switch to Client Mode ➔",
            font=(FONT_FAMILY, 9),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT_MUTED,
            relief=tk.FLAT,
            pady=6,
            command=self._switch_to_client,
        )
        btn_goto_client.pack(fill=tk.X)

    def _build_client_view(self, parent: tk.Frame):
        desc = tk.Label(
            parent,
            text="Connect to a remote computer to view and control its desktop.",
            font=(FONT_FAMILY, 10),
            bg=COLOR_BG_ROOT,
            fg=COLOR_TEXT_MUTED,
        )
        desc.pack(anchor=tk.W, pady=(0, 8))

        # Target Address Box
        target_box = tk.LabelFrame(
            parent,
            text=" 🖥️ Remote Computer Address ",
            font=(FONT_FAMILY, 9, "bold"),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT,
            bd=1,
            relief=tk.SOLID,
            padx=12,
            pady=8,
        )
        target_box.pack(fill=tk.X, pady=(0, 8))

        self.remote_addr_var = tk.StringVar(value="")
        self.remote_entry = tk.Entry(
            target_box,
            textvariable=self.remote_addr_var,
            font=(FONT_MONO, 11),
            bg=COLOR_INPUT_BG,
            fg=COLOR_INPUT_FG,
            insertbackground="#000000",
            relief=tk.SOLID,
            bd=1,
        )
        self.remote_entry.pack(fill=tk.X, pady=(0, 4), ipady=3)

        tk.Label(
            target_box,
            text="Example: 192.168.1.50:8765  or  ws://10.0.0.12:8765",
            font=(FONT_FAMILY, 8),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT_MUTED,
        ).pack(anchor=tk.W)

        # Client Password Box
        client_sec_box = tk.LabelFrame(
            parent,
            text=" 🔒 Password (if remote host is protected) ",
            font=(FONT_FAMILY, 9, "bold"),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT,
            bd=1,
            relief=tk.SOLID,
            padx=12,
            pady=8,
        )
        client_sec_box.pack(fill=tk.X, pady=(0, 8))

        csec_row = tk.Frame(client_sec_box, bg=COLOR_BG_CARD)
        csec_row.pack(fill=tk.X)

        tk.Label(
            csec_row,
            text="Password / PIN:",
            font=(FONT_FAMILY, 10, "bold"),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.client_pass_var = tk.StringVar(value="")
        self.client_pass_entry = tk.Entry(
            csec_row,
            textvariable=self.client_pass_var,
            show="*",
            font=(FONT_MONO, 11),
            bg=COLOR_INPUT_BG,
            fg=COLOR_INPUT_FG,
            insertbackground="#000000",
            relief=tk.SOLID,
            bd=1,
            width=16,
        )
        self.client_pass_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=3)

        self.client_show_pass = False

        def toggle_client_pass():
            self.client_show_pass = not self.client_show_pass
            self.client_pass_entry.config(show="" if self.client_show_pass else "*")
            btn_show_client.config(text="Hide" if self.client_show_pass else "Show")

        btn_show_client = tk.Button(
            csec_row,
            text="Show",
            width=5,
            bg=COLOR_BTN_SEC,
            fg=COLOR_TEXT,
            relief=tk.FLAT,
            command=toggle_client_pass,
        )
        btn_show_client.pack(side=tk.RIGHT)

        # Discovered Computers Box
        disc_frame = tk.LabelFrame(
            parent,
            text=" 🔍 Discovered Desks on Local Network (Click to select) ",
            font=(FONT_FAMILY, 9, "bold"),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT,
            bd=1,
            relief=tk.SOLID,
            padx=8,
            pady=6,
        )
        disc_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        columns = ("name", "address", "security")
        self.disc_tree = ttk.Treeview(
            disc_frame,
            columns=columns,
            show="headings",
            height=4,
            selectmode="browse",
            style="Discovered.Treeview",
        )
        self.disc_tree.heading("name", text="Device Name")
        self.disc_tree.heading("address", text="IP Address")
        self.disc_tree.heading("security", text="Protection")

        self.disc_tree.column("name", width=170)
        self.disc_tree.column("address", width=190)
        self.disc_tree.column("security", width=110)
        self.disc_tree.pack(fill=tk.BOTH, expand=True)

        self.disc_tree.bind("<<TreeviewSelect>>", self._on_select_discovered)
        self.disc_tree.bind("<Double-1>", self._on_double_click_discovered)

        # Connect Button
        self.btn_connect = tk.Button(
            parent,
            text="Connect to Remote Computer",
            font=(FONT_FAMILY, 12, "bold"),
            bg=COLOR_BTN_GREEN,
            fg="#ffffff",
            relief=tk.FLAT,
            height=2,
            cursor="hand2",
            command=self._connect_client,
        )
        self.btn_connect.pack(fill=tk.X, pady=(2, 6))

        # Bottom Switcher
        btn_goto_share = tk.Button(
            parent,
            text="⬅ Want to share this screen instead? Switch to Host Mode",
            font=(FONT_FAMILY, 9),
            bg=COLOR_BG_CARD,
            fg=COLOR_TEXT_MUTED,
            relief=tk.FLAT,
            pady=6,
            command=self._switch_to_share,
        )
        btn_goto_share.pack(fill=tk.X)

    def _on_select_discovered(self, event):
        sel = self.disc_tree.selection()
        if not sel:
            return
        item = self.disc_tree.item(sel[0])
        values = item.get("values", [])
        if len(values) >= 2:
            self.remote_addr_var.set(str(values[1]))

    def _on_double_click_discovered(self, event):
        self._on_select_discovered(event)
        self._connect_client()

    def _on_discovered_devices(self, devices: list[dict]):
        def update():
            selected_addr = self.remote_addr_var.get()
            self.disc_tree.delete(*self.disc_tree.get_children())
            for dev in devices:
                sec = "Protected" if dev.get("protected") else "Open"
                addr = f"{dev['ip']}:{dev['port']}"
                item_id = self.disc_tree.insert("", tk.END, values=(dev["name"], addr, sec))
                if addr == selected_addr:
                    self.disc_tree.selection_set(item_id)
        try:
            self.root.after(0, update)
        except Exception:
            pass

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

        password = self.host_pass_var.get().strip()
        cfg = Config(host="0.0.0.0", port=port, fps=fps, quality=quality, password=password)
        capture = Capture(fps=fps, quality=quality)
        injector = Injector()
        self.server = DeskServer(cfg, capture, injector)

        primary_ip = self.local_ips[0] if self.local_ips else "127.0.0.1"
        self.addr_var.set(f"{primary_ip}:{port}")

        self.server_running = True
        self.btn_server_toggle.config(
            text="Stop Sharing",
            bg=COLOR_BTN_RED,
        )
        sec_msg = " [Password Protected]" if password else " [No Password]"
        self.status_var.set(f"Server LISTENING on port {port}. Ready for connections.{sec_msg}")

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
        self.btn_server_toggle.config(
            text="Start Sharing",
            bg=COLOR_BTN_BLUE,
        )
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

        password = self.client_pass_var.get().strip()
        self.status_var.set(f"Connecting to {target}...")

        def launch_gui():
            cfg = Config()
            gui = GuiClient(cfg, target, password=password)
            gui.start()
            self.root.after(0, lambda: self.status_var.set("Session ended."))

        t = threading.Thread(target=launch_gui, daemon=True)
        t.start()

    def _on_close(self):
        if hasattr(self, "listener"):
            self.listener.stop()
        if self.server_running:
            self._stop_server()
        self.root.destroy()


def start_gui():
    print(f"[Desk] Launching Desk GUI on {sys.platform}...")
    root = tk.Tk()
    app = DeskLauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    start_gui()
