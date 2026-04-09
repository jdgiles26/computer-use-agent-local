#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import Quartz
from AppKit import NSScreen, NSWorkspace


KEY_CODES = {
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "6": 22,
    "5": 23,
    "=": 24,
    "9": 25,
    "7": 26,
    "-": 27,
    "8": 28,
    "0": 29,
    "]": 30,
    "o": 31,
    "u": 32,
    "[": 33,
    "i": 34,
    "p": 35,
    "l": 37,
    "j": 38,
    "'": 39,
    "k": 40,
    ";": 41,
    "\\": 42,
    ",": 43,
    "/": 44,
    "n": 45,
    "m": 46,
    ".": 47,
    "`": 50,
    "return": 36,
    "enter": 36,
    "tab": 48,
    "space": 49,
    "delete": 51,
    "escape": 53,
    "esc": 53,
    "command": 55,
    "shift": 56,
    "capslock": 57,
    "option": 58,
    "alt": 58,
    "control": 59,
    "ctrl": 59,
    "rightshift": 60,
    "rightoption": 61,
    "rightcontrol": 62,
    "function": 63,
    "f17": 64,
    "volumeup": 72,
    "volumedown": 73,
    "mute": 74,
    "f18": 79,
    "f19": 80,
    "f20": 90,
    "f5": 96,
    "f6": 97,
    "f7": 98,
    "f3": 99,
    "f8": 100,
    "f9": 101,
    "f11": 103,
    "f13": 105,
    "f16": 106,
    "f14": 107,
    "f10": 109,
    "f12": 111,
    "f15": 113,
    "help": 114,
    "home": 115,
    "pageup": 116,
    "forwarddelete": 117,
    "f4": 118,
    "end": 119,
    "f2": 120,
    "pagedown": 121,
    "f1": 122,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
}

MODIFIER_FLAGS = {
    "command": Quartz.kCGEventFlagMaskCommand,
    "cmd": Quartz.kCGEventFlagMaskCommand,
    "shift": Quartz.kCGEventFlagMaskShift,
    "option": Quartz.kCGEventFlagMaskAlternate,
    "alt": Quartz.kCGEventFlagMaskAlternate,
    "control": Quartz.kCGEventFlagMaskControl,
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "fn": Quartz.kCGEventFlagMaskSecondaryFn,
    "function": Quartz.kCGEventFlagMaskSecondaryFn,
}

MOUSE_BUTTONS = {
    "left": (
        Quartz.kCGMouseButtonLeft,
        Quartz.kCGEventLeftMouseDown,
        Quartz.kCGEventLeftMouseUp,
        Quartz.kCGEventLeftMouseDragged,
    ),
    "right": (
        Quartz.kCGMouseButtonRight,
        Quartz.kCGEventRightMouseDown,
        Quartz.kCGEventRightMouseUp,
        Quartz.kCGEventRightMouseDragged,
    ),
    "center": (
        Quartz.kCGMouseButtonCenter,
        Quartz.kCGEventOtherMouseDown,
        Quartz.kCGEventOtherMouseUp,
        Quartz.kCGEventOtherMouseDragged,
    ),
}

SETTINGS_PANELS = {
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "screen_recording": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
}


class DesktopControlError(RuntimeError):
    pass


