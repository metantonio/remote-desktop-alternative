"""Headless round-trip tests for DeskServer + DeskClient over loopback WS.

Uses a FakeCapture (tiny JPEG, no display) and a FakeInjector (records calls)
so everything runs headless.  Verifies the full frame path both directions:
  client -> server : MOVE / DOWN / UP / KEY / TEXT / HELO / PING / STOP
  server -> client : SCREEN / FRAME
"""
from __future__ import annotations
import asyncio
import io
from typing import List, Tuple

import pytest
from PIL import Image

from desk import protocol as p
from desk.transport import DeskWS, DeskClient
from desk.client import RemoteClient
from desk.injector import Injector
from desk.server import DeskServer
from desk.capture import Capture


# ---------- fakes ----------
class FakeCapture(Capture):
    def __init__(self):
        super().__init__(screen_index=0, quality=60, fps=1)
        self.img = Image.new("RGB", (12, 8), color=(255, 128, 0))
        buf = io.BytesIO()
        self.img.convert("RGB").save(buf, format="JPEG", quality=60)
        self.buf = buf.getvalue()
        self.calls = 0

    def grab(self):
        self.calls += 1
        return (12, 8, self.buf)


class FakeInjector:
    def __init__(self):
        self.moves: List = []
        self.downs: List = []
        self.ups: List = []
        self.keys: List = []
        self.texts: List = []
        self.lock = asyncio.Lock()

    def move(self, x, y):
        self.moves.append((x, y))

    def down(self, b):
        self.downs.append(b)

    def up(self, b):
        self.ups.append(b)

    def key(self, vk, state):
        self.keys.append((vk, state))

    def text(self, s):
        self.texts.append(s)


class Cfg:
    def __init__(self, port: int = 18765, fps: int = 1):
        self.host = "127.0.0.1"
        self.port = port
        self.name = "desk-test-server"
        self.fps = fps
        self.quality = 60
        self.max_width = 100
        self.max_height = 100
        self.ping_interval = 0.5
        self.reconnect_delay = 1.0
        self.screen_size = (0, 0)


async def _find_free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _start_server():
    """Start a DeskServer (ws + capture loop). Return (server, injector, ws, cap_task, port)."""
    port = await _find_free_port()
    capture = FakeCapture()
    injector = FakeInjector()
    server = DeskServer(Cfg(port=port, fps=5), capture, injector)
    server._running = True
    await server.ws.start()
    cap_task = asyncio.create_task(server._capture_loop())
    return server, injector, server.ws, cap_task, port


async def _collect_frames(ws_client, count, timeout=5.0):
    """Collect decoded objects from a connected DeskClient."""
    frames: List = []
    async def collect():
        async for obj in ws_client.frames():
            frames.append(obj)
            if len(frames) >= count:
                return
    ct = asyncio.create_task(collect())
    try:
        await asyncio.wait_for(ct, timeout)
    except asyncio.TimeoutError:
        ct.cancel()
    return frames


async def test_frame_flow():
    """Client receives SCREEN then FRAME from server."""
    server, injector, ws, cap_task, port = await _start_server()
    client = DeskClient(f"ws://127.0.0.1:{port}")
    await client.connect()
    # client sends HELO
    await client.push_frame(p.HELO, p.enc_hello(role="client", name="c1",
                                                  screen_w=100, screen_h=100,
                                                  protocol="desk/1.0"))
    frames = await asyncio.wait_for(_collect_frames(client, 4, 5.0), 5.0)
    kinds = {o[0] for o in frames}
    assert "screen" in kinds, f"no SCREEN in {kinds}"
    assert "frame" in kinds, f"no FRAME in {kinds}"
    for kind, data in frames:
        if kind == "frame":
            w, h, codec, flags, img = data
            assert codec == p.CODEC_JPEG
            pil = Image.open(io.BytesIO(img))
            assert pil.size[0] == 12 and pil.size[1] == 8
    client._running = True
    await client.close()
    cap_task.cancel()
    try:
        await cap_task
    except asyncio.CancelledError:
        pass
    server._running = False
    await server.ws.stop()


