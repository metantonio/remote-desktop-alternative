"""Local/controlling side of desk (client).

RemoteClient : headless transport client (connect, receive frames, send input,
              heartbeat).  This is the core that both the GUI and headless
              modes build on.
GuiClient    : pygame window that displays the remote screen (letterboxed) and
              forwards mouse/keyboard into the remote machine.
"""
from __future__ import annotations
import asyncio
import logging
import threading
import queue
from typing import Optional, Callable

from . import protocol
from .transport import DeskClient

log = logging.getLogger("desk.client")

# windows VK codes we can forward
VK = {
    "escape": 0x1B,
    "tab": 0x09,
    "return": 0x0D,
    "enter": 0x0D,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
}
for c in "abcdefghijklmnopqrstuvwxyz":
    VK[c] = 0x41 + (ord(c) - ord('a'))
for d in "0123456789":
    VK[d] = 0x30 + (ord(d) - ord('0'))


class RemoteClient:
    """Headless client: connect, receive frames, optionally send input."""

    def __init__(self, uri: str, password: str = "", on_frame: Optional[Callable] = None):
        self.uri = uri
        self.password = password
        self.on_frame = on_frame
        self.client = DeskClient(uri)
        self.remote_w = 0
        self.remote_h = 0
        self.auth_status = "pending"
        self.auth_error = ""
        self.is_connecting = True
        self.error_message = ""
        self._running = False
        self._lock = threading.Lock()
        self._frame_q = queue.Queue(maxsize=128)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._t: Optional[threading.Thread] = None

    async def _heartbeat(self):
        while self._running:
            await asyncio.sleep(3.0)
            try:
                await self.client.push_frame(protocol.enc_ping())
            except Exception:
                self._running = False
                break

    async def run(self):
        self.is_connecting = True
        try:
            await self.client.connect()
        except Exception as ex:
            self.is_connecting = False
            self._running = False
            self.error_message = f"Connection failed: {ex}"
            log.warning("Could not connect to %s: %s", self.uri, ex)
            return

        self.is_connecting = False
        self._running = True

        hello_data = {
            "role": "client",
            "name": "desk-client",
            "screen_w": 0,
            "screen_h": 0,
            "protocol": "desk/1.0",
        }
        if self.password:
            hello_data["password"] = self.password
        try:
            await self.client.push_frame(protocol.enc_hello(**hello_data))
        except Exception as ex:
            self.error_message = f"Greeting failed: {ex}"
            self._running = False
            return

        hb = asyncio.create_task(self._heartbeat())
        try:
            async for obj in self.client.frames():
                kind, data = obj
                if kind == "hello" and isinstance(data, dict):
                    if data.get("auth") == "unauthorized":
                        self.auth_status = "failed"
                        self.auth_error = data.get("error", "Invalid password")
                        self.error_message = f"Access denied: {self.auth_error}"
                    else:
                        self.auth_status = "ok"
                elif kind == "screen":
                    self.remote_w, self.remote_h = data
                elif kind == "log":
                    log.info("Server log: %s", data)
                if self.on_frame:
                    try:
                        res = self.on_frame(kind, data)
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as ex:
                        log.debug("on_frame error: %s", ex)
                try:
                    self._frame_q.put_nowait(obj)
                except queue.Full:
                    try:
                        self._frame_q.get_nowait()
                        self._frame_q.put_nowait(obj)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass
        except Exception as ex:
            self.error_message = f"Connection error: {ex}"
        finally:
            hb.cancel()
            try:
                await self.client.close()
            except Exception:
                pass
            self._running = False
            self.is_connecting = False
            if not self.error_message:
                self.error_message = "Session closed."

    def start_background(self, on_frame: Optional[Callable] = None):
        if on_frame:
            self.on_frame = on_frame
        self._t = threading.Thread(target=self._run_thread, daemon=True)
        self._t.start()

    def _run_thread(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.run())
        finally:
            self.loop.close()

    def frames(self) -> "FrameQueue":
        return FrameQueue(self._frame_q)

    async def send_move(self, x, y):
        await self.client.push_frame(protocol.enc_move(int(x), int(y)))

    async def send_down(self, b):
        await self.client.push_frame(protocol.enc_down(int(b)))

    async def send_up(self, b):
        await self.client.push_frame(protocol.enc_up(int(b)))

    async def send_key(self, vk, state):
        await self.client.push_frame(protocol.enc_key(int(vk), int(state)))

    async def send_text(self, s):
        await self.client.push_frame(protocol.enc_text(str(s)))

    async def send_stop(self):
        await self.client.push_frame(protocol.enc_stop())

    # --- Thread-safe synchronous helpers for GUI or other threads ---
    def send_move_sync(self, x, y):
        if self.loop and self.loop.is_running() and self._running:
            asyncio.run_coroutine_threadsafe(self.send_move(x, y), self.loop)

    def send_down_sync(self, b):
        if self.loop and self.loop.is_running() and self._running:
            asyncio.run_coroutine_threadsafe(self.send_down(b), self.loop)

    def send_up_sync(self, b):
        if self.loop and self.loop.is_running() and self._running:
            asyncio.run_coroutine_threadsafe(self.send_up(b), self.loop)

    def send_key_sync(self, vk, state):
        if self.loop and self.loop.is_running() and self._running:
            asyncio.run_coroutine_threadsafe(self.send_key(vk, state), self.loop)

    def send_text_sync(self, s):
        if self.loop and self.loop.is_running() and self._running:
            asyncio.run_coroutine_threadsafe(self.send_text(s), self.loop)

    def stop_sync(self):
        self._running = False
        if self.loop and self.loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(self.client.close(), self.loop)
                fut.result(timeout=2.0)
            except Exception:
                pass
        if self._t and self._t.is_alive():
            self._t.join(timeout=2.0)

    async def stop(self):
        self._running = False
        try:
            await self.send_stop()
        except Exception:
            pass
        try:
            await self.client.close()
        except Exception:
            pass

    def is_alive(self):
        return self._running or self.is_connecting


