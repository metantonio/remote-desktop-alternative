"""Remote/controlled side of desk (server).

Starts a WebSocket server, captures the local screen at a target fps and
streams JPEG frames to every controller, and injects their mouse/keyboard.
"""
from __future__ import annotations
import asyncio
import logging

from . import protocol
from .transport import DeskWS
from .capture import Capture
from .injector import Injector

from .discovery import BeaconBroadcaster

log = logging.getLogger("desk.server")


class DeskServer:
    def __init__(self, cfg, capture: Capture, injector: Injector):
        self.cfg = cfg
        self.capture = capture
        self.injector = injector
        self.ws = DeskWS(cfg.host, cfg.port)
        self.ws.on_frame = self._on_client_frame
        self._running = False
        self.screen_w, self.screen_h = 0, 0
        self.password = getattr(cfg, "password", "")
        self._initialized_conns = set()
        self._authenticated_conns = set()
        disc_port = getattr(cfg, "discovery_port", 8766)
        self._beacon = BeaconBroadcaster(
            port=self.cfg.port,
            discovery_port=disc_port,
            name=self.cfg.name,
            protected=bool(self.password),
        )

    async def run(self):
        self._running = True
        await self.ws.start()
        self._beacon.start()
        cap = asyncio.create_task(self._capture_loop())
        try:
            while self._running:
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            pass
        finally:
            self._beacon.stop()
            cap.cancel()
            try:
                await cap
            except asyncio.CancelledError:
                pass
            await self.ws.stop()

    async def _capture_loop(self):
        interval = 1.0 / max(1.0, float(self.cfg.fps))
        while self._running:
            # Only grab screen when at least one client is connected and authenticated
            active_clients = [
                conn for conn in self.ws.clients.values()
                if not self.password or conn.name in self._authenticated_conns
            ]
            if not active_clients:
                await asyncio.sleep(0.25)
                continue

            t0 = asyncio.get_running_loop().time()
            try:
                w, h, img = await asyncio.to_thread(self.capture.grab)
            except Exception as ex:
                log.warning("Capture failed (check screen recording permissions): %s", ex)
                await asyncio.sleep(2.0)
                continue

            self.screen_w, self.screen_h = w, h
            active_names = set(self.ws.clients.keys())
            self._initialized_conns &= active_names
            self._authenticated_conns &= active_names

            for conn in active_clients:
                flags = 0
                if conn.name not in self._initialized_conns:
                    self._initialized_conns.add(conn.name)
                    flags |= protocol.FLAG_FIRST
                    await conn.push_frame(protocol.enc_screen(w, h))
                await conn.push_frame(protocol.enc_frame(w, h, protocol.CODEC_JPEG, img, flags))
            elapsed = asyncio.get_running_loop().time() - t0
            await asyncio.sleep(max(0.001, interval - elapsed))

    async def _on_client_frame(self, conn, ftype, payload):
        try:
            obj = protocol.decode_frame(ftype, payload)
        except Exception as ex:
            log.warning("bad frame from %r: %s", conn.name, ex)
            return
        await self.dispatch(obj, conn=conn)

    async def dispatch(self, obj, conn=None):
        kind, data = obj
        if kind == "hello":
            # Check password authentication
            if self.password:
                client_pass = str(data.get("password", "")) if isinstance(data, dict) else ""
                if client_pass != self.password:
                    log.warning("Authentication failed for client %r", getattr(conn, "name", "unknown"))
                    if conn:
                        await conn.push_frame(protocol.enc_hello(
                            role="server", auth="unauthorized", error="Invalid password"
                        ))
                        await conn.push_frame(protocol.enc_log("Authentication failed: Invalid password."))
                        await conn.close()
                    return
                if conn:
                    self._authenticated_conns.add(conn.name)
            else:
                if conn:
                    self._authenticated_conns.add(conn.name)

            target = [conn] if conn else list(self.ws.clients.values())
            for c in target:
                await c.push_frame(protocol.enc_hello(
                    role="server", auth="ok", name=self.cfg.name,
                    screen_w=self.screen_w, screen_h=self.screen_h,
                    fps=self.cfg.fps, quality=self.cfg.quality))
                if self.screen_w > 0 and self.screen_h > 0:
                    await c.push_frame(protocol.enc_screen(self.screen_w, self.screen_h))
            return

        # Restrict remote control and ping to authenticated clients
        if self.password and conn and conn.name not in self._authenticated_conns:
            return

        if kind == "ping":
            target = [conn] if conn else list(self.ws.clients.values())
            for c in target:
                await c.push_frame(protocol.enc_pong())
        elif kind == "stop":
            self._running = False
        elif kind == "move":
            x, y = data
            await asyncio.to_thread(self.injector.move, x, y)
        elif kind == "down":
            await asyncio.to_thread(self.injector.down, data)
        elif kind == "up":
            await asyncio.to_thread(self.injector.up, data)
        elif kind == "key":
            vk, state = data
            await asyncio.to_thread(self.injector.key, vk, state)
        elif kind == "text":
            await asyncio.to_thread(self.injector.text, data)
        else:
            pass

    async def stop(self):
        self._running = False
        self._beacon.stop()
        await self.ws.stop()
