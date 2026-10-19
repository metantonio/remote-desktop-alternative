"""Input injection into the local (controlled) machine.

Windows: raw SendInput (absolute mouse + VK keyboard) with fallback to pynput.
Other OS: pynput.
"""
from __future__ import annotations
import logging
import platform
import ctypes
from ctypes import wintypes

log = logging.getLogger("desk.injector")

# Windows Virtual-Key Codes
VK = {
    "Escape": 0x1B,
    "Tab": 0x09,
    "Return": 0x0D,
    "Enter": 0x0D,
    "Space": 0x20,
    "Backspace": 0x08,
    "Delete": 0x2E,
    "Left": 0x25,
    "Up": 0x26,
    "Right": 0x27,
    "Down": 0x28,
    "Home": 0x24,
    "End": 0x23,
    "PageUp": 0x21,
    "PageDown": 0x22,
}
for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    VK[c] = 0x41 + (ord(c) - ord('A'))
    VK[c.lower()] = 0x41 + (ord(c) - ord('A'))
for d in "0123456789":
    VK[d] = 0x30 + (ord(d) - ord('0'))


class Injector:
    def __init__(self, backend: str | None = None):
        if backend is None:
            backend = "sendinput" if platform.system() == "Windows" else "pynput"
        self.backend = backend
        self._impl = None
        if backend == "sendinput":
            try:
                self._impl = _SendInput()
            except Exception as ex:
                log.warning("SendInput init failed (%s), falling back to pynput", ex)
                self.backend = "pynput"
                self._impl = _Pynput()
        else:
            self._impl = _Pynput()

    # ---- mouse ----
    def move(self, x: int, y: int):
        self._impl.move(x, y)

    def down(self, button: int):
        name = self._bname(button)
        self._impl.down(name)

    def up(self, button: int):
        name = self._bname(button)
        self._impl.up(name)

    def click(self, x: int, y: int, button: int = 0):
        self.move(x, y)
        self.down(button)
        self.up(button)

    def _bname(self, b: int) -> str:
        return {0: "left", 1: "right", 2: "middle"}.get(b, "left")

    # ---- keyboard ----
    def key(self, vk: int, state: int):
        self._impl.key(vk, state)

    def text(self, s: str):
        self._impl.text(s)

    def shutdown(self):
        if hasattr(self._impl, "stop"):
            self._impl.stop()


# ---------------------------------------------------------------------------
# Windows SendInput via ctypes
# ---------------------------------------------------------------------------
class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]


class _SendInput:
    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1

    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_ABSOLUTE = 0x8000

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004

    def __init__(self):
        assert platform.system() == "Windows", "SendInput backend requires Windows"
        self._user32 = ctypes.windll.user32
        # SM_CXSCREEN = 0, SM_CYSCREEN = 1
        self._width = max(1, self._user32.GetSystemMetrics(0))
        self._height = max(1, self._user32.GetSystemMetrics(1))

    def move(self, x: int, y: int):
        dx = int(x * 65535 / self._width)
        dy = int(y * 65535 / self._height)
        inp = _INPUT(type=self.INPUT_MOUSE)
        inp.u.mi.dx = dx
        inp.u.mi.dy = dy
        inp.u.mi.dwFlags = self.MOUSEEVENTF_MOVE | self.MOUSEEVENTF_ABSOLUTE
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def down(self, bname: str):
        flags = {
            "left": self.MOUSEEVENTF_LEFTDOWN,
            "right": self.MOUSEEVENTF_RIGHTDOWN,
            "middle": self.MOUSEEVENTF_MIDDLEDOWN,
        }.get(bname, self.MOUSEEVENTF_LEFTDOWN)
        inp = _INPUT(type=self.INPUT_MOUSE)
        inp.u.mi.dwFlags = flags
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def up(self, bname: str):
        flags = {
            "left": self.MOUSEEVENTF_LEFTUP,
            "right": self.MOUSEEVENTF_RIGHTUP,
            "middle": self.MOUSEEVENTF_MIDDLEUP,
        }.get(bname, self.MOUSEEVENTF_LEFTUP)
        inp = _INPUT(type=self.INPUT_MOUSE)
        inp.u.mi.dwFlags = flags
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def key(self, vk: int, state: int):
        flags = 0 if state else self.KEYEVENTF_KEYUP
        inp = _INPUT(type=self.INPUT_KEYBOARD)
        inp.u.ki.wVk = vk & 0xFFFF
        inp.u.ki.dwFlags = flags
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def text(self, s: str):
        for ch in s:
            vk = VK.get(ch)
            if vk is not None:
                self.key(vk, 1)
                self.key(vk, 0)
            else:
                # Unicode SendInput
                code = ord(ch)
                inp = _INPUT(type=self.INPUT_KEYBOARD)
                inp.u.ki.wScan = code
                inp.u.ki.dwFlags = self.KEYEVENTF_UNICODE
                self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
                inp.u.ki.dwFlags = self.KEYEVENTF_UNICODE | self.KEYEVENTF_KEYUP
                self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


# ---------------------------------------------------------------------------
# pynput fallback / cross-platform
# ---------------------------------------------------------------------------
class _Pynput:
    def __init__(self):
        from pynput.mouse import Controller as M, Button
        from pynput.keyboard import Controller as K, Key, KeyCode
        self._m = M()
        self._k = K()
        self._Button = Button
        self._Key = Key
        self._KeyCode = KeyCode

    def move(self, x: int, y: int):
        self._m.position = (x, y)

    def down(self, bname: str):
        btn = self._Button.left if bname == "left" else (
            self._Button.right if bname == "right" else self._Button.middle)
        self._m.press(btn)

    def up(self, bname: str):
        btn = self._Button.left if bname == "left" else (
            self._Button.right if bname == "right" else self._Button.middle)
        self._m.release(btn)

    def key(self, vk: int, state: int):
        try:
            k = self._KeyCode.from_vk(vk)
            if state:
                self._k.press(k)
            else:
                self._k.release(k)
        except Exception:
            pass

    def text(self, s: str):
        self._k.type(s)

    def stop(self):
        pass