class FrameQueue:
    """Thread-safe wrapper around the frame queue for the GUI loop."""

    def __init__(self, q: queue.Queue):
        self.q = q

    def get(self, timeout=0.02):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None


class GuiClient:
    """pygame window displaying the remote screen + input forwarding."""

    def __init__(self, cfg, uri: str, password: str = ""):
        self.cfg = cfg
        self.uri = uri
        self.password = password
        self.remote = RemoteClient(uri, password=password)
        self.running = True
        self._surface = None
        self._size = (1280, 720)
        self.screen = None
        self._font = None

    def start(self):
        import pygame
        pygame.init()
        self.screen = pygame.display.set_mode(self._size, pygame.RESIZABLE)
        pygame.display.set_caption(f"Desk Remote Client - {self.uri}")
        self._font = pygame.font.SysFont("Arial", 18)
        self.remote.start_background(self._on_remote_frame)
        clock = pygame.time.Clock()
        try:
            while self.running:
                self._process_events()
                self._draw()
                pygame.display.flip()
                clock.tick(60)
        finally:
            self._stop()
            pygame.quit()

    def _stop(self):
        self.running = False
        self.remote.stop_sync()

    def _on_remote_frame(self, kind, data):
        if kind == "screen":
            w, h = data
            self.remote.remote_w, self.remote.remote_h = w, h
            log.info("remote screen %d x %d", w, h)
        elif kind == "frame":
            import io
            import pygame
            w, h, codec, flags, img_bytes = data
            try:
                # Load directly from JPEG bytes to pygame surface
                surf = pygame.image.load(io.BytesIO(img_bytes)).convert()
                self._surface = surf
                self.remote.remote_w, self.remote.remote_h = w, h
            except Exception as ex:
                log.debug("failed to decode frame into pygame surface: %s", ex)
        elif kind == "log":
            log.info("remote log: %s", data)

    def _process_events(self):
        import pygame
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.VIDEORESIZE:
                self._size = (e.w, e.h)
                self.screen = pygame.display.set_mode(self._size, pygame.RESIZABLE)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 2, 3):
                # pygame: 1=left, 2=middle, 3=right
                # desk protocol: MB_LEFT=0, MB_RIGHT=1, MB_MIDDLE=2
                mb_code = 0 if e.button == 1 else (1 if e.button == 3 else 2)
                coords = self._local_to_remote(e.pos)
                if coords:
                    rx, ry = coords
                    self.remote.send_move_sync(rx, ry)
                    self.remote.send_down_sync(mb_code)
            elif e.type == pygame.MOUSEBUTTONUP and e.button in (1, 2, 3):
                mb_code = 0 if e.button == 1 else (1 if e.button == 3 else 2)
                coords = self._local_to_remote(e.pos)
                if coords:
                    rx, ry = coords
                    self.remote.send_move_sync(rx, ry)
                self.remote.send_up_sync(mb_code)
            elif e.type == pygame.MOUSEMOTION:
                coords = self._local_to_remote(e.pos)
                if coords:
                    rx, ry = coords
                    self.remote.send_move_sync(rx, ry)
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    if (pygame.key.get_mods() & pygame.KMOD_SHIFT) or not self.remote.is_alive():
                        self.running = False
                    else:
                        self._send_key(e.key, 1)
                else:
                    self._send_key(e.key, 1)
            elif e.type == pygame.KEYUP:
                self._send_key(e.key, 0)

    def _send_key(self, k, state):
        import pygame
        name = pygame.key.name(k).lower()
        vk = VK.get(name)
        if vk is not None:
            self.remote.send_key_sync(vk, state)

    def _local_to_remote(self, pos):
        rw, rh = self.remote.remote_w, self.remote.remote_h
        if rw <= 0 or rh <= 0:
            return None
        sw, sh = self.screen.get_size()
        scale = min(sw / rw, sh / rh)
        dw = int(rw * scale)
        dh = int(rh * scale)
        ox = (sw - dw) // 2
        oy = (sh - dh) // 2
        dx = pos[0] - ox
        dy = pos[1] - oy
        if dx < 0 or dx >= dw or dy < 0 or dy >= dh:
            return None
        rx = int(dx * rw / dw)
        ry = int(dy * rh / dh)
        return rx, ry

    def _draw(self):
        import pygame
        self.screen.fill((20, 20, 25))
        rw, rh = self.remote.remote_w, self.remote.remote_h
        sw, sh = self.screen.get_size()
        if rw > 0 and rh > 0 and self._surface is not None and self.remote._running:
            scale = min(sw / rw, sh / rh)
            dw = max(1, int(rw * scale))
            dh = max(1, int(rh * scale))
            ox = (sw - dw) // 2
            oy = (sh - dh) // 2
            scaled_surf = pygame.transform.smoothscale(self._surface, (dw, dh))
            self.screen.blit(scaled_surf, (ox, oy))
            pygame.draw.rect(self.screen, (70, 70, 80), (ox, oy, dw, dh), 1)
        else:
            if self.remote.auth_status == "failed":
                msg = f"ACCESS DENIED: {self.remote.auth_error or 'Invalid password'}"
                color = (255, 90, 90)
            elif self.remote.is_connecting:
                msg = f"Connecting to {self.uri}..."
                color = (180, 180, 230)
            elif self.remote.is_alive():
                msg = "Connected. Waiting for display stream..."
                color = (160, 220, 160)
            else:
                err = self.remote.error_message or "Connection closed"
                msg = f"DISCONNECTED: {err}"
                color = (255, 120, 120)

            txt = self._font.render(msg, True, color)
            self.screen.blit(txt, (sw // 2 - txt.get_width() // 2, sh // 2 - txt.get_height() // 2))

            sub_txt = self._font.render("Press Shift+ESC or close window to exit", True, (130, 130, 140))
            self.screen.blit(sub_txt, (sw // 2 - sub_txt.get_width() // 2, sh // 2 + 25))

        # Status overlay at top
        status = f"desk [{self.uri}] - {rw}x{rh} | Shift+ESC to exit"
        status_txt = self._font.render(status, True, (240, 240, 240), (40, 40, 50))
        self.screen.blit(status_txt, (10, 10))
