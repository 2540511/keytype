"""Windows 原生输入能力：SendInput、全局热键、窗口样式。

KeyType 的核心不是往剪贴板里写内容，而是通过 Windows 的 SendInput
把文字作为真正的键盘输入逐字发送给当前获得焦点的窗口。网页收到的
事件类型是 `insertText`，不会触发 paste / beforeinput(insertFromPaste)
一类的粘贴拦截。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import threading
import time

if os.name != "nt":  # pragma: no cover - 这个项目只面向 Windows
    raise RuntimeError("KeyType 目前只支持 Windows。")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi")
except OSError:  # pragma: no cover
    dwmapi = None

ULONG_PTR = ctypes.c_size_t

# ---------------------------------------------------------------------------
# SendInput 结构
# ---------------------------------------------------------------------------

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

VK_SHIFT = 0x10
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wt.DWORD),
        ("wParamL", wt.WORD),
        ("wParamH", wt.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wt.DWORD),
        ("u", _INPUTUNION),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wt.HWND),
        ("message", wt.UINT),
        ("wParam", wt.WPARAM),
        ("lParam", wt.LPARAM),
        ("time", wt.DWORD),
        ("pt", wt.POINT),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wt.LONG),
        ("top", wt.LONG),
        ("right", wt.LONG),
        ("bottom", wt.LONG),
    ]


class FLASHWINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("hwnd", wt.HWND),
        ("dwFlags", wt.DWORD),
        ("uCount", wt.UINT),
        ("dwTimeout", wt.DWORD),
    ]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Sid", ctypes.c_void_p),
        ("Attributes", wt.DWORD),
    ]


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [
        ("Label", SID_AND_ATTRIBUTES),
    ]


TOKEN_QUERY = 0x0008
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_INTEGRITY_LEVEL = 25

kernel32.OpenProcess.argtypes = (wt.DWORD, wt.BOOL, wt.DWORD)
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = (wt.HANDLE,)
kernel32.CloseHandle.restype = wt.BOOL
advapi32.OpenProcessToken.argtypes = (
    wt.HANDLE,
    wt.DWORD,
    ctypes.POINTER(wt.HANDLE),
)
advapi32.OpenProcessToken.restype = wt.BOOL
advapi32.GetTokenInformation.argtypes = (
    wt.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wt.DWORD,
    ctypes.POINTER(wt.DWORD),
)
advapi32.GetTokenInformation.restype = wt.BOOL
advapi32.GetSidSubAuthorityCount.argtypes = (ctypes.c_void_p,)
advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
advapi32.GetSidSubAuthority.argtypes = (ctypes.c_void_p, wt.DWORD)
advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wt.DWORD)


user32.SendInput.argtypes = (wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wt.UINT
user32.MapVirtualKeyW.argtypes = (wt.UINT, wt.UINT)
user32.MapVirtualKeyW.restype = wt.UINT
user32.GetForegroundWindow.restype = wt.HWND
user32.GetForegroundWindow.argtypes = ()
user32.GetWindowThreadProcessId.argtypes = (wt.HWND, ctypes.POINTER(wt.DWORD))
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetParent.argtypes = (wt.HWND,)
user32.GetParent.restype = wt.HWND
user32.RegisterHotKey.argtypes = (wt.HWND, ctypes.c_int, wt.UINT, wt.UINT)
user32.RegisterHotKey.restype = wt.BOOL
user32.UnregisterHotKey.argtypes = (wt.HWND, ctypes.c_int)
user32.UnregisterHotKey.restype = wt.BOOL
user32.GetMessageW.argtypes = (ctypes.POINTER(MSG), wt.HWND, wt.UINT, wt.UINT)
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = (wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.PostThreadMessageW.restype = wt.BOOL
user32.SetWindowPos.argtypes = (
    wt.HWND,
    wt.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wt.UINT,
)
user32.SetWindowPos.restype = wt.BOOL
user32.GetWindowLongW.argtypes = (wt.HWND, ctypes.c_int)
user32.GetWindowLongW.restype = wt.LONG
user32.SetWindowLongW.argtypes = (wt.HWND, ctypes.c_int, wt.LONG)
user32.SetWindowLongW.restype = wt.LONG
user32.SystemParametersInfoW.argtypes = (
    wt.UINT,
    wt.UINT,
    ctypes.c_void_p,
    wt.UINT,
)
user32.SystemParametersInfoW.restype = wt.BOOL
kernel32.GetCurrentThreadId.restype = wt.DWORD


class SendInputError(RuntimeError):
    """SendInput 没有把事件送入系统时抛出的错误。"""


def enable_dpi_awareness() -> None:
    """让 Tk 直接按物理像素渲染，避免高分屏发虚。"""
    try:
        shcore = ctypes.WinDLL("shcore")
        shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def system_dpi() -> int:
    try:
        get_dpi = user32.GetDpiForSystem
        get_dpi.restype = wt.UINT
        return int(get_dpi())
    except Exception:
        return 96


def screen_work_area() -> tuple[int, int, int, int]:
    rect = RECT()
    if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def _send_events(events: list[tuple[int, int, int]]) -> None:
    """events 为 (wVk, wScan, flags) 列表；失败时抛出 SendInputError。"""
    if not events:
        return
    array = (INPUT * len(events))()
    for i, (vk, scan, flags) in enumerate(events):
        array[i].type = INPUT_KEYBOARD
        array[i].ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    ctypes.set_last_error(0)
    sent = user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
    if sent != len(events):
        raise SendInputError(
            f"SendInput 只发送了 {sent}/{len(events)} 个事件"
            f"（错误码 {ctypes.get_last_error()}）。"
            "如果目标窗口以管理员权限运行，请也用管理员权限启动 KeyType。"
        )


def _scan_code(vk: int) -> int:
    return int(user32.MapVirtualKeyW(vk, 0))


def send_unicode_char(char: str) -> None:
    """逐字发送一个 Unicode 字符（包含 BMP 之外的 emoji）。"""
    if not char:
        return
    raw = char.encode("utf-16-le")
    events: list[tuple[int, int, int]] = []
    for i in range(0, len(raw), 2):
        unit = int.from_bytes(raw[i : i + 2], "little")
        events.append((0, unit, KEYEVENTF_UNICODE))
        events.append((0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    _send_events(events)


def send_newline(shift: bool = False) -> None:
    scan = _scan_code(VK_RETURN)
    events: list[tuple[int, int, int]] = []
    if shift:
        events.append((VK_SHIFT, _scan_code(VK_SHIFT), 0))
    events.append((VK_RETURN, scan, 0))
    events.append((VK_RETURN, scan, KEYEVENTF_KEYUP))
    if shift:
        events.append((VK_SHIFT, _scan_code(VK_SHIFT), KEYEVENTF_KEYUP))
    _send_events(events)


def is_escape_down() -> bool:
    return bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)


def foreground_pid() -> int:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def foreground_info() -> tuple[int, int, str]:
    """返回 (hwnd, pid, 标题)，用于诊断。"""
    hwnd = int(user32.GetForegroundWindow() or 0)
    if not hwnd:
        return 0, 0, ""
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return hwnd, int(pid.value), buf.value


def process_integrity_level(pid: int) -> int | None:
    """返回进程完整性级别（0x1000 低 / 0x2000 中 / 0x3000 高）。"""
    if not pid:
        return None
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    token = wt.HANDLE()
    try:
        if not advapi32.OpenProcessToken(handle, TOKEN_QUERY, ctypes.byref(token)):
            return None
        size = wt.DWORD()
        advapi32.GetTokenInformation(
            token, TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(size)
        )
        if size.value <= 0:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
            token,
            TOKEN_INTEGRITY_LEVEL,
            buffer,
            size.value,
            ctypes.byref(size),
        ):
            return None
        label = ctypes.cast(
            buffer, ctypes.POINTER(TOKEN_MANDATORY_LABEL)
        ).contents
        count_ptr = advapi32.GetSidSubAuthorityCount(label.Label.Sid)
        if not count_ptr:
            return None
        count = int(count_ptr.contents.value)
        if count <= 0:
            return None
        level_ptr = advapi32.GetSidSubAuthority(label.Label.Sid, count - 1)
        if not level_ptr:
            return None
        return int(level_ptr.contents.value)
    finally:
        if token:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(handle)


def integrity_name(level: int | None) -> str:
    if level is None:
        return "未知"
    if level >= 0x4000:
        return "系统"
    if level >= 0x3000:
        return "管理员/高"
    if level >= 0x2000:
        return "普通/中"
    if level >= 0x1000:
        return "低"
    return "不可信"


def top_level_hwnd(tk_window) -> int:
    """Tk 的 winfo_id() 在 Windows 上是子窗口，标题栏窗口要再取 parent。"""
    try:
        hwnd = int(tk_window.winfo_id())
        parent = user32.GetParent(hwnd)
        return int(parent or hwnd)
    except Exception:
        return 0


def apply_dark_titlebar(hwnd: int) -> None:
    """Windows 11 深色标题栏 + 圆角；旧系统上静默失败。"""
    if not hwnd or dwmapi is None:
        return
    try:
        dark = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)
        )
    except Exception:
        try:
            dark = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(dark), ctypes.sizeof(dark)
            )
        except Exception:
            pass
    for attribute, value in (
        (33, 2),  # DWMWA_WINDOW_CORNER_PREFERENCE = round
        (34, 0x003A2F2A),  # border: #2A2F3A
        (35, 0x0014100E),  # caption: #0E1014
        (36, 0x00F8F4F2),  # text: #F2F4F8
    ):
        try:
            val = ctypes.c_int(value)
            dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(val), ctypes.sizeof(val)
            )
        except Exception:
            pass


def style_hud_window(hwnd: int) -> None:
    """让提示浮层不抢焦点、可点击穿透。必须在显示前设置。"""
    if not hwnd:
        return
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_NOACTIVATE = 0x08000000
    try:
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd,
            GWL_EXSTYLE,
            style | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE,
        )
    except Exception:
        pass


def show_hud_window(hwnd: int, x: int, y: int) -> None:
    """显示提示浮层，但不激活它，也不改变当前键盘焦点。"""
    if not hwnd:
        return
    HWND_TOPMOST = -1
    SWP_NOSIZE = 0x0001
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        x,
        y,
        0,
        0,
        SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
    )


def flash_window(hwnd: int) -> None:
    if not hwnd:
        return
    try:
        info = FLASHWINFO(
            ctypes.sizeof(FLASHWINFO),
            hwnd,
            0x00000003,  # FLASHW_ALL
            3,
            0,
        )
        user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 单实例与原生提示
# ---------------------------------------------------------------------------

ERROR_ALREADY_EXISTS = 183
_single_mutex = None


def acquire_single_instance(name: str = "Local\\KeyType.SingleInstance") -> bool:
    """已有实例时返回 False。句柄保存在模块全局，避免被回收。"""
    global _single_mutex
    try:
        kernel32.CreateMutexW.argtypes = (wt.LPVOID, wt.BOOL, wt.LPCWSTR)
        kernel32.CreateMutexW.restype = wt.HANDLE
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            return True
        _single_mutex = handle
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
    except Exception:
        return True


def native_message(text: str, title: str = "KeyType") -> None:
    try:
        user32.MessageBoxW.argtypes = (wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.UINT)
        user32.MessageBoxW(None, text, title, 0x00000040)  # MB_ICONINFORMATION
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 全局热键：Ctrl+Alt+K
# ---------------------------------------------------------------------------

HOTKEY_ID = 0xB10
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


class HotkeyListener(threading.Thread):
    """在独立线程里建消息循环，稳定接收全局热键。"""

    def __init__(self, on_hotkey, on_error) -> None:
        super().__init__(name="KeyTypeHotkey", daemon=True)
        self.on_hotkey = on_hotkey
        self.on_error = on_error
        self.ready = threading.Event()
        self.error: int | None = None
        self._thread_id: int | None = None
        self._stopping = False

    def run(self) -> None:
        self._thread_id = int(kernel32.GetCurrentThreadId())
        ok = user32.RegisterHotKey(
            None,
            HOTKEY_ID,
            MOD_CONTROL | MOD_ALT | MOD_NOREPEAT,
            ord("K"),
        )
        if not ok:
            self.error = ctypes.get_last_error() or -1
            self.ready.set()
            try:
                self.on_error(self.error)
            except Exception:
                pass
            return
        self.ready.set()
        if self._stopping:
            user32.UnregisterHotKey(None, HOTKEY_ID)
            return
        msg = MSG()
        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result <= 0:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    try:
                        self.on_hotkey()
                    except Exception:
                        pass
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)

    def stop(self) -> None:
        self._stopping = True
        tid = self._thread_id
        if tid:
            try:
                user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        if self.is_alive():
            self.join(timeout=0.6)


def hotkey_error_text(code: int) -> str:
    if code == 1409:
        return "Ctrl+Alt+K 已被其他程序占用"
    return f"全局热键注册失败（错误码 {code}）"
