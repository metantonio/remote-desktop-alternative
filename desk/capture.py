"""Screen capture -> JPEG bytes.

Primary path uses `mss` (fast, cross-platform, native screen grab).
Fallback is PIL `ImageGrab` (or synthetic placeholder if screen is unavailable).

Returns (width, height, jpeg_bytes) at the requested quality.
"""
from __future__ import annotations
import io
import logging
from PIL import Image

log = logging.getLogger("desk.capture")

try:
    import ctypes
    # Make process DPI aware on Windows so screen captures reflect true physical dimensions
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class Capture:
    def __init__(self, screen_index: int = 0, monitor: dict | None = None,
                 quality: int = 80, fps: int = 30, max_width: int = 1920,
                 max_height: int = 1080):
        self.screen_index = screen_index
        self.monitor = monitor
        self.quality = quality
        self.fps = fps
        self.max_width = max_width
        self.max_height = max_height
        self._mss = None

    def _get_mss(self):
        if self._mss is None:
            import mss
            self._mss = mss.mss()
        return self._mss

    def screen_size(self) -> tuple[int, int]:
        try:
            m = self._get_mss()
            if self.monitor:
                return (
                    self.monitor.get("width", self.monitor.get("w", 0)),
                    self.monitor.get("height", self.monitor.get("h", 0))
                )
            sizes = self._screen_size_all()
            if sizes and self.screen_index < len(sizes):
                return sizes[self.screen_index]
            if sizes:
                return sizes[0]
        except Exception:
            pass
        return (self.max_width, self.max_height)

    def _screen_size_all(self) -> list[tuple[int, int]]:
        try:
            m = self._get_mss()
            return [
                (mon.get("width", mon.get("w", 0)), mon.get("height", mon.get("h", 0)))
                for mon in m.monitors[1:]
            ]
        except Exception:
            return []

    def grab_raw(self) -> Image.Image:
        """Return a PIL Image using mss or fallback to PIL ImageGrab."""
        # 1. Try mss
        try:
            m = self._get_mss()
            monitor = self.monitor
            if monitor is None:
                try:
                    monitor = m.monitors[self.screen_index + 1]
                except (IndexError, KeyError):
                    monitor = m.monitors[1] if len(m.monitors) > 1 else m.monitors[0]
            sct_img = m.grab(monitor)
            # Try sct_img.rgb first for macOS, Linux and Windows
            try:
                return Image.frombytes("RGB", sct_img.size, sct_img.rgb)
            except Exception:
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        except Exception as ex:
            log.debug("mss grab failed: %s, trying ImageGrab fallback", ex)

        # 2. Try ImageGrab
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            if img:
                return img.convert("RGB")
        except Exception as ex:
            log.debug("PIL ImageGrab failed: %s", ex)

        # 3. Emergency fallback: solid image
        return Image.new("RGB", (640, 480), color=(30, 30, 30))

    def grab(self) -> tuple[int, int, bytes]:
        """Grab one frame, downscale to max_width/height, return (w, h, jpeg_bytes)."""
        img = self.grab_raw()
        w, h = img.size

        # downscale if needed
        scale = 1.0
        if w > self.max_width:
            scale = self.max_width / float(w)
        if h > self.max_height:
            scale = min(scale, self.max_height / float(h))
        if scale < 1.0:
            nw = max(1, int(w * scale))
            nh = max(1, int(h * scale))
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
            img = img.resize((nw, nh), resample)
            w, h = nw, nh

        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=self.quality, optimize=True)
        return w, h, buf.getvalue()
