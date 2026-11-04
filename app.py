"""KeyType · 键盘代打

把文字逐字“敲”进当前获得焦点的输入框，绕开只拦截粘贴的网页。
纯本地运行，不读取网络，也不修改目标页面。
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import winapi

APP_NAME = "KeyType"
APP_TITLE = "KeyType · 键盘代打"

BG = "#0E1014"
CARD = "#161A21"
CARD_2 = "#1C212A"
CARD_3 = "#232A36"
BORDER = "#2A303C"
TEXT = "#F1F4F8"
MUTED = "#8C95A5"
DIM = "#5D6675"
ACCENT = "#FFB454"
ACCENT_HOVER = "#FFC372"
ACCENT_PRESS = "#EAA03E"
ACCENT_INK = "#251708"
GREEN = "#72E3A6"
RED = "#FF7A7A"
TRACK = "#262C37"
HUD_BG = "#14181F"

FAMILY = "Microsoft YaHei UI"
SCALE = 1.0
DEBUG_LOG = False

DEMO_TEXT = (
    "这是一段本来无法粘贴到网页里的文字。\n"
    "KeyType 不碰剪贴板，而是逐字发送键盘输入。\n\n"
    "中文、English、数字 123、Emoji 😀 都可以。\n"
    "按 Esc 可以随时中止。"
)

DEFAULT_SETTINGS = {
    "text": "",
    "delay": 3,
    "speed": "normal",
    "newline": "enter",
    "minimize": True,
    "restore": True,
    "topmost": False,
}

DELAYS = [2, 3, 5, 8]
SPEEDS = {"slow": 60, "normal": 20, "fast": 8}
SPEED_LABELS = {"slow": "慢", "normal": "标准", "fast": "快"}
NEWLINES = {"enter": "回车", "shift_enter": "Shift+回车"}


def s(value: float) -> int:
    """逻辑像素 -> 当前屏幕物理像素。"""
    return max(1, int(round(value * SCALE)))


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def config_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home())
    return base / APP_NAME / "settings.json"


def portable_config_path() -> Path | None:
    """打包版在用户配置目录不可写时，回退到程序目录。"""
    if not getattr(sys, "frozen", False):
        return None
    try:
        return Path(sys.executable).resolve().parent / "keytype-settings.json"
    except OSError:
        return None


def debug_log(message: str) -> None:
    """仅在 KEYTYPE_DEBUG=1 或 --debug-log 时写诊断日志。"""
    if not DEBUG_LOG and os.environ.get("KEYTYPE_DEBUG") != "1":
        return
    candidates = [config_path().parent / "debug.log"]
    portable = portable_config_path()
    if portable is not None:
        candidates.append(portable.parent / "debug.log")
    candidates.append(Path(os.environ.get("TEMP") or ".") / "KeyType-debug.log")
    for path in candidates:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S.%f} {message}\n")
            return
        except OSError:
            continue


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    candidates = [config_path()]
    portable = portable_config_path()
    if portable is not None:
        candidates.append(portable)
    stored = None
    for path in candidates:
        try:
            with path.open("r", encoding="utf-8-sig") as fh:
                stored = json.load(fh)
            break
        except (OSError, ValueError, TypeError):
            continue
    if isinstance(stored, dict):
        if isinstance(stored.get("text"), str):
            settings["text"] = stored["text"]
        if stored.get("delay") in DELAYS:
            settings["delay"] = stored["delay"]
        if stored.get("speed") in SPEEDS:
            settings["speed"] = stored["speed"]
        if stored.get("newline") in NEWLINES:
            settings["newline"] = stored["newline"]
        for key in ("minimize", "restore", "topmost"):
            if isinstance(stored.get(key), bool):
                settings[key] = stored[key]
    return settings


def save_settings(settings: dict) -> None:
    candidates = [config_path()]
    portable = portable_config_path()
    if portable is not None:
        candidates.append(portable)
    for path in candidates:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".tmp")
            with temp.open("w", encoding="utf-8") as fh:
                json.dump(settings, fh, ensure_ascii=False, indent=2)
            os.replace(temp, path)
            return
        except OSError:
            continue


def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    return canvas.create_polygon(
        points, smooth=True, splinesteps=24, **kwargs
    )


class PrimaryButton(tk.Canvas):
    def __init__(self, master, text, command, height=52, bg=BG):
        super().__init__(
            master,
            bg=bg,
            height=s(height),
            width=1,
            bd=0,
            highlightthickness=s(1),
            highlightbackground=bg,
            highlightcolor=ACCENT,
            takefocus=True,
            cursor="hand2",
        )
        self.command = command
        self._text = text
        self._enabled = True
        self._hover = False
        self._pressed = False
        self._font = tkfont.Font(family=FAMILY, size=12, weight="bold")
        self._arrow_font = tkfont.Font(family=FAMILY, size=13, weight="bold")
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", self._on_key)
        self.bind("<space>", self._on_key)
        self.bind("<FocusIn>", lambda _e: self._draw())
        self.bind("<FocusOut>", lambda _e: self._draw())

    def _on_enter(self, _event=None):
        self._hover = True
        self._draw()

    def _on_leave(self, _event=None):
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event=None):
        if not self._enabled:
            return
        self.focus_set()
        self._pressed = True
        self._draw()

    def _on_release(self, event=None):
        if not self._enabled:
            return
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if not was_pressed:
            return
        if event is not None:
            inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
            if not inside:
                return
        self.command()

    def _on_key(self, _event=None):
        if self._enabled:
            self.command()
        return "break"

    def set_enabled(self, enabled: bool, text: str | None = None):
        self._enabled = bool(enabled)
        if text is not None:
            self._text = text
        self.configure(cursor="hand2" if enabled else "arrow")
        if not enabled:
            self._hover = False
            self._pressed = False
        self._draw()

    def _draw(self):
        width = max(self.winfo_width(), s(120))
        height = max(self.winfo_height(), s(40))
        self.delete("all")
        if not self._enabled:
            fill = "#38322A"
            ink = "#97866D"
        elif self._pressed:
            fill = ACCENT_PRESS
            ink = ACCENT_INK
        elif self._hover:
            fill = ACCENT_HOVER
            ink = ACCENT_INK
        else:
            fill = ACCENT
            ink = ACCENT_INK
        rounded_rect(
            self,
            s(1),
            s(1),
            width - s(1),
            height - s(1),
            s(14),
            fill=fill,
            outline="",
        )
        self.create_text(
            width / 2 - s(5),
            height / 2,
            text=self._text,
            font=self._font,
            fill=ink,
            anchor="center",
        )
        self.create_text(
            width - s(24),
            height / 2,
            text="→",
            font=self._arrow_font,
            fill=ink,
            anchor="center",
        )


class LinkButton(tk.Label):
    def __init__(self, master, text, command, bg=CARD):
        super().__init__(
            master,
            text=text,
            font=(FAMILY, 8),
            fg=MUTED,
            bg=bg,
            cursor="hand2",
            bd=0,
            padx=0,
            pady=0,
        )
        self.command = command
        self.bind("<Enter>", lambda _e: self.configure(fg=ACCENT))
        self.bind("<Leave>", lambda _e: self.configure(fg=MUTED))
        self.bind("<Button-1>", lambda _e: self.command())


class Segmented(tk.Canvas):
    def __init__(
        self,
        master,
        labels: list[str],
        values: list,
        value,
        command=None,
        bg=CARD,
    ):
        super().__init__(
            master,
            bg=bg,
            height=s(28),
            width=1,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.labels = labels
        self.values = values
        self.value = value
        self.command = command
        self._hover_index = -1
        self._font = tkfont.Font(family=FAMILY, size=8)
        self._font_bold = tkfont.Font(family=FAMILY, size=8, weight="bold")
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Button-1>", self._on_click)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)

    def _segments(self):
        width = max(self.winfo_width(), s(80))
        count = len(self.labels)
        gap = s(3)
        seg = (width - gap * (count - 1)) / count
        return width, gap, seg

    def _index_at(self, x: int) -> int:
        _, gap, seg = self._segments()
        if seg <= 0:
            return -1
        index = int(x // (seg + gap))
        if index < 0:
            return -1
        if index >= len(self.labels):
            index = len(self.labels) - 1
        return index

    def _on_click(self, event):
        index = self._index_at(event.x)
        if 0 <= index < len(self.values):
            self.set(self.values[index], emit=True)

    def _on_motion(self, event):
        index = self._index_at(event.x)
        if index != self._hover_index:
            self._hover_index = index
            self._draw()

    def _on_leave(self, _event=None):
        self._hover_index = -1
        self._draw()

    def set(self, value, emit=False):
        if value in self.values:
            self.value = value
            self._draw()
            if emit and self.command:
                self.command(value)

    def _draw(self):
        width = max(self.winfo_width(), s(80))
        height = max(self.winfo_height(), s(20))
        _, gap, seg = self._segments()
        self.delete("all")
        for i, label in enumerate(self.labels):
            x1 = i * (seg + gap)
            x2 = x1 + seg
            selected = self.values[i] == self.value
            if selected:
                fill = ACCENT
                ink = ACCENT_INK
                font = self._font_bold
            elif i == self._hover_index:
                fill = "#2B3240"
                ink = TEXT
                font = self._font
            else:
                fill = "#202631"
                ink = MUTED
                font = self._font
            rounded_rect(
                self,
                x1,
                s(1),
                x2,
                height - s(1),
                s(8),
                fill=fill,
                outline="",
            )
            self.create_text(
                (x1 + x2) / 2,
                height / 2,
                text=label,
                font=font,
                fill=ink,
            )


class Toggle(tk.Canvas):
    def __init__(self, master, variable: tk.BooleanVar, command=None, bg=CARD):
        super().__init__(
            master,
            width=s(34),
            height=s(20),
            bg=bg,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.variable = variable
        self.command = command
        self.bind("<Button-1>", self.toggle)
        self.bind("<Configure>", lambda _e: self.redraw())
        self.redraw()

    def toggle(self, _event=None):
        self.variable.set(not self.variable.get())
        self.redraw()
        if self.command:
            self.command(self.variable.get())
        return "break"

    def redraw(self):
        width = max(self.winfo_width(), s(30))
        height = max(self.winfo_height(), s(16))
        self.delete("all")
        on = bool(self.variable.get())
        rounded_rect(
            self,
            s(1),
            s(1),
            width - s(1),
            height - s(1),
            height / 2,
            fill=ACCENT if on else "#303746",
            outline="",
        )
        radius = height / 2 - s(3)
        cx = width - height / 2 if on else height / 2
        self.create_oval(
            cx - radius,
            height / 2 - radius,
            cx + radius,
            height / 2 + radius,
            fill="#FFF9EF" if on else "#A3ABBA",
            outline="",
        )


class Hud:
    """不抢焦点的输入进度浮层。"""

    WIDTH = 292
    HEIGHT = 96

    def __init__(self, root: tk.Tk):
        self.root = root
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        try:
            self.window.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(
            self.window,
            width=s(self.WIDTH),
            height=s(self.HEIGHT),
            bg=HUD_BG,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack()
        self.window.update_idletasks()
        self.hwnd = winapi.top_level_hwnd(self.window)
        winapi.style_hud_window(self.hwnd)
        self._visible = False
        self._font_big = tkfont.Font(family=FAMILY, size=22, weight="bold")
        self._font_title = tkfont.Font(family=FAMILY, size=9, weight="bold")
        self._font_detail = tkfont.Font(family=FAMILY, size=8)
        self._draw("3", "秒后开始", "请切到目标输入框", 0.0, ACCENT)

    def _position(self):
        left, top, width, height = winapi.screen_work_area()
        w, h = s(self.WIDTH), s(self.HEIGHT)
        x = left + (width - w) // 2
        y = top + s(22)
        return x, y, w, h

    def show(self):
        debug_log(
            f"hud.show visible={self._visible} fg={winapi.foreground_pid()} hwnd={self.hwnd}"
        )
        if self._visible:
            return
        x, y, w, h = self._position()
        self.window.geometry(f"{w}x{h}+{x}+{y}")
        self.window.deiconify()
        self.window.update_idletasks()
        winapi.show_hud_window(self.hwnd, x, y)
        self._visible = True
        debug_log(f"hud.shown fg={winapi.foreground_pid()}")

    def hide(self):
        if self._visible:
            self.window.withdraw()
            self._visible = False

    def destroy(self):
        try:
            self.window.destroy()
        except tk.TclError:
            pass

    def countdown(self, remaining: int):
        self._draw(
            str(remaining),
            "秒后开始",
            "切到目标窗口 · Esc",
            0.0,
            ACCENT,
        )
        self.show()

    def typing(self, index: int, total: int):
        ratio = index / total if total else 0
        self._draw(
            f"{int(ratio * 100)}%",
            "正在键入",
            f"{index} / {total} · Esc 停止",
            ratio,
            ACCENT,
        )
        self.show()

    def done(self, total: int):
        self._draw("✓", "输入完成", f"共 {total} 字", 1.0, GREEN)
        self.show()

    def aborted(self, detail: str = "按 Esc 停止"):
        self._draw("—", "已中止", detail, 0.0, MUTED)
        self.show()

    def problem(self, title: str, detail: str):
        self._draw("!", title, detail, 0.0, RED)
        self.show()

    def _draw(self, big, title, detail, ratio, color):
        width, height = s(self.WIDTH), s(self.HEIGHT)
        self.canvas.delete("all")
        rounded_rect(
            self.canvas,
            s(1),
            s(1),
            width - s(1),
            height - s(1),
            s(15),
            fill=HUD_BG,
            outline=BORDER,
            width=s(1),
        )
        rounded_rect(
            self.canvas,
            s(1),
            s(18),
            s(5),
            height - s(18),
            s(2),
            fill=color,
            outline="",
        )
        divider_x = s(136)
        self.canvas.create_line(
            divider_x,
            s(20),
            divider_x,
            height - s(22),
            fill=BORDER,
        )
        self.canvas.create_text(
            s(20),
            height / 2 - s(5),
            text=big,
            font=self._font_big,
            fill=color,
            anchor="w",
        )
        self.canvas.create_text(
            s(148),
            height / 2 - s(14),
            text=title,
            font=self._font_title,
            fill=TEXT,
            anchor="w",
        )
        self.canvas.create_text(
            s(148),
            height / 2 + s(7),
            text=detail,
            font=self._font_detail,
            fill=MUTED,
            anchor="w",
        )
        track_x1, track_y1 = s(18), height - s(13)
        track_x2 = width - s(18)
        rounded_rect(
            self.canvas,
            track_x1,
            track_y1,
            track_x2,
            track_y1 + s(3),
            s(2),
            fill=TRACK,
            outline="",
        )
        if ratio > 0:
            fill_x2 = track_x1 + (track_x2 - track_x1) * min(1.0, ratio)
            if fill_x2 - track_x1 >= s(3):
                rounded_rect(
                    self.canvas,
                    track_x1,
                    track_y1,
                    fill_x2,
                    track_y1 + s(3),
                    s(2),
                    fill=color,
                    outline="",
                )
        self.window.update_idletasks()


class KeyTypeApp:
    def __init__(self, root: tk.Tk, demo=False, no_save=False):
        global SCALE, FAMILY
        self.root = root
        self.demo = demo
        self.no_save = no_save or demo
        self.dpi = max(96, int(root.winfo_fpixels("1i")))
        SCALE = self.dpi / 96.0
        families = set(tkfont.families(root))
        FAMILY = (
            "Microsoft YaHei UI"
            if "Microsoft YaHei UI" in families
            else ("Microsoft YaHei" if "Microsoft YaHei" in families else "Segoe UI")
        )
        MONO_FAMILY = "Cascadia Mono" if "Cascadia Mono" in families else "Consolas"

        self.settings = load_settings()
        if demo:
            self.settings["text"] = DEMO_TEXT
            self.settings["topmost"] = True
            self.settings["minimize"] = True
            self.settings["restore"] = True
        self.state = "idle"
        self.events: queue.Queue = queue.Queue()
        self._run_token = 0
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._hud_hide_job = None
        self._save_job = None
        self._restore_job = None
        self._toggles: list[Toggle] = []
        self._hotkey: winapi.HotkeyListener | None = None
        self._hotkey_ok = True

        self._setup_window()
        self._build_ui()
        self.hud = Hud(self.root)
        self._apply_initial_settings()
        self._start_hotkey()
        self.root.after(40, self._poll_events)
        self.root.after(200, self._apply_titlebar)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Control-Return>", self._on_ctrl_enter)
        self.root.bind("<Escape>", self._on_escape_key)

        if self.state == "idle":
            self._set_status("就绪 · 把文字放进来，切到目标窗口即可", "idle")
        debug_log(f"app.ready pid={os.getpid()} hwnd={winapi.top_level_hwnd(self.root)}")

    # ------------------------------------------------------------------
    # 窗口与布局
    # ------------------------------------------------------------------
    def _setup_window(self):
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.option_add("*tearOff", False)
        width, height = s(480), s(600)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(s(10), (screen_w - width) // 2)
        y = max(s(10), (screen_h - height) // 2 - s(24))
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(width, height)
        icon_path = resource_path("assets/keytype.ico")
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass
        ttk.Style(self.root).theme_use("clam")
        style = ttk.Style(self.root)
        style.configure(
            "KeyType.Vertical.TScrollbar",
            gripcount=0,
            background=CARD_3,
            darkcolor=CARD_3,
            lightcolor=CARD_3,
            troughcolor=CARD,
            bordercolor=CARD,
            arrowcolor=DIM,
            arrowsize=s(10),
            width=s(8),
        )
        style.map("KeyType.Vertical.TScrollbar", background=[("active", BORDER)])
        if self.settings.get("topmost"):
            self.root.attributes("-topmost", True)

    def _build_ui(self):
        self.outer = tk.Frame(self.root, bg=BG)
        self.outer.pack(fill="both", expand=True, padx=s(20), pady=(s(13), s(11)))

        self._build_header()
        self._section_title("要输入的内容", "Ctrl+V 粘贴")
        self._build_text_card()
        self._section_title("发送设置", "不经过剪贴板")
        self._build_options()
        self._build_start()
        self._build_status()

    def _build_header(self):
        header = tk.Frame(self.outer, bg=BG)
        header.pack(fill="x", pady=(0, s(12)))

        logo = tk.Canvas(
            header,
            width=s(42),
            height=s(42),
            bg=BG,
            highlightthickness=0,
            bd=0,
        )
        logo.pack(side="left")
        rounded_rect(
            logo,
            s(1),
            s(1),
            s(41),
            s(41),
            s(11),
            fill=ACCENT,
            outline="",
        )
        logo.create_text(
            s(21),
            s(21) + s(1),
            text="K",
            font=(FAMILY, 17, "bold"),
            fill=ACCENT_INK,
        )

        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left", padx=(s(11), 0))
        tk.Label(
            titles,
            text="KeyType",
            bg=BG,
            fg=TEXT,
            font=(FAMILY, 16, "bold"),
            bd=0,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            titles,
            text="键盘代打 · 不是粘贴，是逐字输入",
            bg=BG,
            fg=MUTED,
            font=(FAMILY, 8),
            bd=0,
            anchor="w",
        ).pack(anchor="w", pady=(s(1), 0))

        badge = tk.Canvas(
            header,
            width=s(78),
            height=s(23),
            bg=BG,
            highlightthickness=0,
            bd=0,
        )
        badge.pack(side="right", pady=(s(3), 0))
        rounded_rect(
            badge,
            s(1),
            s(1),
            s(77),
            s(22),
            s(11),
            fill="#14241C",
            outline="#294233",
        )
        badge.create_oval(
            s(11),
            s(8),
            s(16),
            s(13),
            fill=GREEN,
            outline="",
        )
        badge.create_text(
            s(22),
            s(11),
            text="本地运行",
            font=(FAMILY, 7),
            fill=GREEN,
            anchor="w",
        )

    def _section_title(self, text, hint=None):
        row = tk.Frame(self.outer, bg=BG)
        row.pack(fill="x", pady=(0, s(5)))
        tk.Label(
            row,
            text=text,
            bg=BG,
            fg=TEXT,
            font=(FAMILY, 9, "bold"),
            bd=0,
            anchor="w",
        ).pack(side="left")
        if hint:
            tk.Label(
                row,
                text=hint,
                bg=BG,
                fg=DIM,
                font=(FAMILY, 8),
                bd=0,
            ).pack(side="right")

    def _build_text_card(self):
        card = tk.Frame(
            self.outer,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.text_card = card
        card.pack(fill="x", pady=(0, s(11)))

        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=s(12), pady=(s(8), s(3)))

        text_wrap = tk.Frame(inner, bg=CARD)
        text_wrap.pack(fill="both", expand=True)
        self.text = tk.Text(
            text_wrap,
            height=6,
            width=1,
            bg=CARD,
            fg=TEXT,
            insertbackground=ACCENT,
            insertwidth=s(2),
            selectbackground="#3A455A",
            selectforeground=TEXT,
            font=(FAMILY, 10),
            bd=0,
            relief="flat",
            highlightthickness=0,
            padx=0,
            pady=0,
            wrap="word",
            undo=True,
            spacing1=s(1),
            spacing3=s(1),
        )
        self.scroll = ttk.Scrollbar(
            text_wrap,
            orient="vertical",
            command=self.text.yview,
            style="KeyType.Vertical.TScrollbar",
        )
        self.text.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y", padx=(s(5), 0))
        self.text.pack(side="left", fill="both", expand=True)

        self.placeholder = tk.Label(
            text_wrap,
            text="把被禁止粘贴的文字放到这里…\n支持中文、Emoji 和多行文本",
            bg=CARD,
            fg=DIM,
            font=(FAMILY, 10),
            justify="left",
            anchor="nw",
            cursor="xterm",
        )
        self.placeholder.place(x=s(1), y=s(2))
        self.placeholder.bind("<Button-1>", lambda _e: self.text.focus_set())
        self.placeholder.bind(
            "<Button-1>", lambda _e: self.text.focus_set(), add="+"
        )

        footer = tk.Frame(card, bg=CARD)
        footer.pack(fill="x", padx=s(13), pady=(s(2), s(8)))
        LinkButton(footer, "读取剪贴板", self._read_clipboard).pack(side="left")
        tk.Label(
            footer,
            text="·",
            bg=CARD,
            fg=BORDER,
            font=(FAMILY, 8),
            bd=0,
        ).pack(side="left", padx=s(6))
        LinkButton(footer, "清空", self._clear_text).pack(side="left")
        self.count_label = tk.Label(
            footer,
            text="0 字",
            bg=CARD,
            fg=DIM,
            font=(FAMILY, 8),
            bd=0,
        )
        self.count_label.pack(side="right")

        self.text.bind("<<Modified>>", self._on_text_modified)
        self.text.bind("<Button-3>", self._show_context_menu)
        self.text.bind("<Control-a>", self._select_all)
        self.text.bind("<FocusIn>", self._on_text_focus_in)
        self.text.bind("<FocusOut>", self._on_text_focus_out)
        self._build_context_menu()

    def _build_context_menu(self):
        self.context_menu = tk.Menu(
            self.root,
            tearoff=False,
            bg=CARD_2,
            fg=TEXT,
            activebackground=ACCENT,
            activeforeground=ACCENT_INK,
            bd=0,
            relief="flat",
            font=(FAMILY, 9),
        )
        self.context_menu.add_command(
            label="剪切", command=lambda: self.text.event_generate("<<Cut>>")
        )
        self.context_menu.add_command(
            label="复制", command=lambda: self.text.event_generate("<<Copy>>")
        )
        self.context_menu.add_command(
            label="粘贴", command=lambda: self.text.event_generate("<<Paste>>")
        )
        self.context_menu.add_separator()
        self.context_menu.add_command(
            label="全选", command=lambda: self.text.tag_add("sel", "1.0", "end-1c")
        )

    def _build_options(self):
        card = tk.Frame(
            self.outer,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, s(11)))

        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=s(13), pady=(s(8), s(7)))

        delay_row = self._option_row(inner, "切换等待")
        self.delay_seg = Segmented(
            delay_row,
            [f"{value} 秒" for value in DELAYS],
            DELAYS,
            self.settings["delay"],
            self._on_delay_change,
            bg=CARD,
        )
        self.delay_seg.pack(side="left", fill="x", expand=True)

        speed_row = self._option_row(inner, "输入速度")
        self.speed_seg = Segmented(
            speed_row,
            [SPEED_LABELS["slow"], SPEED_LABELS["normal"], SPEED_LABELS["fast"]],
            ["slow", "normal", "fast"],
            self.settings["speed"],
            self._on_speed_change,
            bg=CARD,
        )
        self.speed_seg.pack(side="left", fill="x", expand=True)

        newline_row = self._option_row(inner, "换行按键")
        self.newline_seg = Segmented(
            newline_row,
            [NEWLINES["enter"], NEWLINES["shift_enter"]],
            ["enter", "shift_enter"],
            self.settings["newline"],
            self._on_newline_change,
            bg=CARD,
        )
        self.newline_seg.pack(side="left", fill="x", expand=True)

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=(s(1), s(8)))

        toggle_row = tk.Frame(inner, bg=CARD)
        toggle_row.pack(fill="x")
        self.minimize_var = tk.BooleanVar(value=bool(self.settings["minimize"]))
        self.restore_var = tk.BooleanVar(value=bool(self.settings["restore"]))
        self.topmost_var = tk.BooleanVar(value=bool(self.settings["topmost"]))
        self._toggle_item(
            toggle_row, "开始时最小化", self.minimize_var, self._on_minimize_toggle
        )
        self._toggle_item(
            toggle_row, "完成后返回", self.restore_var, self._on_restore_toggle
        )
        self._toggle_item(
            toggle_row, "窗口置顶", self.topmost_var, self._on_topmost_toggle
        )

        tk.Label(
            inner,
            text="若浏览器/编辑器以管理员运行，请右键以管理员身份启动 KeyType",
            bg=CARD,
            fg=DIM,
            font=(FAMILY, 7),
            bd=0,
            anchor="w",
        ).pack(fill="x", pady=(s(7), 0))

    def _option_row(self, parent, label):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=(0, s(6)))
        tk.Label(
            row,
            text=label,
            bg=CARD,
            fg=MUTED,
            font=(FAMILY, 8),
            width=7,
            anchor="w",
            bd=0,
        ).pack(side="left", padx=(0, s(4)))
        return row

    def _toggle_item(self, parent, label, variable, command):
        frame = tk.Frame(parent, bg=CARD)
        frame.pack(side="left", fill="x", expand=True)
        text = tk.Label(
            frame,
            text=label,
            bg=CARD,
            fg=MUTED,
            font=(FAMILY, 8),
            bd=0,
            cursor="hand2",
        )
        text.pack(side="left")
        switch = Toggle(frame, variable, command=command, bg=CARD)
        switch.pack(side="left", padx=(s(6), 0))
        text.bind("<Button-1>", lambda _e, sw=switch: sw.toggle())
        self._toggles.append(switch)

    def _build_start(self):
        self.start_button = PrimaryButton(
            self.outer,
            "开始键入",
            self._on_start_clicked,
            height=51,
            bg=BG,
        )
        self.start_button.pack(fill="x", pady=(s(3), 0))
        self.hint_label = tk.Label(
            self.outer,
            text="点击后 3 秒内切到目标输入框 · Esc 中止",
            bg=BG,
            fg=DIM,
            font=(FAMILY, 8),
            bd=0,
            anchor="center",
        )
        self.hint_label.pack(fill="x", pady=(s(7), 0))

    def _build_status(self):
        footer = tk.Frame(self.outer, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(s(10), 0))
        row = tk.Frame(footer, bg=BG)
        row.pack(fill="x")
        self.status_dot = tk.Canvas(
            row,
            width=s(7),
            height=s(7),
            bg=BG,
            highlightthickness=0,
            bd=0,
        )
        self.status_dot.pack(side="left", pady=(s(2), 0))
        self.status_dot.create_oval(
            s(1), s(1), s(6), s(6), fill=DIM, outline=""
        )
        self.status_label = tk.Label(
            row,
            text="",
            bg=BG,
            fg=MUTED,
            font=(FAMILY, 8),
            bd=0,
            anchor="w",
        )
        self.status_label.pack(side="left", padx=(s(6), 0), fill="x", expand=True)
        self.progress_count = tk.Label(
            row,
            text="",
            bg=BG,
            fg=DIM,
            font=(FAMILY, 8),
            bd=0,
        )
        self.progress_count.pack(side="right")
        self.progress = tk.Canvas(
            footer,
            height=s(4),
            bg=BG,
            highlightthickness=0,
            bd=0,
        )
        self.progress.pack(fill="x", pady=(s(6), 0))
        self.progress.bind("<Configure>", lambda _e: self._draw_progress())
        self._progress_ratio = 0.0

    def _apply_initial_settings(self):
        self._set_text(self.settings.get("text", ""))
        self._update_delay_hint()
        self._update_text_meta()
        self.topmost_var.set(bool(self.settings["topmost"]))
        self.root.attributes("-topmost", bool(self.settings["topmost"]))
        self._draw_progress()
        self.start_button._draw()
        self.delay_seg._draw()
        self.speed_seg._draw()
        self.newline_seg._draw()
        for switch in self._toggles:
            switch.redraw()

    def _apply_titlebar(self):
        try:
            hwnd = winapi.top_level_hwnd(self.root)
            winapi.apply_dark_titlebar(hwnd)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 文本与设置
    # ------------------------------------------------------------------
    def _set_text(self, text: str):
        self.text.delete("1.0", "end")
        if text:
            self.text.insert("1.0", text)
        self.text.edit_modified(False)
        self.text.edit_reset()
        self._update_text_meta()

    def _get_text(self) -> str:
        return self.text.get("1.0", "end-1c")

    def _on_text_modified(self, _event=None):
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self._update_text_meta()
        self._schedule_save()

    def _update_text_meta(self):
        content = self._get_text()
        count = len(content)
        self.count_label.configure(text=f"{count} 字")
        if content.strip():
            self.placeholder.place_forget()
        else:
            self.placeholder.place(x=s(1), y=s(2))
        self.text.configure(yscrollcommand=self.scroll.set)

    def _on_text_focus_in(self, _event=None):
        self.text_card.configure(highlightbackground=ACCENT)

    def _on_text_focus_out(self, _event=None):
        self.text_card.configure(highlightbackground=BORDER)

    def _select_all(self, _event=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "1.0")
        return "break"

    def _show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _read_clipboard(self):
        try:
            data = self.root.clipboard_get()
        except tk.TclError:
            self._set_status("剪贴板里没有文字", "error")
            return
        self._set_text(data)
        self._set_status(f"已读取剪贴板 · {len(data)} 字", "idle")
        self.text.focus_set()
        self._schedule_save()

    def _clear_text(self):
        self._set_text("")
        self._set_status("已清空", "idle")
        self.text.focus_set()
        self._schedule_save()

    def _on_delay_change(self, value):
        self.settings["delay"] = int(value)
        self._update_delay_hint()
        self._schedule_save()

    def _on_speed_change(self, value):
        self.settings["speed"] = value
        self._schedule_save()

    def _on_newline_change(self, value):
        self.settings["newline"] = value
        self._schedule_save()

    def _on_minimize_toggle(self, value):
        self.settings["minimize"] = bool(value)
        self._schedule_save()

    def _on_restore_toggle(self, value):
        self.settings["restore"] = bool(value)
        self._schedule_save()

    def _on_topmost_toggle(self, value):
        self.settings["topmost"] = bool(value)
        try:
            self.root.attributes("-topmost", bool(value))
        except tk.TclError:
            pass
        self._schedule_save()

    def _update_delay_hint(self):
        delay = int(self.settings["delay"])
        hotkey = "Ctrl+Alt+K" if self._hotkey_ok else "按钮开始"
        self.hint_label.configure(
            text=f"点击后 {delay} 秒内点目标输入框；或点输入框后按 {hotkey}"
        )

    def _schedule_save(self):
        if self.no_save:
            return
        if self._save_job is not None:
            try:
                self.root.after_cancel(self._save_job)
            except tk.TclError:
                pass
        self._save_job = self.root.after(1200, self._save_now)

    def _save_now(self):
        self._save_job = None
        if self.no_save:
            return
        self.settings["text"] = self._get_text()
        save_settings(self.settings)

    def _collect_settings(self):
        self.settings["text"] = self._get_text()
        self.settings["delay"] = int(self.delay_seg.value)
        self.settings["speed"] = self.speed_seg.value
        self.settings["newline"] = self.newline_seg.value
        self.settings["minimize"] = bool(self.minimize_var.get())
        self.settings["restore"] = bool(self.restore_var.get())
        self.settings["topmost"] = bool(self.topmost_var.get())

    # ------------------------------------------------------------------
    # 状态 / 进度
    # ------------------------------------------------------------------
    def _set_status(self, text, tone="idle"):
        colors = {
            "idle": DIM,
            "countdown": ACCENT,
            "typing": ACCENT,
            "done": GREEN,
            "error": RED,
        }
        fg = {
            "idle": MUTED,
            "countdown": TEXT,
            "typing": TEXT,
            "done": GREEN,
            "error": RED,
        }
        color = colors.get(tone, DIM)
        self.status_dot.itemconfigure(1, fill=color)
        self.status_label.configure(text=text, fg=fg.get(tone, MUTED))

    def _set_progress(self, ratio: float, text: str | None = None):
        self._progress_ratio = max(0.0, min(1.0, ratio))
        if text is not None:
            self.progress_count.configure(text=text)
        self._draw_progress()

    def _draw_progress(self):
        width = max(self.progress.winfo_width(), s(40))
        height = max(self.progress.winfo_height(), s(3))
        self.progress.delete("all")
        rounded_rect(
            self.progress,
            0,
            (height - s(3)) / 2,
            width,
            (height + s(3)) / 2,
            s(2),
            fill=TRACK,
            outline="",
        )
        if self._progress_ratio > 0:
            fill_width = width * self._progress_ratio
            if fill_width >= s(3):
                rounded_rect(
                    self.progress,
                    0,
                    (height - s(3)) / 2,
                    fill_width,
                    (height + s(3)) / 2,
                    s(2),
                    fill=ACCENT,
                    outline="",
                )

    # ------------------------------------------------------------------
    # 热键
    # ------------------------------------------------------------------
    def _start_hotkey(self):
        if self.demo:
            return
        self._hotkey = winapi.HotkeyListener(
            lambda: self.events.put(("hotkey",)),
            lambda code: self.events.put(("hotkey_error", code)),
        )
        self._hotkey.start()
        self.root.after(350, self._check_hotkey)

    def _check_hotkey(self):
        if self._hotkey is None:
            return
        if self._hotkey.error:
            self._on_hotkey_error(self._hotkey.error)
        else:
            debug_log("hotkey.ready")

    def _on_hotkey_error(self, code):
        self._hotkey_ok = False
        self._set_status(
            f"全局热键不可用（{code}），请用按钮开始", "error"
        )
        try:
            self._update_delay_hint()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 开始 / 中止
    # ------------------------------------------------------------------
    def _on_start_clicked(self):
        self._begin("button")

    def _on_ctrl_enter(self, _event=None):
        self._begin("button")
        return "break"

    def _on_escape_key(self, _event=None):
        if self.state in ("countdown", "typing"):
            self._stop_event.set()
            self._set_status("正在停止…", "error")
        return "break"

    def _begin(self, source="button"):
        if self.state != "idle":
            debug_log(f"begin.ignored source={source} state={self.state}")
            return
        raw = self._get_text()
        text = (
            raw.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\x00", "")
            .replace("\t", "    ")
        )
        debug_log(
            f"begin source={source} len={len(text)} fg={winapi.foreground_info()} "
            f"own_pid={os.getpid()} state={self.root.state()}"
        )
        if not text.strip():
            self._set_status("请先放一点文字进来", "error")
            if source == "hotkey":
                self._hud_problem("没有可输入的文字", "先在 KeyType 里放入内容")
                self._hide_hud_later(1200)
                self._return_to_app(force=True)
            return

        self._collect_settings()
        if not self.no_save:
            save_settings(self.settings)
        self._cancel_restore()
        delay = int(self.settings["delay"])
        interval = SPEEDS.get(self.settings["speed"], 20) / 1000.0
        shift_enter = self.settings["newline"] == "shift_enter"
        minimize = bool(self.settings["minimize"])

        self.state = "countdown"
        self._run_token += 1
        token = self._run_token
        self._stop_event = threading.Event()
        self._cancel_hud_hide()
        self.start_button.set_enabled(False, "准备中…")
        self._set_progress(0.0, "")
        self._set_status(
            f"{delay} 秒后开始 · 请切到目标输入框", "countdown"
        )
        self._hud_countdown(delay)

        if minimize:
            try:
                self.root.iconify()
                self.root.update_idletasks()
                debug_log(f"begin.iconified state={self.root.state()} fg={winapi.foreground_info()}")
            except tk.TclError:
                pass
        elif self.settings.get("topmost"):
            self.root.attributes("-topmost", True)

        self._worker = threading.Thread(
            target=self._typing_worker,
            args=(text, delay, interval, shift_enter, token),
            name="KeyTypeWorker",
            daemon=True,
        )
        self._worker.start()

    def _hud_countdown(self, remaining):
        self.hud.countdown(remaining)

    def _hud_problem(self, title, detail):
        self.hud.problem(title, detail)

    def _typing_worker(self, text, delay, interval, shift_enter, token):
        total = len(text)

        def cancelled() -> bool:
            return (
                self._stop_event.is_set()
                or token != self._run_token
                or winapi.is_escape_down()
            )

        def pause(seconds: float) -> bool:
            end = time.perf_counter() + max(0.0, seconds)
            while time.perf_counter() < end:
                if cancelled():
                    return False
                time.sleep(min(0.02, max(0.0, end - time.perf_counter())))
            return True

        try:
            for remaining in range(delay, 0, -1):
                if cancelled():
                    self.events.put(("aborted", "已中止", 0, total))
                    return
                self.events.put(("countdown", remaining))
                if not pause(1.0):
                    self.events.put(("aborted", "已中止 · Esc", 0, total))
                    return

            if winapi.foreground_pid() == os.getpid():
                debug_log("typing.focus_own_window")
                self.events.put(("focus_error", total))
                return

            fg_hwnd, fg_pid, fg_title = winapi.foreground_info()
            if not fg_pid:
                self.events.put(("focus_error", total))
                return
            target_level = winapi.process_integrity_level(fg_pid)
            own_level = winapi.process_integrity_level(os.getpid())
            debug_log(
                f"typing.start total={total} fg={winapi.foreground_info()} "
                f"target_level={target_level} own_level={own_level}"
            )
            if own_level is not None and target_level is None:
                # 打不开目标进程通常意味着目标完整性级别更高（UIPI）。
                # 这时 SendInput 会“成功返回”但事件被丢弃，必须提前拦住。
                self.events.put(
                    ("privilege_error", fg_title, "更高或无法读取", total)
                )
                return
            if (
                target_level is not None
                and own_level is not None
                and target_level > own_level
            ):
                self.events.put(
                    (
                        "privilege_error",
                        fg_title,
                        winapi.integrity_name(target_level),
                        total,
                    )
                )
                return

            self.events.put(("typing_started", total))
            last_emit = 0.0
            for index, char in enumerate(text, 1):
                if cancelled():
                    self.events.put(("aborted", "已中止 · Esc", index - 1, total))
                    return
                if index % 8 == 0 and winapi.foreground_pid() == os.getpid():
                    debug_log(f"typing.abort_own_focus index={index}")
                    self.events.put(
                        ("aborted", "焦点回到工具窗口，已停止", index - 1, total)
                    )
                    return
                if char == "\n":
                    winapi.send_newline(shift=shift_enter)
                    if not pause(max(interval, 0.055)):
                        self.events.put(("aborted", "已中止 · Esc", index, total))
                        return
                else:
                    winapi.send_unicode_char(char)
                    if not pause(interval):
                        self.events.put(("aborted", "已中止 · Esc", index, total))
                        return
                now = time.perf_counter()
                if index == 1 or index == total or now - last_emit >= 0.045:
                    last_emit = now
                    self.events.put(("typing", index, total))
            # 让目标窗口有机会处理输入队列里的最后几个键，再宣布完成。
            # 否则这里立刻把 KeyType 拉回前台，可能吞掉末尾字符。
            if not pause(0.45):
                self.events.put(("aborted", "已中止 · Esc", total, total))
                return
            self.events.put(("done", total))
            debug_log(f"typing.done total={total} fg={winapi.foreground_info()}")
        except winapi.SendInputError as exc:
            debug_log(f"typing.sendinput_error {exc}")
            self.events.put(("error", str(exc)))
        except Exception as exc:  # pragma: no cover - 防御性兜底
            debug_log(f"typing.exception {exc}")
            self.events.put(("error", f"输入过程中发生错误：{exc}"))
            traceback.print_exc()

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------
    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                try:
                    self._handle_event(event)
                except Exception:
                    traceback.print_exc()
        except queue.Empty:
            pass
        try:
            self.root.after(40, self._poll_events)
        except tk.TclError:
            pass

    def _handle_event(self, event):
        kind = event[0]
        if kind == "hotkey":
            debug_log(f"hotkey.event state={self.state} fg={winapi.foreground_pid()}")
            if self.state == "idle":
                self._begin("hotkey")
        elif kind == "hotkey_error":
            self._on_hotkey_error(event[1])
        elif kind == "countdown":
            remaining = event[1]
            self._set_status(
                f"{remaining} 秒后开始 · 请切到目标输入框", "countdown"
            )
            self.hud.countdown(remaining)
        elif kind == "typing_started":
            self.state = "typing"
            total = event[1]
            self._set_status(f"正在键入 · 0 / {total}", "typing")
            self._set_progress(0.0, f"0 / {total}")
            self.hud.typing(0, total)
        elif kind == "typing":
            index, total = event[1], event[2]
            self._set_status(f"正在键入 · {index} / {total}", "typing")
            self._set_progress(index / total if total else 0, f"{index} / {total}")
            self.hud.typing(index, total)
        elif kind == "done":
            total = event[1]
            self._finish(
                f"完成 · 共 {total} 字",
                "done",
                total,
                "done",
            )
        elif kind == "aborted":
            _, reason, index, total = event
            self._finish(
                f"{reason} · {index} / {total}",
                "error",
                index,
                "aborted",
            )
        elif kind == "focus_error":
            total = event[1]
            self._finish(
                "焦点还在 KeyType，请切到目标输入框后重试",
                "error",
                0,
                "problem",
                title="还没有切到目标窗口",
                detail="点击目标输入框后再试一次",
            )
        elif kind == "privilege_error":
            _, target_title, target_level, total = event
            debug_log(
                f"privilege_error target={target_title!r} level={target_level}"
            )
            self._finish(
                "目标窗口权限更高，请以管理员身份运行 KeyType",
                "error",
                0,
                "problem",
                title="目标权限更高",
                detail="请以管理员身份启动",            )
        elif kind == "error":
            self._finish(
                f"发送失败 · {event[1][:36]}",
                "error",
                0,
                "problem",
                title="输入被系统拦截",
                detail="目标可能以管理员运行",
                show_error=True,
            )

    def _finish(
        self,
        message,
        tone,
        count,
        hud_kind,
        title=None,
        detail=None,
        show_error=False,
    ):
        if self.state == "idle":
            return
        was_typing = self.state in ("typing", "countdown")
        debug_log(
            f"finish message={message!r} count={count} fg={winapi.foreground_info()} state={self.root.state()}"
        )
        self.state = "idle"
        self._stop_event.set()
        self.start_button.set_enabled(True, "开始键入")
        self._set_status(message, tone)
        if hud_kind == "done":
            self.hud.done(count)
        elif hud_kind == "aborted":
            self.hud.aborted(detail or "按 Esc 停止")
        elif hud_kind == "problem":
            self.hud.problem(title or "输入未完成", detail or "请重试")
        if hud_kind == "done":
            self._set_progress(1.0, f"{count} / {count}")
        else:
            self._set_progress(self._progress_ratio)
        if hud_kind == "done":
            self._restore_job = self.root.after(250, self._restore_after_done)
        else:
            self._return_to_app(force=(tone == "error"))
        if hud_kind == "done":
            self._hide_hud_later(900 if self.settings.get("restore", True) else 1600)
        else:
            self._hide_hud_later(1800)
        if show_error and was_typing:
            self.root.after(
                220,
                lambda: messagebox.showerror(
                    "KeyType",
                    "发送键盘输入失败。\n\n"
                    "如果目标浏览器以管理员权限运行，请右键用管理员权限启动 KeyType。\n\n"
                    + message,
                ),
            )

    def _return_to_app(self, force=False):
        if not force and not self.settings.get("restore", True):
            try:
                winapi.flash_window(winapi.top_level_hwnd(self.root))
            except Exception:
                pass
            return
        try:
            if self.root.state() == "iconic":
                self.root.deiconify()
            self.root.lift()
            if self.settings.get("topmost"):
                self.root.attributes("-topmost", True)
        except tk.TclError:
            pass

    def _cancel_hud_hide(self):
        if self._hud_hide_job is not None:
            try:
                self.root.after_cancel(self._hud_hide_job)
            except tk.TclError:
                pass
            self._hud_hide_job = None

    def _cancel_restore(self):
        if self._restore_job is not None:
            try:
                self.root.after_cancel(self._restore_job)
            except tk.TclError:
                pass
            self._restore_job = None

    def _restore_after_done(self):
        self._restore_job = None
        self._return_to_app(force=False)

    def _hide_hud_later(self, delay):
        self._cancel_hud_hide()
        self._hud_hide_job = self.root.after(delay, self._hide_hud)

    def _hide_hud(self):
        self._hud_hide_job = None
        self.hud.hide()

    def _on_close(self):
        self._stop_event.set()
        self._run_token += 1
        self._cancel_hud_hide()
        self._cancel_restore()
        self._save_now()
        if self._hotkey is not None:
            self._hotkey.stop()
        self.hud.destroy()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="KeyType 键盘代打")
    parser.add_argument("--demo", action="store_true", help="载入演示文字且不保存设置")
    parser.add_argument("--no-save", action="store_true", help="不写入本地设置")
    parser.add_argument("--debug-log", action="store_true", help="写入输入诊断日志")
    args = parser.parse_args()
    global DEBUG_LOG
    DEBUG_LOG = args.debug_log

    winapi.enable_dpi_awareness()
    if not args.demo and not winapi.acquire_single_instance():
        winapi.native_message(
            "KeyType 已经在运行。\n\n请从任务栏或 Alt+Tab 切换到已有窗口。",
            "KeyType",
        )
        return

    root = tk.Tk(className="KeyType")

    def report_callback_exception(exc, value, tb):
        traceback.print_exception(exc, value, tb)
        try:
            messagebox.showerror("KeyType", f"发生错误：\n{value}")
        except Exception:
            pass

    root.report_callback_exception = report_callback_exception
    app = KeyTypeApp(root, demo=args.demo, no_save=args.no_save)
    app.run()


if __name__ == "__main__":
    main()
