"""Unit tests for the desk binary protocol.

enc_* returns a complete frame (magic+type+len+payload).  dec_* decodes a
payload.  parse_frames() splits a byte stream.  decode_frame() gives (kind, data).
"""
from __future__ import annotations
import struct
import pytest
from desk import protocol as p


def _frames(blob: bytes):
    frames, left = p.parse_frames(bytearray(blob))
    assert not left, "trailing bytes: %r" % left[-64:]
    return frames


class TestFrameRoundTrip:
    def test_magic_header(self):
        f = p.enc_move(1, 2)
        assert f[:4] == b"DESK"
        assert f[4] == p.MOVE
        assert struct.unpack("<I", f[5:9])[0] == 8
        # body: 8 bytes of payload
        assert len(f) == 4 + 1 + 4 + 8

    def test_move_roundtrip(self):
        f = p.enc_move(100, 200)
        ftype, payload = _frames(f)[0]
        assert ftype == p.MOVE
        assert p.dec_move(payload) == (100, 200)
        assert p.decode_frame(p.MOVE, payload) == ("move", (100, 200))

    def test_screen_roundtrip(self):
        f = p.enc_screen(1920, 1080)
        ftype, payload = _frames(f)[0]
        assert ftype == p.SCREEN
        assert p.dec_screen(payload) == (1920, 1080)
        assert p.decode_frame(p.SCREEN, payload) == ("screen", (1920, 1080))

    def test_hello_roundtrip(self):
        f = p.enc_hello(name="x", role="client")
        ftype, payload = _frames(f)[0]
        assert ftype == p.HELO
        obj = p.decode_frame(p.HELO, payload)
        assert obj == ("hello", {"name": "x", "role": "client"})

    def test_frame_roundtrip(self):
        img = b"\xff\xd8\xff\xd9"
        f = p.enc_frame(4, 5, p.CODEC_JPEG, img, p.FLAG_FIRST)
        ftype, payload = _frames(f)[0]
        assert ftype == p.FRAME
        obj = p.decode_frame(p.FRAME, payload)
        assert obj[0] == "frame"
        w, h, codec, flags, data = obj[1]
        assert (w, h) == (4, 5)
        assert codec == p.CODEC_JPEG
        assert flags & p.FLAG_FIRST
        assert data == img

    def test_down_up(self):
        f = p.enc_down(1)
        ftype, payload = _frames(f)[0]
        assert p.decode_frame(p.DOWN, payload) == ("down", 1)
        f = p.enc_up(2)
        ftype, payload = _frames(f)[0]
        assert p.decode_frame(p.UP, payload) == ("up", 2)

    def test_key(self):
        f = p.enc_key(0x7E, 1)
        ftype, payload = _frames(f)[0]
        assert p.decode_frame(p.KEY, payload) == ("key", (0x7E, 1))

    def test_text(self):
        f = p.enc_text("héllo wörld")
        ftype, payload = _frames(f)[0]
        assert p.decode_frame(p.TEXT, payload) == ("text", "héllo wörld")

    def test_ping_pong_stop(self):
        for ft, obj in [(p.PING, "ping"), (p.PONG, "pong"), (p.STOP, "stop")]:
            f = p.make_frame(ft, b"")
            ftype, payload = _frames(f)[0]
            assert p.decode_frame(ftype, payload) == (obj, None)

    def test_log(self):
        f = p.enc_log("hi there")
        ftype, payload = _frames(f)[0]
        assert p.decode_frame(p.LOG, payload) == ("log", "hi there")

    def test_multi_frame(self):
        a = p.enc_move(10, 20)
        b = p.enc_down(0)
        frames = _frames(a + b)
        assert len(frames) == 2
        assert frames[0][0] == p.MOVE
        assert frames[1][0] == p.DOWN
        x, y = p.dec_move(frames[0][1])
        assert (x, y) == (10, 20)


class TestSplitFrames:
    def test_split_in_middle(self):
        f = p.enc_frame(16, 16, p.CODEC_JPEG, b"X" * 100)
        mid = 5
        stream = p.FrameStream()
        frames = stream.feed(f[:mid])
        assert not frames
        frames = stream.feed(f[mid:])
        assert len(frames) == 1
        ftype, payload = frames[0]
        assert ftype == p.FRAME
        kind, frame_data = p.decode_frame(ftype, payload)
        assert kind == "frame"
        w, h, codec, flags, data = frame_data
        assert (w, h) == (16, 16)
        assert data == b"X" * 100
        assert stream.pending == 0

    def test_split_in_header(self):
        f = p.enc_move(1, 1)
        stream = p.FrameStream()
        stream.feed(f[:1])
        frames = stream.feed(f[1:])
        assert len(frames) == 1
        assert frames[0][0] == p.MOVE

    def test_multiple_partial(self):
        a = p.enc_move(1, 2)
        b = p.enc_down(0)
        stream = p.FrameStream()
        frames = stream.feed(bytes(a))
        assert len(frames) == 1
        assert frames[0][0] == p.MOVE
        frames = stream.feed(bytes(b))
        assert len(frames) == 1
        assert frames[0][0] == p.DOWN


class TestBadMagic:
    def test_bad_magic(self):
        f = p.enc_ping()
        bad = b"XXXX" + f[4:]
        stream = p.FrameStream()
        with pytest.raises(p.FrameError):
            stream.feed(bad)

    def test_short_payload_is_leftover(self):
        # a frame cut off mid-payload is not an error; it stays as leftover
        f = p.enc_move(1, 1)
        stream = p.FrameStream()
        stream.feed(f[:12])  # incomplete (12 < 17)
        frames = stream.feed(b"")
        assert not frames  # still incomplete
        assert len(stream.buf) == 12
        # feed the rest -> completes the frame
        frames = stream.feed(f[12:])
        assert len(frames) == 1
        assert frames[0][0] == p.MOVE
        x, y = p.decode_move(frames[0][1])
        assert (x, y) == (1, 1)
