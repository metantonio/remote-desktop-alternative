"""CLI entrypoint for desk (server, client, and interactive mode)."""
from __future__ import annotations
import argparse
import asyncio
import logging
import socket
import sys

from .config import Config
from .capture import Capture
from .injector import Injector
from .server import DeskServer
from .client import RemoteClient, GuiClient


def get_local_ips() -> list[str]:
    """Retrieve non-loopback local IPv4 addresses."""
    ips = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        # Fallback via UDP socket trick
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ips.append(s.getsockname()[0])
        except Exception:
            ips.append("127.0.0.1")
    return ips


def run_server(args):
    """Run desk remote desktop server."""
    cfg = Config(
        host=args.host,
        port=args.port,
        quality=args.quality,
        fps=args.fps,
        max_width=args.max_width,
        max_height=args.max_height,
        name=args.name,
    )
    capture = Capture(
        quality=cfg.quality,
        fps=cfg.fps,
        max_width=cfg.max_width,
        max_height=cfg.max_height,
    )
    injector = Injector()
    server = DeskServer(cfg, capture, injector)

    sw, sh = capture.screen_size()
    local_ips = get_local_ips()

    print("=" * 60)
    print("           DESK - REMOTE DESKTOP SERVER")
    print("=" * 60)
    print(f" Status:    LISTENING on {cfg.host}:{cfg.port}")
    print(f" Screen:    {sw}x{sh} @ {cfg.fps} FPS (Quality: {cfg.quality}%)")
    print(f" Input:     {injector.backend.upper()} backend active")
    print(" Connect from another PC using:")
    for ip in local_ips:
        print(f"   -> desk client ws://{ip}:{cfg.port}")
        print(f"   -> python -m desk client ws://{ip}:{cfg.port}")
    print("=" * 60)
    print(" Press Ctrl+C to terminate.")

    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        injector.shutdown()


def run_client(args):
    """Run desk client."""
    target = args.target.strip()
    if not target.startswith("ws://") and not target.startswith("wss://"):
        if ":" in target:
            target = f"ws://{target}"
        else:
            target = f"ws://{target}:8765"

    cfg = Config()

    if args.headless:
        print(f"Connecting headless to {target}...")
        client = RemoteClient(target)
        try:
            asyncio.run(client.run())
        except KeyboardInterrupt:
            print("\nDisconnecting...")
    else:
        try:
            import pygame
        except ImportError:
            print("ERROR: pygame is not installed. Run: pip install pygame")
            print("Or connect in headless mode: desk client --headless <target>")
            sys.exit(1)

        print(f"Starting GUI client connecting to {target}...")
        gui = GuiClient(cfg, target)
        gui.start()


def interactive_menu():
    """Interactive text menu when launched without arguments."""
    print("=" * 50)
    print("            DESK - Python AnyDesk Alternative")
    print("=" * 50)
    print(" 1) Start Server (Share this computer's screen)")
    print(" 2) Connect as Client (Control a remote computer)")
    print(" 3) Exit")
    print("=" * 50)

    try:
        choice = input("Select an option [1-3]: ").strip()
    except (KeyboardInterrupt, EOFError):
        return

    if choice == "1":
        parser = argparse.ArgumentParser()
        args = parse_server_args(["server"])
        run_server(args)
    elif choice == "2":
        try:
            remote_addr = input("Enter remote host/IP (e.g. 192.168.1.50 or ws://192.168.1.50:8765): ").strip()
        except (KeyboardInterrupt, EOFError):
            return
        if not remote_addr:
            print("No address provided.")
            return
        args = parse_client_args(["client", remote_addr])
        run_client(args)
    else:
        print("Exiting.")


def parse_server_args(argv):
    parser = argparse.ArgumentParser(description="Start Desk remote server.")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    parser.add_argument("--quality", type=int, default=80, help="JPEG quality 1-100 (default: 80)")
    parser.add_argument("--fps", type=int, default=30, help="Target FPS (default: 30)")
    parser.add_argument("--max-width", type=int, default=1920, help="Max streaming width")
    parser.add_argument("--max-height", type=int, default=1080, help="Max streaming height")
    parser.add_argument("--name", default="desk-server", help="Server display name")
    return parser.parse_args(argv[1:])


def parse_client_args(argv):
    parser = argparse.ArgumentParser(description="Connect to remote Desk server.")
    parser.add_argument("target", help="Remote address (e.g. ws://192.168.1.20:8765 or 192.168.1.20)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode without GUI")
    return parser.parse_args(argv[1:])


def launch_gui_or_menu():
    """Try to launch the Tkinter GUI launcher, fallback to text menu."""
    try:
        from .gui_launcher import start_gui
        start_gui()
    except Exception as ex:
        log.debug("GUI launcher failed (%s), falling back to text menu", ex)
        interactive_menu()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if len(sys.argv) < 2:
        launch_gui_or_menu()
        return

    cmd = sys.argv[1].lower()
    if cmd in ("gui", "--gui", "-g"):
        from .gui_launcher import start_gui
        start_gui()
    elif cmd in ("server", "serve", "-s"):
        args = parse_server_args(sys.argv[1:])
        run_server(args)
    elif cmd in ("client", "connect", "-c"):
        if len(sys.argv) < 3:
            print("Usage: desk client <ip_or_ws_url> [--headless]")
            sys.exit(1)
        args = parse_client_args(sys.argv[1:])
        run_client(args)
    elif cmd in ("menu", "--menu", "-m"):
        interactive_menu()
    elif cmd in ("-h", "--help", "help"):
        print("Desk - Python Remote Desktop")
        print("Usage:")
        print("  python -m desk                     (Start Graphical User Interface)")
        print("  python -m desk server [--host 0.0.0.0] [--port 8765] [--quality 80] [--fps 30]")
        print("  python -m desk client <host:port | ws://url> [--headless]")
        print("  python -m desk menu                (Interactive text console menu)")
    else:
        # Treat as client target directly if it looks like an IP/host
        args = parse_client_args(["client"] + sys.argv[1:])
        run_client(args)


if __name__ == "__main__":
    main()
