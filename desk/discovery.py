"""Local network auto-discovery for Desk via UDP broadcast beacons.

Hosts broadcast a periodic announcement beacon on UDP port (default 8766).
Clients listen on that port and automatically discover available desks on the LAN.
"""
from __future__ import annotations
import json
import logging
import socket
import threading
import time
from typing import Callable, Dict, Any, List

log = logging.getLogger("desk.discovery")

BEACON_MAGIC = "DESK_BEACON_V1"


class BeaconBroadcaster:
    """Periodically broadcasts host presence on the local network."""

    def __init__(self, port: int, discovery_port: int = 8766, name: str = "",
                 protected: bool = False, interval: float = 2.0):
        self.port = port
        self.discovery_port = discovery_port
        self.name = name or socket.gethostname()
        self.protected = protected
        self.interval = interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception as ex:
            log.warning("Failed to create discovery broadcaster socket: %s", ex)
            return

        payload = json.dumps({
            "magic": BEACON_MAGIC,
            "name": self.name,
            "port": self.port,
            "protected": self.protected,
        }).encode("utf-8")

        while self._running:
            try:
                self._sock.sendto(payload, ("<broadcast>", self.discovery_port))
            except Exception as ex:
                log.debug("Beacon broadcast sendto failed: %s", ex)
            # Sleep in small increments for responsive stop()
            for _ in range(int(self.interval * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass


class BeaconListener:
    """Listens for local network discovery beacons and tracks active desks."""

    def __init__(self, discovery_port: int = 8766, on_update: Callable[[List[Dict[str, Any]]], None] | None = None,
                 expiry: float = 6.0):
        self.discovery_port = discovery_port
        self.on_update = on_update
        self.expiry = expiry
        self._devices: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except Exception:
                    pass
            self._sock.bind(("0.0.0.0", self.discovery_port))
            self._sock.settimeout(1.0)
        except Exception as ex:
            log.warning("Discovery listener bind failed on port %d: %s", self.discovery_port, ex)
            return

        while self._running:
            now = time.time()
            try:
                data, addr = self._sock.recvfrom(2048)
                ip = addr[0]
                try:
                    msg = json.loads(data.decode("utf-8"))
                except Exception:
                    continue

                if msg.get("magic") == BEACON_MAGIC:
                    port = int(msg.get("port", 8765))
                    name = str(msg.get("name", ip))
                    protected = bool(msg.get("protected", False))
                    dev_id = f"{ip}:{port}"
                    with self._lock:
                        self._devices[dev_id] = {
                            "id": dev_id,
                            "ip": ip,
                            "port": port,
                            "name": name,
                            "protected": protected,
                            "last_seen": now,
                        }
            except socket.timeout:
                pass
            except Exception as ex:
                if self._running:
                    log.debug("Discovery listener recv error: %s", ex)

            # Purge expired devices
            with self._lock:
                expired = [k for k, v in self._devices.items() if now - v["last_seen"] > self.expiry]
                for k in expired:
                    del self._devices[k]
                current_list = list(self._devices.values())

            if self.on_update:
                try:
                    self.on_update(current_list)
                except Exception as ex:
                    log.debug("Discovery on_update callback error: %s", ex)

    def get_devices(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._devices.values())

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
