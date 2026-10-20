"""Configuration for desk. All knobs a user might want."""
from __future__ import annotations
import os


class Config:
    def __init__(self, **kw):
        self.host = kw.get("host", os.getenv("DESK_HOST", "0.0.0.0"))
        self.port = int(kw.get("port", os.getenv("DESK_PORT", "8765")))
        self.discovery_port = int(kw.get("discovery_port", "8766"))
        self.quality = int(kw.get("quality", "80"))          # jpeg quality
        self.fps = int(kw.get("fps", "30"))                  # frames per second
        self.max_width = int(kw.get("max_width", "1920"))    # scale remote to <= this
        self.max_height = int(kw.get("max_height", "1080"))
        self.ping_interval = float(kw.get("ping_interval", "3.0"))
        self.reconnect_delay = float(kw.get("reconnect_delay", "2.0"))
        self.name = kw.get("name", os.getenv("DESK_NAME", "desk"))
        self.password = str(kw.get("password", os.getenv("DESK_PASSWORD", "")))

    def to_hello(self, role: str, screen_w: int, screen_h: int) -> dict:
        data = {
            "name": self.name,
            "role": role,
            "screen_w": screen_w,
            "screen_h": screen_h,
            "fps": self.fps,
            "quality": self.quality,
            "max_width": self.max_width,
            "max_height": self.max_height,
            "protocol": "desk/1.0",
        }
        if self.password:
            data["password"] = self.password
        return data

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def from_env() -> Config:
    """Build a Config from environment + defaults."""
    return Config()
