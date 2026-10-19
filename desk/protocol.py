"""Binary frame protocol.

Layout of every frame:

    +----------------+---------+----------------+---------------------+
    | MAGIC "DESK"   | TYPE    | LEN (u32 LE)   | PAYLOAD (LEN bytes) |
    +----------------+---------+----------------+---------------------+
    | 4 bytes        | 1 byte  | 4 bytes        | ...                 |

Frames are concatenated in the stream; no length prefix on the whole frame
is needed because LEN is present per frame. All integers are little-endian.
"""

from __future__ import annotations

import json
import struct

MAGIC = b"DESK"  # 4-byte frame delimiter
MAGIC_LEN = len(MAGIC)

class FrameStream:
    """Accumulate WS bytes until complete frames are available."""

    def __init__(self, max_buf: int = 8 * 1024 * 1024):
        self.buf: bytearray = bytearray()
        self.max = max_buf

    def feed(self, data: bytes) -> list:
        self.buf += data
        frames, left = parse_frames(self.buf)
        del self.buf[:len(self.buf) - len(left)]
        return frames

    def flush(self):
        frames, _ = parse_frames(self.buf)
        self.buf.clear()
        return frames

    @property
    def pending(self) -> int:
        return len(self.buf)

    def clear(self):
        self.buf.clear()


# ---- Frame types (u8) -----------------------------------------------------
HELO = 0x01
SCREEN = 0x02
FRAME = 0x03
CURSOR = 0x04
MOVE = 0x05
DOWN = 0x06
UP = 0x07
KEY = 0x08
TEXT = 0x09
PING = 0x0A
PONG = 0x0B
STOP = 0x0C
LOG = 0x0D

# ---- Codec (u8) for FRAME --------------------------------------------------
CODEC_JPEG = 0
CODEC_PNG = 1
CODEC_RAW = 2

# ---- FLAG bits (u8) -------------------------------------------------------
FLAG_FIRST = 0x01   # first frame of this stream (re-scales / re-syncs)
FLAG_FULL = 0x02    # full-screen frame (not a region)

# ---- Mouse buttons ---------------------------------------------------------
MB_LEFT = 0
MB_RIGHT = 1
MB_MIDDLE = 2

# ---- KEY state (u8) --------------------------------------------------------
KEY_DOWN = 1
KEY_UP = 0

# ---- Frame type -> short label ------------------------------------------------
FRAME_NAMES = {
    HELO: "HELO", SCREEN: "SCREEN", FRAME: "FRAME", CURSOR: "CURSOR",
    MOVE: "MOVE", DOWN: "DOWN", UP: "UP", KEY: "KEY", TEXT: "TEXT",
    PING: "PING", PONG: "PONG", STOP: "STOP", LOG: "LOG",
}


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------

class FrameError(ValueError):
    pass


def make_frame(ftype: int, payload: bytes) -> bytes:
    """Encode one frame as bytes."""
    return MAGIC + bytes([ftype & 0xFF]) + struct.pack("<I", len(payload)) + payload


def _unpack_u32(buf: bytes, i: int) -> int:
    return struct.unpack_from("<I", buf, i)[0]


def parse_frames(data: bytearray):
    """Split `data` into (ftype, payload) frames.

    Returns (frames, leftover) where leftover is the trailing bytes belonging to
    an incomplete frame (kept for the next feed).  If no frame is complete,
    leftover is the whole buffer (from the first frame's magic onward).
    """
    out = []
    n = len(data)
    i = 0
    leftover_start = None
    while i < n:
        if n - i < MAGIC_LEN:
            if MAGIC.startswith(bytes(data[i:n])):
                leftover_start = i
                break
            raise FrameError("bad magic at %d" % i)
        if data[i:i + MAGIC_LEN] != MAGIC:
            raise FrameError("bad magic at %d" % i)
        frame_start = i
        i += MAGIC_LEN
        if i >= n:
            leftover_start = frame_start
            break
        ftype = data[i]
        i += 1
        if i + 4 > n:
            leftover_start = frame_start
            break
        plen = _unpack_u32(data, i)
        i += 4
        if i + plen > n:
            leftover_start = frame_start
            break
        payload = bytes(data[i:i + plen])
        i += plen
        out.append((ftype, payload))
    return out, bytes(data[leftover_start:]) if leftover_start is not None else b""


