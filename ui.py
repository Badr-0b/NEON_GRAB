"""NEON//GRAB — visual layer: palette, gradients, banner, animations, prompts."""
from __future__ import annotations

import os
import random
import sys
import time

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    DownloadColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.spinner import SPINNERS
from rich.style import Style
from rich.table import Table
from rich.text import Text

import questionary
from questionary import Style as QStyle

try:  # Windows key polling, used to let any key skip the intro
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None

console = Console(highlight=False)

# ── palette ────────────────────────────────────────────────────────────────
HOT = (255, 24, 48)     # crimson — primary
DEEP = (140, 0, 20)     # blood red — dark end of gradients
GLINT = (255, 140, 140) # pale hot red — answers, highlights
STEEL = (232, 232, 236) # white — prompts, values
DIM = (130, 36, 46)     # dried red — frames, hints
ALERT = (255, 196, 0)   # hazard amber — warnings, errors
CLEAR = (255, 255, 255) # bright white — success
GHOST = (200, 196, 198) # soft grey — body text


def hx(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def lerp(a, b, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ramp(t: float, stops=(DEEP, HOT)):
    """Colour at position t (0..1) on a multi-stop gradient."""
    t = t % 1.0 if t != 1.0 else 1.0
    seg = t * (len(stops) - 1)
    i = min(int(seg), len(stops) - 2)
    return lerp(stops[i], stops[i + 1], seg - i)


def gradient(text: str, start=GLINT, end=HOT, bold=True) -> Text:
    out = Text()
    n = max(len(text) - 1, 1)
    for i, ch in enumerate(text):
        out.append(ch, style=Style(color=hx(lerp(start, end, i / n)), bold=bold))
    return out


C_HOT, C_DEEP, C_STEEL, C_GLINT, C_DIM, C_ALERT, C_CLEAR, C_GHOST = map(
    hx, (HOT, DEEP, STEEL, GLINT, DIM, ALERT, CLEAR, GHOST)
)

# ── custom spinners ────────────────────────────────────────────────────────
SPINNERS["neon"] = {
    "interval": 90,
    "frames": ["▰▱▱▱▱", "▰▰▱▱▱", "▰▰▰▱▱", "▰▰▰▰▱", "▰▰▰▰▰", "▱▰▰▰▰", "▱▱▰▰▰", "▱▱▱▰▰", "▱▱▱▱▰", "▱▱▱▱▱"],
}
SPINNERS["glyph"] = {"interval": 70, "frames": list("⣾⣽⣻⢿⡿⣟⣯⣷")}

# ── banner ─────────────────────────────────────────────────────────────────
_LETTERS = {
    "N": ["███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║", "╚═╝  ╚═══╝"],
    "E": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
    "O": [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "/": ["    ██╗", "   ██╔╝", "  ██╔╝ ", " ██╔╝  ", "██╔╝   ", "╚═╝    "],
    "G": [" ██████╗ ", "██╔════╝ ", "██║  ███╗", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "R": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
    "A": [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    "B": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██████╔╝", "╚═════╝ "],
}


def _build_logo(word: str) -> list[str]:
    rows = [""] * 6
    for ch in word:
        for r in range(6):
            rows[r] += _LETTERS[ch][r]
    return rows


LOGO = _build_logo("NEON//GRAB")
LOGO_W = max(len(r) for r in LOGO)
NOISE = "!<>-_\\/[]{}=+*^?#░▒▓▚▞$%&@"
TAGLINE = "// youtube extraction rig · v1.0 · jack in, rip out //"
AUTHOR = "Badr Obtel"
WINDOW_TITLE = f"NEON//GRAB — by {AUTHOR}"


def signature() -> Text:
    """The maker's mark — one look, reused everywhere the author is shown."""
    return Text.assemble(
        ("◢◤ ", C_HOT),
        ("crafted by ", Style(color=C_DIM, italic=True)),
        (AUTHOR.upper(), Style(color=C_STEEL, bold=True)),
        (" ◥◣", C_HOT),
    )


def set_window_title():
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleTitleW(WINDOW_TITLE)
        except Exception:
            pass


def _logo_frame(reveal: float, phase: float) -> Text:
    """reveal: 0..1 fraction of real glyphs; phase: gradient offset for the sweep."""
    out = Text()
    for row in LOGO:
        for col, ch in enumerate(row):
            if ch == " ":
                out.append(" ")
                continue
            colour = hx(ramp((col / LOGO_W + phase) % 1.0, (DEEP, HOT, DEEP)))
            if random.random() < reveal:
                out.append(ch, style=Style(color=colour, bold=True))
            else:
                out.append(random.choice(NOISE), style=Style(color=hx(DIM)))
        out.append("\n")
    return out


def _compact_logo(phase: float = 0.0) -> Text:
    s = "▓▒░  N E O N // G R A B  ░▒▓"
    out = Text()
    for i, ch in enumerate(s):
        out.append(ch, style=Style(color=hx(ramp((i / len(s) + phase) % 1.0, (DEEP, HOT, DEEP))), bold=True))
    return out


def _key_pressed() -> bool:
    if msvcrt and msvcrt.kbhit():
        while msvcrt.kbhit():
            msvcrt.getwch()
        return True
    return False


def drain_keys():
    if msvcrt:
        while msvcrt.kbhit():
            msvcrt.getwch()


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def banner(animated: bool = True):
    """Glitch the logo in, then sweep a gradient across it."""
    wide = console.width >= LOGO_W + 4
    skip = False
    if animated:
        with Live(console=console, auto_refresh=False, transient=True) as live:
            frames = 22
            for f in range(frames):
                if _key_pressed():
                    skip = True
                    break
                r = (f + 1) / frames
                frame = _logo_frame(r ** 1.6, 0) if wide else _compact_logo(f / frames)
                live.update(Align.center(frame), refresh=True)
                time.sleep(0.035)
            if not skip:
                for f in range(16):
                    if _key_pressed():
                        skip = True
                        break
                    frame = _logo_frame(1.0, f / 16) if wide else _compact_logo(f / 16)
                    live.update(Align.center(frame), refresh=True)
                    time.sleep(0.03)
    final = _logo_frame(1.0, 0) if wide else _compact_logo()
    console.print(Align.center(final))
    console.print(Align.center(gradient(TAGLINE, DIM, HOT, bold=False)))
    console.print(Align.center(signature()))
    console.print()
    return skip


# ── text effects ───────────────────────────────────────────────────────────
def type_out(text: Text, delay: float = 0.008, fast: bool = False):
    """Typewriter effect for a rich Text line."""
    if fast or delay <= 0:
        console.print(text)
        return
    with Live(console=console, auto_refresh=False, transient=True) as live:
        n = len(text.plain)
        step = max(1, n // 40)
        for i in range(0, n + 1, step):
            cursor = Text("█", style=C_HOT)
            live.update(Text.assemble(text[:i], cursor), refresh=True)
            time.sleep(delay)
    console.print(text)


def boot_line(status: str, label: str, value: str, fast: bool = False):
    colours = {"OK": C_CLEAR, "WARN": C_ALERT, "FAIL": C_ALERT, "...": C_STEEL}
    dots = "." * max(3, 28 - len(label))
    line = Text.assemble(
        ("  [", C_DIM),
        (f"{status:^4}", Style(color=colours.get(status, C_STEEL), bold=True)),
        ("] ", C_DIM),
        (label + " ", C_GHOST),
        (dots + " ", C_DIM),
        (value, C_STEEL if status == "OK" else colours.get(status, C_STEEL)),
    )
    type_out(line, fast=fast)


def scanline(char: str = "━"):
    w = console.width
    console.print(gradient(char * w, DIM, HOT, bold=False))


def section(num: str, title: str):
    """Glitchy section header: scrambles for a few frames then locks in."""
    label = f" {num} ▸ {title} "
    console.print()
    with Live(console=console, auto_refresh=False, transient=True) as live:
        for f in range(5):
            scrambled = "".join(
                random.choice(NOISE) if ch != " " and random.random() > f / 5 else ch for ch in label
            )
            live.update(Text.assemble(("◢◤", C_HOT), (scrambled, Style(color=C_STEEL, bold=True))), refresh=True)
            time.sleep(0.03)
    head = Text.assemble(("◢◤", C_HOT), gradient(label, GLINT, HOT))
    rest = console.width - len(head.plain) - 1
    head.append(" " + "─" * max(rest, 0), style=C_DIM)
    console.print(head)


def panel(body, title: str, colour=C_HOT) -> Panel:
    return Panel(
        body,
        title=Text.assemble(("◢ ", colour), gradient(title, GLINT, HOT), (" ◣", colour)),
        title_align="left",
        border_style=colour,
        box=box.HEAVY,
        padding=(1, 2),
    )


def note(msg: str, colour=C_DIM):
    console.print(Text.assemble(("  ░ ", colour), (msg, Style(color=colour, italic=True))))


def error_panel(title: str, msg: str):
    console.print(
        Panel(
            Text(msg, style=C_GHOST),
            title=Text.assemble(("◢ ", C_ALERT), (title, Style(color=C_ALERT, bold=True)), (" ◣", C_ALERT)),
            title_align="left",
            border_style=C_ALERT,
            box=box.HEAVY,
            padding=(1, 2),
        )
    )


def terminated():
    console.print()
    console.print(Text.assemble(("  // ", C_HOT), ("CONNECTION TERMINATED", Style(color=C_HOT, bold=True)), ("  ▓▒░", C_HOT)))
    console.print(Text.assemble("  ", signature()))
    console.print()


def outro():
    console.print()
    console.print(Align.center(gradient("░▒▓  LOGGING OFF THE GRID — STAY CHROME  ▓▒░", HOT, GLINT)))
    console.print(Align.center(signature()))
    console.print()


# ── prompts ────────────────────────────────────────────────────────────────
Q_STYLE = QStyle(
    [
        ("qmark", f"fg:{C_HOT} bold"),
        ("question", f"fg:{C_STEEL} bold"),
        ("answer", f"fg:{C_GLINT} bold"),
        ("pointer", f"fg:{C_HOT} bold"),
        ("highlighted", f"fg:{C_HOT} bold"),
        ("selected", f"fg:{C_STEEL}"),
        ("instruction", f"fg:{C_DIM} italic"),
        ("text", f"fg:{C_GHOST}"),
        ("separator", f"fg:{C_DIM}"),
        ("disabled", f"fg:{C_DIM} italic"),
        ("validation-toolbar", f"fg:#000000 bg:{C_ALERT} bold"),
    ]
)
QMARK = " ▶"


def ask_text(msg, **kw):
    drain_keys()
    return questionary.text(msg, qmark=QMARK, style=Q_STYLE, **kw).unsafe_ask()


def ask_path(msg, **kw):
    drain_keys()
    return questionary.path(msg, qmark=QMARK, style=Q_STYLE, only_directories=True, **kw).unsafe_ask()


def ask_select(msg, choices, default=None):
    drain_keys()
    return questionary.select(
        msg,
        choices=choices,
        default=default,
        qmark=QMARK,
        pointer=" ▸",
        style=Q_STYLE,
        instruction="(↑/↓ + enter)",
    ).unsafe_ask()


def ask_confirm(msg, default=True):
    drain_keys()
    return questionary.confirm(msg, default=default, qmark=QMARK, style=Q_STYLE).unsafe_ask()


Choice = questionary.Choice
Separator = questionary.Separator


# ── progress ───────────────────────────────────────────────────────────────
class NeonBar(ProgressColumn):
    """Gradient-filled bar; pulses when total is unknown."""

    def __init__(self, width: int = 36, reserve: int = 0):
        super().__init__()
        self._max = width
        self._reserve = reserve  # columns used by the other progress fields

    @property
    def width(self) -> int:
        if not self._reserve:
            return self._max
        return max(8, min(self._max, console.width - self._reserve))

    def render(self, task):
        t = Text()
        if task.total is None or task.total == 0:
            if task.finished:
                for i in range(self.width):
                    t.append("█", style=hx(ramp(i / self.width)))
                return t
            pos = (time.monotonic() * 18) % (self.width + 8) - 4
            for i in range(self.width):
                d = abs(i - pos)
                if d < 4:
                    t.append("▓" if d < 2 else "▒", style=hx(ramp(i / self.width)))
                else:
                    t.append("░", style=C_DIM)
            return t
        pct = min(task.completed / task.total, 1.0)
        exact = pct * self.width
        filled = int(exact)
        for i in range(self.width):
            if i < filled:
                t.append("█", style=hx(ramp(i / self.width)))
            elif i == filled and exact - filled > 0.5:
                t.append("▌", style=hx(ramp(i / self.width)))
            else:
                t.append("░", style=C_DIM)
        return t


class PctColumn(ProgressColumn):
    def render(self, task):
        if not task.total:
            return Text("  ··%", style=C_DIM)
        return Text(f"{task.percentage:5.1f}%", style=Style(color=C_GLINT, bold=True))


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn("neon", style=C_HOT, finished_text=Text("▰▰▰▰▰", style=C_CLEAR)),
        TextColumn("{task.description}", style=C_STEEL),
        NeonBar(reserve=72),
        PctColumn(),
        DownloadColumn(binary_units=True),
        TextColumn("•", style=C_DIM),
        TransferSpeedColumn(),
        TextColumn("•", style=C_DIM),
        TimeRemainingColumn(compact=True),
        console=console,
        refresh_per_second=15,
    )


def make_pp_progress() -> Progress:
    """Spinner rows for post-processing stages (merge, convert, split...)."""
    return Progress(
        SpinnerColumn("glyph", style=C_HOT, finished_text=Text("  ✔", style=Style(color=C_CLEAR, bold=True))),
        TextColumn("{task.description}", style=C_STEEL),
        NeonBar(width=20),
        console=console,
        refresh_per_second=15,
    )


def kv_table(rows: list[tuple[str, str | Text]]) -> Table:
    t = Table.grid(padding=(0, 2))
    t.add_column(style=Style(color=C_HOT, bold=True), no_wrap=True)
    t.add_column(style=C_GHOST)
    for k, v in rows:
        t.add_row(k, v)
    return t
