"""X11 screen capture and explicit mouse/keyboard actions for the local MCP."""

from __future__ import annotations

import io
import os
import subprocess
import time

from PIL import Image as PILImage
from Xlib import X, XK, display as xdisplay
from Xlib.ext import xtest
from mss import mss


KEY_ALIASES = {
    "ctrl": "Control_L", "control": "Control_L", "alt": "Alt_L",
    "shift": "Shift_L", "super": "Super_L", "win": "Super_L",
    "enter": "Return", "return": "Return", "esc": "Escape",
    "escape": "Escape", "backspace": "BackSpace", "delete": "Delete",
    "space": "space", "tab": "Tab", "up": "Up", "down": "Down",
    "left": "Left", "right": "Right", "home": "Home", "end": "End",
    "pageup": "Prior", "pagedown": "Next",
}
BUTTONS = {"left": 1, "middle": 2, "right": 3}


def _display():
    return xdisplay.Display(os.environ.get("DISPLAY", ":0"))


def screen_info() -> dict:
    with mss() as capture:
        monitors = [{"index": i, "left": m["left"], "top": m["top"],
                     "width": m["width"], "height": m["height"]}
                    for i, m in enumerate(capture.monitors)]
    conn = _display()
    try:
        pointer = conn.screen().root.query_pointer()
        return {"display": os.environ.get("DISPLAY", ":0"), "monitors": monitors,
                "mouse": {"x": pointer.root_x, "y": pointer.root_y},
                "note": "Monitor 0 is the combined desktop; mouse coordinates use the combined desktop."}
    finally:
        conn.close()


def screenshot(monitor: int = 0) -> bytes:
    with mss() as capture:
        if not isinstance(monitor, int) or not 0 <= monitor < len(capture.monitors):
            raise ValueError("Unknown monitor index; call desktop_info first")
        shot = capture.grab(capture.monitors[monitor])
    image = PILImage.frombytes("RGB", shot.size, shot.rgb)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=78, optimize=True)
    if output.tell() > 8_000_000:
        raise ValueError("Screenshot exceeds 8 MB tunnel-safe limit")
    return output.getvalue()


def _coordinates(conn, x: int, y: int) -> tuple[int, int]:
    screen = conn.screen()
    x, y = int(x), int(y)
    if not (0 <= x < screen.width_in_pixels and 0 <= y < screen.height_in_pixels):
        raise ValueError("Coordinates are outside the X11 desktop; call desktop_info")
    return x, y


def move_mouse(x: int, y: int) -> dict:
    conn = _display()
    try:
        x, y = _coordinates(conn, x, y)
        xtest.fake_input(conn, X.MotionNotify, x=x, y=y)
        conn.sync()
        return {"x": x, "y": y}
    finally:
        conn.close()


def click_mouse(x: int, y: int, button: str = "left", clicks: int = 1) -> dict:
    if button not in BUTTONS or clicks not in (1, 2):
        raise ValueError("button must be left/middle/right; clicks must be 1 or 2")
    conn = _display()
    try:
        x, y = _coordinates(conn, x, y)
        xtest.fake_input(conn, X.MotionNotify, x=x, y=y)
        for n in range(clicks):
            xtest.fake_input(conn, X.ButtonPress, BUTTONS[button])
            xtest.fake_input(conn, X.ButtonRelease, BUTTONS[button])
            conn.sync()
            if n + 1 < clicks:
                time.sleep(0.12)
        return {"x": x, "y": y, "button": button, "clicks": clicks}
    finally:
        conn.close()


def scroll_mouse(x: int, y: int, steps: int) -> dict:
    steps = int(steps)
    if not -20 <= steps <= 20 or steps == 0:
        raise ValueError("steps must be between -20 and 20, excluding zero")
    conn = _display()
    try:
        x, y = _coordinates(conn, x, y)
        xtest.fake_input(conn, X.MotionNotify, x=x, y=y)
        button = 4 if steps > 0 else 5
        for _ in range(abs(steps)):
            xtest.fake_input(conn, X.ButtonPress, button)
            xtest.fake_input(conn, X.ButtonRelease, button)
        conn.sync()
        return {"x": x, "y": y, "steps": steps}
    finally:
        conn.close()


def hotkey(keys: list[str]) -> dict:
    if not isinstance(keys, list) or not 1 <= len(keys) <= 5:
        raise ValueError("Supply 1-5 keys, for example ['ctrl', 's']")
    conn = _display()
    pressed = []
    try:
        for key in keys:
            if not isinstance(key, str) or not 1 <= len(key) <= 20:
                raise ValueError("Invalid key name")
            name = KEY_ALIASES.get(key.lower(), key)
            sym = XK.string_to_keysym(name)
            code = conn.keysym_to_keycode(sym) if sym else 0
            if not code:
                raise ValueError(f"Key not available on current X11 layout: {key}")
            xtest.fake_input(conn, X.KeyPress, code)
            pressed.append(code)
        conn.sync()
        return {"keys": keys}
    finally:
        for code in reversed(pressed):
            xtest.fake_input(conn, X.KeyRelease, code)
        conn.sync()
        conn.close()


def type_text(text: str) -> dict:
    """Paste Unicode text using the X11 clipboard; this replaces clipboard content."""
    if not isinstance(text, str) or not text or len(text) > 4000 or "\x00" in text:
        raise ValueError("Provide 1-4000 characters without NUL")
    result = subprocess.run(["xclip", "-selection", "clipboard", "-i"],
                            input=text.encode("utf-8"), capture_output=True, timeout=5)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[:500])
    hotkey(["ctrl", "v"])
    return {"characters": len(text), "clipboard_replaced": True}