async def test_input_injection():
    """Server injects client's MOVE/DOWN/UP/KEY/TEXT into the (fake) injector."""
    server, injector, ws, cap_task, port = await _start_server()
    client = DeskClient(f"ws://127.0.0.1:{port}")
    await client.connect()
    await client.push_frame(p.HELO, p.enc_hello(role="client"))
    # send a bunch of input frames
    await client.push_frame(p.MOVE, p.enc_move(33, 44))
    await client.push_frame(p.DOWN, p.enc_down(0))
    await client.push_frame(p.DOWN, p.enc_down(1))
    await client.push_frame(p.UP, p.enc_up(0))
    await client.push_frame(p.UP, p.enc_up(1))
    await client.push_frame(p.KEY, p.enc_key(0x7E, 1))
    await client.push_frame(p.KEY, p.enc_key(0x7E, 0))
    await client.push_frame(p.TEXT, p.enc_text("hi"))
    await asyncio.sleep(0.5)
    assert (33, 44) in injector.moves, f"moves={injector.moves}"
    assert 0 in injector.downs and 1 in injector.downs
    assert 0 in injector.ups and 1 in injector.ups
    assert (0x7E, 1) in injector.keys
    assert (0x7E, 0) in injector.keys
    assert "hi" in injector.texts
    await client.close()
    cap_task.cancel()
    try:
        await cap_task
    except asyncio.CancelledError:
        pass
    server._running = False
    await server.ws.stop()


async def test_stop():
    """Sending STOP stops the server."""
    server, injector, ws, cap_task, port = await _start_server()
    client = DeskClient(f"ws://127.0.0.1:{port}")
    await client.connect()
    await asyncio.sleep(0.4)
    assert server._running, "server should be running before stop"
    await client.push_frame(p.STOP, p.enc_stop())
    await asyncio.sleep(0.5)
    assert not server._running, "server did not stop after STOP frame"
    await client.close()
    cap_task.cancel()
    try:
        await cap_task
    except asyncio.CancelledError:
        pass
    server._running = False
    await server.ws.stop()


async def test_ping_pong():
    """Client sends PING, server replies PONG to the client."""
    server, injector, ws, cap_task, port = await _start_server()
    client = DeskClient(f"ws://127.0.0.1:{port}")
    await client.connect()
    await client.push_frame(p.HELO, p.enc_hello(role="client"))
    await client.push_frame(p.PING, p.enc_ping())
    frames = await _collect_frames(client, 4, 3.0)
    kinds = {o[0] for o in frames}
    assert "pong" in kinds, f"no pong; have {kinds}"
    await client.close()
    cap_task.cancel()
    try:
        await cap_task
    except asyncio.CancelledError:
        pass
    server._running = False
    await server.ws.stop()


async def test_password_auth():
    """Server with password rejects invalid password and accepts correct password."""
    port = await _find_free_port()
    capture = FakeCapture()
    injector = FakeInjector()
    server = DeskServer(Cfg(port=port, fps=5), capture, injector)
    server.password = "secret123"
    server._running = True
    await server.ws.start()
    cap_task = asyncio.create_task(server._capture_loop())

    # 1. Connect with wrong password -> rejected
    client_bad = RemoteClient(f"ws://127.0.0.1:{port}", password="wrong")
    client_bad_task = asyncio.create_task(client_bad.run())
    await asyncio.sleep(0.4)
    assert client_bad.auth_status == "failed"
    client_bad_task.cancel()

    # 2. Connect with correct password -> accepted
    client_ok = RemoteClient(f"ws://127.0.0.1:{port}", password="secret123")
    client_ok_task = asyncio.create_task(client_ok.run())
    await asyncio.sleep(0.4)
    assert client_ok.auth_status == "ok"
    assert client_ok.remote_w == 12 and client_ok.remote_h == 8

    await client_ok.stop()
    client_ok_task.cancel()
    cap_task.cancel()
    try:
        await cap_task
    except asyncio.CancelledError:
        pass
    server._running = False
    await server.ws.stop()