# ---------------------------------------------------------------------------
# Per-type encoders / decoders
# ---------------------------------------------------------------------------

def enc_hello(**kw) -> bytes:
    return make_frame(HELO, json.dumps(kw).encode("utf-8"))


def dec_hello(payload: bytes) -> dict:
    return json.loads(payload.decode("utf-8"))


def enc_screen(width: int, height: int) -> bytes:
    return make_frame(SCREEN, struct.pack("<II", width, height))


def dec_screen(payload: bytes) -> tuple:
    w, h = struct.unpack("<II", payload)
    return w, h


def enc_frame(width: int, height: int, codec: int, image: bytes,
              flags: int = 0) -> bytes:
    body = struct.pack("<II BB", width, height, codec & 0xFF, flags & 0xFF)
    return make_frame(FRAME, body + image)


def dec_frame(payload: bytes):
    if len(payload) < 10:
        raise FrameError("frame too short: %r" % payload[:20])
    w, h, codec, flags = struct.unpack("<II BB", payload[:10])
    return w, h, codec, flags, payload[10:]


def enc_cursor(x: int, y: int) -> bytes:
    return make_frame(CURSOR, struct.pack("<II", x, y))


def dec_cursor(payload: bytes):
    x, y = struct.unpack("<II", payload)
    return x, y


def enc_move(x: int, y: int) -> bytes:
    return make_frame(MOVE, struct.pack("<II", x, y))


def dec_move(payload: bytes):
    x, y = struct.unpack("<II", payload)
    return x, y


decode_move = dec_move


def enc_down(button: int) -> bytes:
    return make_frame(DOWN, struct.pack("<H", button))


def enc_up(button: int) -> bytes:
    return make_frame(UP, struct.pack("<H", button))


def enc_key(vk: int, state: int) -> bytes:
    return make_frame(KEY, struct.pack("<H B", vk & 0xFFFF, state & 0xFF))


def dec_key(payload: bytes):
    vk, state = struct.unpack("<H B", payload)
    return vk, state


def enc_text(text: str) -> bytes:
    return make_frame(TEXT, text.encode("utf-8"))


def dec_text(payload: bytes) -> str:
    return payload.decode("utf-8")


def enc_log(text: str) -> bytes:
    return make_frame(LOG, text.encode("utf-8"))


def dec_log(payload: bytes) -> str:
    return payload.decode("utf-8")


def enc_ping() -> bytes:
    return make_frame(PING, b"")


def enc_pong() -> bytes:
    return make_frame(PONG, b"")


def enc_stop() -> bytes:
    return make_frame(STOP, b"")


# ---------------------------------------------------------------------------
# High-level dispatcher (server / client both use this)
# ---------------------------------------------------------------------------

def decode_frame(ftype: int, payload: bytes):
    """Decode a single frame into a python object. Raise FrameError on bad data."""
    if ftype == HELO:
        return ("hello", dec_hello(payload))
    if ftype == SCREEN:
        return ("screen", dec_screen(payload))
    if ftype == FRAME:
        return ("frame", dec_frame(payload))
    if ftype == CURSOR:
        return ("cursor", dec_cursor(payload))
    if ftype == MOVE:
        return ("move", dec_move(payload))
    if ftype == DOWN:
        return ("down", struct.unpack("<H", payload)[0])
    if ftype == UP:
        return ("up", struct.unpack("<H", payload)[0])
    if ftype == KEY:
        return ("key", dec_key(payload))
    if ftype == TEXT:
        return ("text", dec_text(payload))
    if ftype == PING:
        return ("ping", None)
    if ftype == PONG:
        return ("pong", None)
    if ftype == STOP:
        return ("stop", None)
    if ftype == LOG:
        return ("log", dec_log(payload))
    raise FrameError("unknown frame type 0x%02x" % ftype)