class DesktopTool:
    def __init__(self, workspace_root: Path, output_dir: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.output_dir = output_dir.resolve()
        self.desktop_output_dir = self.output_dir / "desktop"
        self.desktop_output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def has_accessibility_access() -> bool:
        try:
            return bool(Quartz.CGPreflightPostEventAccess())
        except Exception:
            return True

    @staticmethod
    def open_settings_panel(panel: str) -> str:
        name = panel.strip().lower()
        if name not in SETTINGS_PANELS:
            raise DesktopControlError(f"Unsupported settings panel: {panel}")
        proc = subprocess.run(
            ["/usr/bin/open", SETTINGS_PANELS[name]],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise DesktopControlError(proc.stderr.strip() or f"Could not open settings panel {panel}")
        return f"Opened macOS settings panel: {name}"

    @staticmethod
    def _require_accessibility() -> None:
        if not DesktopTool.has_accessibility_access():
            raise DesktopControlError(
                "Accessibility permission is required for desktop mouse/keyboard control. "
                "Enable it for Terminal or your Python app in System Settings > Privacy & Security > Accessibility."
            )

    @staticmethod
    def normalize_key_name(key: str) -> str:
        return key.strip().lower().replace("arrow", "")

    @staticmethod
    def normalize_modifiers(modifiers: list[str] | None) -> list[str]:
        result = []
        for modifier in modifiers or []:
            name = modifier.strip().lower()
            if name not in MODIFIER_FLAGS:
                raise DesktopControlError(f"Unsupported modifier: {modifier}")
            result.append(name)
        return result

    @staticmethod
    def virtual_screen_bounds() -> dict[str, int]:
        screens = list(NSScreen.screens())
        if not screens:
            return {"x": 0, "y": 0, "width": 0, "height": 0}
        min_x = min(int(screen.frame().origin.x) for screen in screens)
        min_y = min(int(screen.frame().origin.y) for screen in screens)
        max_x = max(int(screen.frame().origin.x + screen.frame().size.width) for screen in screens)
        max_y = max(int(screen.frame().origin.y + screen.frame().size.height) for screen in screens)
        return {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}

    @staticmethod
    def current_mouse_position() -> dict[str, int]:
        point = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        return {"x": int(point.x), "y": int(point.y)}

    @staticmethod
    def clamp_point(x: int, y: int) -> tuple[int, int]:
        screen = DesktopTool.virtual_screen_bounds()
        clamped_x = max(screen["x"], min(int(x), screen["x"] + screen["width"] - 1))
        clamped_y = max(screen["y"], min(int(y), screen["y"] + screen["height"] - 1))
        return clamped_x, clamped_y

    @staticmethod
    def _mouse_event(event_type: int, x: int, y: int, button: int) -> None:
        event = Quartz.CGEventCreateMouseEvent(None, event_type, (x, y), button)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    @staticmethod
    def _key_event(key_code: int, is_down: bool, flags: int = 0) -> None:
        event = Quartz.CGEventCreateKeyboardEvent(None, key_code, is_down)
        Quartz.CGEventSetFlags(event, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    @staticmethod
    def _unicode_key_event(text: str, is_down: bool) -> None:
        event = Quartz.CGEventCreateKeyboardEvent(None, 0, is_down)
        Quartz.CGEventKeyboardSetUnicodeString(event, len(text), text)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    @staticmethod
    def key_code_for(key: str) -> int:
        normalized = DesktopTool.normalize_key_name(key)
        if normalized not in KEY_CODES:
            raise DesktopControlError(f"Unsupported key: {key}")
        return KEY_CODES[normalized]

    def screenshot(self, path: str | None = None) -> str:
        target = self.desktop_output_dir / f"screenshot-{int(time.time())}.png"
        if path:
            candidate = Path(path)
            target = (self.workspace_root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
            try:
                target.relative_to(self.workspace_root)
            except ValueError as exc:
                raise DesktopControlError("Screenshot path must stay inside the workspace.") from exc
            target.parent.mkdir(parents=True, exist_ok=True)

        proc = subprocess.run(
            ["/usr/sbin/screencapture", "-x", str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = proc.stderr.strip() or "screencapture failed"
            raise DesktopControlError(
                f"{detail}. Grant Screen Recording permission to Terminal or your Python app in "
                "System Settings > Privacy & Security > Screen Recording."
            )
        return f"Saved screenshot to {target}"

    def get_state(
        self,
        include_running_apps: bool = False,
        include_clipboard: bool = False,
    ) -> str:
        frontmost = NSWorkspace.sharedWorkspace().frontmostApplication()
        app_name = None
        bundle_id = None
        if frontmost is not None:
            app_name = frontmost.localizedName()
            bundle_id = frontmost.bundleIdentifier()
        payload: dict[str, Any] = {
            "frontmost_app": app_name,
            "frontmost_bundle_id": bundle_id,
            "mouse": self.current_mouse_position(),
            "screen": self.virtual_screen_bounds(),
            "accessibility_access": self.has_accessibility_access(),
        }
        if include_running_apps:
            payload["running_apps"] = [
                app.localizedName()
                for app in NSWorkspace.sharedWorkspace().runningApplications()
                if app.localizedName()
            ][:20]
        if include_clipboard:
            payload["clipboard"] = self.get_clipboard(limit=500)
        return json.dumps(payload, ensure_ascii=True, indent=2)

    def move_mouse(self, x: int, y: int) -> str:
        self._require_accessibility()
        x, y = self.clamp_point(x, y)
        self._mouse_event(Quartz.kCGEventMouseMoved, x, y, Quartz.kCGMouseButtonLeft)
        return f"Moved mouse to ({x}, {y})"

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> str:
        self._require_accessibility()
        button_name = button.strip().lower()
        if button_name not in MOUSE_BUTTONS:
            raise DesktopControlError(f"Unsupported mouse button: {button}")
        mouse_button, down_event, up_event, _ = MOUSE_BUTTONS[button_name]
        x, y = self.clamp_point(x, y)
        self._mouse_event(Quartz.kCGEventMouseMoved, x, y, mouse_button)
        for _ in range(max(1, int(clicks))):
            self._mouse_event(down_event, x, y, mouse_button)
            self._mouse_event(up_event, x, y, mouse_button)
            time.sleep(0.05)
        return f"Clicked {button_name} at ({x}, {y}) x{max(1, int(clicks))}"

    def drag_mouse(self, x: int, y: int, button: str = "left") -> str:
        self._require_accessibility()
        button_name = button.strip().lower()
        if button_name not in MOUSE_BUTTONS:
            raise DesktopControlError(f"Unsupported mouse button: {button}")
        mouse_button, down_event, up_event, drag_event = MOUSE_BUTTONS[button_name]
        current = self.current_mouse_position()
        start_x, start_y = self.clamp_point(current["x"], current["y"])
        end_x, end_y = self.clamp_point(x, y)
        self._mouse_event(down_event, start_x, start_y, mouse_button)
        steps = 12
        for step in range(1, steps + 1):
            next_x = start_x + ((end_x - start_x) * step) / steps
            next_y = start_y + ((end_y - start_y) * step) / steps
            self._mouse_event(drag_event, int(next_x), int(next_y), mouse_button)
            time.sleep(0.01)
        self._mouse_event(up_event, end_x, end_y, mouse_button)
        return f"Dragged mouse to ({end_x}, {end_y}) with {button_name} button"

    def scroll(self, dx: int = 0, dy: int = -200) -> str:
        self._require_accessibility()
        event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 2, int(dy), int(dx))
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        return f"Scrolled by dx={int(dx)} dy={int(dy)}"

    def type_text(self, text: str) -> str:
        self._require_accessibility()
        if not text:
            raise DesktopControlError("desktop_type_text requires text")
        for char in text:
            self._unicode_key_event(char, True)
            self._unicode_key_event(char, False)
            time.sleep(0.01)
        return f"Typed {len(text)} characters"

    def press_key(self, key: str, modifiers: list[str] | None = None) -> str:
        self._require_accessibility()
        modifier_names = self.normalize_modifiers(modifiers)
        flags = 0
        modifier_key_codes = []
        for modifier in modifier_names:
            flags |= MODIFIER_FLAGS[modifier]
            modifier_key_codes.append(self.key_code_for(modifier))

        for code in modifier_key_codes:
            self._key_event(code, True, flags)
        key_code = self.key_code_for(key)
        self._key_event(key_code, True, flags)
        self._key_event(key_code, False, flags)
        for code in reversed(modifier_key_codes):
            self._key_event(code, False, 0)
        if modifier_names:
            return f"Pressed {'+'.join(modifier_names + [key])}"
        return f"Pressed {key}"

    def hotkey(self, keys: list[str]) -> str:
        if len(keys) < 2:
            raise DesktopControlError("desktop_hotkey requires at least two keys")
        *modifiers, key = keys
        return self.press_key(key, modifiers)

    def get_clipboard(self, limit: int = 2000) -> str:
        proc = subprocess.run(
            ["/usr/bin/pbpaste"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise DesktopControlError(proc.stderr.strip() or "Could not read clipboard")
        text = proc.stdout or ""
        if len(text) > limit:
            text = f"{text[:limit]}\n\n[truncated {len(text) - limit} chars]"
        return text

    def set_clipboard(self, text: str) -> str:
        proc = subprocess.run(
            ["/usr/bin/pbcopy"],
            input=text,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise DesktopControlError(proc.stderr.strip() or "Could not write clipboard")
        return f"Copied {len(text)} characters to clipboard"

    def paste_text(self, text: str) -> str:
        if not text:
            raise DesktopControlError("desktop_paste_text requires text")
        self.set_clipboard(text)
        self.press_key("v", ["command"])
        return f"Pasted {len(text)} characters via clipboard"

    def open_app(self, app_name: str) -> str:
        if not app_name.strip():
            raise DesktopControlError("desktop_open_app requires app_name")
        proc = subprocess.run(
            ["/usr/bin/open", "-a", app_name],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise DesktopControlError(proc.stderr.strip() or f"Could not open app {app_name}")
        time.sleep(0.5)
        return f"Opened app {app_name}"

    def wait(self, seconds: float) -> str:
        value = max(0.0, min(float(seconds), 30.0))
        time.sleep(value)
        return f"Waited {value:.2f} seconds"
