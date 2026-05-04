#!/usr/bin/env python3
"""
key_probe.py

Shows exactly what the terminal sends to Python for keyboard shortcuts.

Useful for comparing:
- conhost / cmd.exe
- Windows Terminal
- PowerShell
- Git Bash / MSYS
- WSL
- Linux/macOS terminals

Exit: Ctrl+Q
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime

IS_WINDOWS = os.name == "nt"


CTRL_NAMES = {
    0x00: "NUL / Ctrl+Space / Ctrl+@",
    0x01: "SOH / Ctrl+A",
    0x02: "STX / Ctrl+B",
    0x03: "ETX / Ctrl+C",
    0x04: "EOT / Ctrl+D",
    0x05: "ENQ / Ctrl+E",
    0x06: "ACK / Ctrl+F",
    0x07: "BEL / Ctrl+G",
    0x08: "BS / Ctrl+H / Backspace",
    0x09: "HT / Tab / Ctrl+I",
    0x0A: "LF / Ctrl+J",
    0x0B: "VT / Ctrl+K",
    0x0C: "FF / Ctrl+L",
    0x0D: "CR / Enter / Ctrl+M",
    0x0E: "SO / Ctrl+N",
    0x0F: "SI / Ctrl+O",
    0x10: "DLE / Ctrl+P",
    0x11: "DC1 / Ctrl+Q",
    0x12: "DC2 / Ctrl+R",
    0x13: "DC3 / Ctrl+S",
    0x14: "DC4 / Ctrl+T",
    0x15: "NAK / Ctrl+U",
    0x16: "SYN / Ctrl+V",
    0x17: "ETB / Ctrl+W",
    0x18: "CAN / Ctrl+X",
    0x19: "EM / Ctrl+Y",
    0x1A: "SUB / Ctrl+Z",
    0x1B: "ESC / Escape / Alt-prefix",
    0x1C: "FS / Ctrl+\\",
    0x1D: "GS / Ctrl+]",
    0x1E: "RS / Ctrl+^",
    0x1F: "US / Ctrl+_",
    0x7F: "DEL / Backspace",
}


CSI_U_HINTS = {
    # CSI u format: ESC [ codepoint ; modifiers u
    # modifier values are usually:
    # 2 Shift, 3 Alt, 4 Shift+Alt, 5 Ctrl, 6 Ctrl+Shift,
    # 7 Ctrl+Alt, 8 Ctrl+Shift+Alt
    67: "C",
    86: "V",
    99: "c",
    118: "v",
}


def now() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def byte_name(b: int) -> str:
    if b in CTRL_NAMES:
        return CTRL_NAMES[b]
    if 32 <= b <= 126:
        return f"printable '{chr(b)}'"
    return "non-printable"


def render_bytes(data: bytes) -> str:
    hex_part = " ".join(f"{b:02X}" for b in data)
    dec_part = " ".join(str(b) for b in data)

    escaped = (
        repr(data)
        .replace("\\x1b", "\\e")
        .replace("\\r", "\\r")
        .replace("\\n", "\\n")
        .replace("\\t", "\\t")
    )

    names = ", ".join(byte_name(b) for b in data)

    return (
        f"bytes={escaped}\n"
        f"  hex: {hex_part}\n"
        f"  dec: {dec_part}\n"
        f"  names: {names}"
    )


def try_decode_utf8(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ""

    if not text:
        return ""

    safe = text.replace("\x1b", "␛").replace("\r", "␍").replace("\n", "␊")
    return safe


def parse_csi_u(data: bytes) -> str | None:
    # Example:
    #   ESC [ 67 ; 6 u  -> Ctrl+Shift+C
    #   ESC [ 86 ; 6 u  -> Ctrl+Shift+V
    if not (data.startswith(b"\x1b[") and data.endswith(b"u")):
        return None

    payload = data[2:-1].decode("ascii", errors="ignore")
    if ";" not in payload:
        return None

    code_text, mod_text = payload.split(";", 1)

    try:
        codepoint = int(code_text)
        modifier = int(mod_text)
    except ValueError:
        return None

    key = CSI_U_HINTS.get(codepoint)
    if key is None:
        try:
            key = chr(codepoint)
        except ValueError:
            key = f"codepoint {codepoint}"

    modifier_name = {
        2: "Shift",
        3: "Alt",
        4: "Shift+Alt",
        5: "Ctrl",
        6: "Ctrl+Shift",
        7: "Ctrl+Alt",
        8: "Ctrl+Shift+Alt",
    }.get(modifier, f"modifier={modifier}")

    return f"CSI-u decoded: {modifier_name}+{key}"


def parse_bracketed_paste(data: bytes) -> str | None:
    if data.startswith(b"\x1b[200~") and data.endswith(b"\x1b[201~"):
        content = data[len(b"\x1b[200~") : -len(b"\x1b[201~")]
        preview = content[:120].decode("utf-8", errors="replace")
        if len(content) > 120:
            preview += "..."
        return f"bracketed paste payload: {len(content)} bytes, preview={preview!r}"
    return None


def analyze(data: bytes) -> str:
    lines = [render_bytes(data)]

    decoded = try_decode_utf8(data)
    if decoded:
        lines.append(f"  utf8: {decoded!r}")

    csi_u = parse_csi_u(data)
    if csi_u:
        lines.append(f"  {csi_u}")

    paste = parse_bracketed_paste(data)
    if paste:
        lines.append(f"  {paste}")

    if data == b"\x16":
        lines.append("  likely: Ctrl+V reached the app as a keypress")
    elif data.startswith(b"\x1b[200~"):
        lines.append(
            "  likely: terminal performed paste; app received pasted content, not Ctrl+V"
        )
    elif data in (b"\x1b[86;6u", b"\x1b[118;6u"):
        lines.append("  likely: Ctrl+Shift+V reached the app as CSI-u")
    elif data in (b"\x1b[67;6u", b"\x1b[99;6u"):
        lines.append("  likely: Ctrl+Shift+C reached the app as CSI-u")
    elif data == b"\x03":
        lines.append("  likely: Ctrl+C reached the app as ETX")

    return "\n".join(lines)


def read_key_windows() -> bytes:
    import msvcrt

    first = msvcrt.getwch()

    # Ctrl+Q exit
    if first == "\x11":
        return b"\x11"

    # Windows extended-key prefix.
    if first in ("\x00", "\xe0"):
        second = msvcrt.getwch()
        return (first + second).encode("utf-8", errors="replace")

    return first.encode("utf-8", errors="replace")


def windows_loop() -> None:
    import ctypes

    kernel32 = ctypes.windll.kernel32
    stdin_handle = kernel32.GetStdHandle(-10)
    stdout_handle = kernel32.GetStdHandle(-11)

    original_in_mode = ctypes.c_uint()
    original_out_mode = ctypes.c_uint()

    kernel32.GetConsoleMode(stdin_handle, ctypes.byref(original_in_mode))
    kernel32.GetConsoleMode(stdout_handle, ctypes.byref(original_out_mode))

    # Input flags.
    ENABLE_PROCESSED_INPUT = 0x0001
    ENABLE_LINE_INPUT = 0x0002
    ENABLE_ECHO_INPUT = 0x0004
    ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200

    # Output flags.
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

    new_in_mode = original_in_mode.value
    new_in_mode &= ~ENABLE_LINE_INPUT
    new_in_mode &= ~ENABLE_ECHO_INPUT
    new_in_mode &= ~ENABLE_PROCESSED_INPUT
    new_in_mode |= ENABLE_VIRTUAL_TERMINAL_INPUT

    new_out_mode = original_out_mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING

    kernel32.SetConsoleMode(stdin_handle, new_in_mode)
    kernel32.SetConsoleMode(stdout_handle, new_out_mode)

    try:
        print_header()
        while True:
            data = read_key_windows()
            print_event(data)
            if data == b"\x11":
                break
    finally:
        kernel32.SetConsoleMode(stdin_handle, original_in_mode.value)
        kernel32.SetConsoleMode(stdout_handle, original_out_mode.value)


def posix_loop() -> None:
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)
        print_header()

        while True:
            first = os.read(fd, 1)

            # Collect trailing bytes from the same key sequence/paste event.
            time.sleep(0.015)
            chunks = [first]

            while True:
                ready, _, _ = select.select([fd], [], [], 0)
                if not ready:
                    break
                chunks.append(os.read(fd, 4096))
                time.sleep(0.005)

            data = b"".join(chunks)
            print_event(data)

            if data == b"\x11":
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)


def print_header() -> None:
    print("\nKey probe started.")
    print("Press shortcuts. Exit with Ctrl+Q.")
    print("Recommended checks:")
    print("  Ctrl+C, Ctrl+X, Ctrl+V")
    print("  Ctrl+Shift+C, Ctrl+Shift+V")
    print("  Shift+Insert, Ctrl+Shift+Insert")
    print("  Alt+Up/Down, Ctrl+Alt+Up/Down, Ctrl+Shift+Alt+Up/Down")
    print("-" * 72)
    sys.stdout.flush()


def print_event(data: bytes) -> None:
    print(f"\n[{now()}]")
    print(analyze(data))
    print("-" * 72)
    sys.stdout.flush()


def main() -> int:
    try:
        if IS_WINDOWS:
            windows_loop()
        else:
            posix_loop()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
