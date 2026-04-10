import sys
import os
import datetime

# Enable ANSI escape sequence processing for Windows cmd.exe
if os.name == "nt":
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        # 0x0004 is ENABLE_VIRTUAL_TERMINAL_PROCESSING
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        # Fallback hack that often forces ANSI rendering on Windows
        os.system("")


class Logger:
    def __init__(self, verbosity=1, include_timestamp=False):
        self.verbosity = verbosity
        self.include_timestamp = include_timestamp

    def _get_timestamp(self):
        if self.include_timestamp:
            return f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
        return ""

    def _print(self, prefix, color_code, message, suffix="", end="\n"):
        RESET = "\033[0m"
        COLOR = f"\033[{color_code}m"
        timestamp = self._get_timestamp()
        formatted_message = f"{timestamp}{COLOR}{prefix}{RESET} {message}{suffix}"
        print(formatted_message, end=end)
        sys.stdout.flush()

    def normal(self, message, **kwargs):
        self._print("[>]", "34", message, **kwargs)  # Blue

    def input(self, message):
        RESET = "\033[0m"
        COLOR = "\033[36m"  # Cyan
        timestamp = self._get_timestamp()
        formatted_message = f"{timestamp}{COLOR}[<]{RESET} {message}"
        return input(formatted_message)

    def error(self, message, **kwargs):
        self._print("[e]", "31", message, **kwargs)  # Red

    def success(self, message, **kwargs):
        self._print("[+]", "32", message, **kwargs)  # Green

    def warning(self, message, **kwargs):
        self._print("[w]", "33", message, **kwargs)  # Yellow

    def info(self, message, **kwargs):
        self._print("[i]", "94", message, **kwargs)  # Light Blue

    def notice(self, message, **kwargs):
        self._print("[*]", "35", message, **kwargs)  # Magenta

    def verbose(self, message, level=2, **kwargs):
        if self.verbosity >= level:
            self._print("[v]", "90", message, **kwargs)  # Gray

    def custom(self, prefix, color_code, message, **kwargs):
        self._print(prefix, color_code, message, **kwargs)


log = Logger()
