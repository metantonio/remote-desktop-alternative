"""WebSocket transport carrying desk binary frames.

DeskWS: asyncio WS server managing controller connections.
DeskClient: connecting WS client yielding decoded frames.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Callable

import websockets
from . import protocol
from .protocol import FrameStream

log = logging.getLogger("desk.transport")


class Conn:
    """One WS peer connection with a frame buffer + async helpers."""

    def __init__(self, ws, name: str):
        self.ws = ws
        self.name = name
        self.stream = FrameStream()
        self._closed = False

    async def push_frame(self, ftype_or_frame, payload: bytes | None = None):
        if self._closed:
            return
        if payload is None:
            data = ftype_or_frame
        elif len(payload) >= protocol.MAGIC_LEN and payload.startswith(protocol.MAGIC):
            data = payload
        else:
            data = protocol.make_frame(ftype_or_frame, payload)
        try:
            await self.ws.send(data)
        except Exception:
            self._closed = True

    async def frames(self):
        """Yield (ftype, payload) frames as they complete."""
        while not self._closed:
            try:
                msg = await self.ws.recv()
            except (websockets.ConnectionClosed, Exception):
                break
            if isinstance(msg, bytes):
                for ftype, payload in self.stream.feed(msg):
                    yield ftype, payload
            else:
                for ftype, payload in self.stream.feed(msg.encode("utf-8", "ignore")):
                    yield ftype, payload
        self.stream.clear()
        self._closed = True

    async def close(self):
        self._closed = True
        try:
            await self.ws.close(code=1000)
        except Exception:
            pass


class DeskWS:
    """Async WS server managing controller connections."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.clients: dict = {}
        self._stop = asyncio.Event()
        self._server = None
        self.on_frame = None  # async callable (conn, ftype, payload)

    async def start(self):
        self._server = await websockets.serve(
            self._handler, self.host, self.port, ping_interval=None, max_size=32 * 1024 * 1024)

    async def stop(self):
        self._stop.set()
        for conn in list(self.clients.values()):
            await conn.close()
        self.clients.clear()
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass

    async def _handler(self, ws, *args):
        addr = getattr(ws, "remote_address", None)
        name = str(addr) if addr else f"client_{id(ws)}"
        conn = Conn(ws, name=name)
        self.clients[conn.name] = conn
        try:
            await self._read(conn)
        finally:
            self.clients.pop(conn.name, None)
            log.info("client %r disconnected", conn.name)

    async def _read(self, conn: Conn):
        try:
            async for ftype, payload in conn.frames():
                if self.on_frame is not None:
                    res = self.on_frame(conn, ftype, payload)
                    if asyncio.iscoroutine(res):
                        await res
        except Exception as ex:
            log.warning("reader %r error: %s", conn.name, ex)

    async def broadcast_frame(self, ftype: int, payload: bytes):
        for conn in list(self.clients.values()):
            await conn.push_frame(ftype, payload)

    def client_count(self) -> int:
        return len(self.clients)

    @property
    def conn_names(self):
        return list(self.clients.keys())


class DeskClient:
    """Connecting WS client: connect to a server and yield decoded frames."""

    def __init__(self, uri: str, on_frame: Callable | None = None):
        self.uri = uri
        self.on_frame = on_frame
        self.ws = None
        self.stream = FrameStream()
        self._closed = False

    async def connect(self):
        self.ws = await websockets.connect(self.uri, ping_interval=None, max_size=32 * 1024 * 1024)

    async def close(self):
        self._closed = True
        try:
            if self.ws:
                await self.ws.close(code=1000)
        except Exception:
            pass

    async def push_frame(self, ftype_or_frame, payload: bytes | None = None):
        if self._closed or self.ws is None:
            return
        if payload is None:
            data = ftype_or_frame
        elif len(payload) >= protocol.MAGIC_LEN and payload.startswith(protocol.MAGIC):
            data = payload
        else:
            data = protocol.make_frame(ftype_or_frame, payload)
        try:
            await self.ws.send(data)
        except Exception:
            self._closed = True

    async def frames(self):
        """Yield decoded objects (kind, data)."""
        while not self._closed:
            try:
                msg = await self.ws.recv()
            except (websockets.ConnectionClosed, Exception):
                self._closed = True
                break
            if isinstance(msg, bytes):
                for ftype, payload in self.stream.feed(msg):
                    obj = protocol.decode_frame(ftype, payload)
                    if self.on_frame:
                        res = self.on_frame(obj)
                        if asyncio.iscoroutine(res):
                            await res
                    yield obj
            else:
                for ftype, payload in self.stream.feed(msg.encode("utf-8", "ignore")):
                    obj = protocol.decode_frame(ftype, payload)
                    if self.on_frame:
                        res = self.on_frame(obj)
                        if asyncio.iscoroutine(res):
                            await res
                    yield obj

    @property
    def closed(self):
        return self._closed
