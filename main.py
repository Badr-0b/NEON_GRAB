"""NEON//GRAB — cyberpunk terminal YouTube downloader.

Flow: URL -> scan -> directory -> mp4/mp3 -> quality -> chapters -> download.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import ui
from ui import C_STEEL, C_GHOST, C_CLEAR, C_HOT, C_DIM, C_GLINT, Style, Text, console

HERE = Path(__file__).resolve().parent
UPDATE_STAMP = HERE / ".venv" / ".ytdlp_last_update"
UPDATE_EVERY = 3 * 24 * 3600  # YouTube breaks things often; refresh yt-dlp every few days

YT_RE = re.compile(
    r"^(https?://)?((www|m|music)\.)?(youtube\.com/(watch\?.*v=|shorts/|live/|embed/)|youtu\.be/)[\w-]{6,}",
    re.I,
)


# ── helpers ────────────────────────────────────────────────────────────────
def human_size(n: float) -> str:
    if not n:
        return "size ??"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:,.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:,.2f} TB"


def hms(sec) -> str:
    sec = int(sec or 0)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


# ── boot ───────────────────────────────────────────────────────────────────
def maybe_update_engine(fast: bool):
    """Quietly refresh yt-dlp every few days (only inside our own venv)."""
    if not in_venv():
        return
    try:
        age = time.time() - UPDATE_STAMP.stat().st_mtime
    except OSError:
        age = UPDATE_EVERY + 1
    if age < UPDATE_EVERY:
        return
    with console.status(
        Text("patching extraction firmware (yt-dlp update)…", style=C_STEEL), spinner="neon", spinner_style=C_HOT
    ):
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", "-q", "--disable-pip-version-check", "yt-dlp[default]"],
            capture_output=True,
            text=True,
        )
    if r.returncode == 0:
        UPDATE_STAMP.touch()
        ui.boot_line("OK", "firmware patch", "yt-dlp up to date", fast)
    else:
        ui.boot_line("WARN", "firmware patch", "update failed (offline?) — using current", fast)


def boot():
    ui.set_window_title()
    ui.clear()
    skipped = ui.banner(animated=True)
    fast = skipped

    maybe_update_engine(fast)
    import downloader  # imported after the update so the fresh version loads
    import yt_dlp.version

    ui.boot_line("OK", "neural uplink", "established", fast)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            first = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
            ver = first.split()[2].split("-")[0]
        except Exception:
            ver = "online"
        ui.boot_line("OK", "ffmpeg core", f"v{ver}", fast)
    else:
        ui.boot_line("FAIL", "ffmpeg core", "NOT FOUND — install: winget install Gyan.FFmpeg", fast)
    ui.boot_line("OK", "yt-dlp engine", yt_dlp.version.__version__, fast)
    if shutil.which("deno"):
        ui.boot_line("OK", "js runtime", "deno", fast)
    elif shutil.which("node"):
        ui.boot_line("OK", "js runtime", "node", fast)
    else:
        ui.boot_line("WARN", "js runtime", "none — winget install DenoLand.Deno", fast)
    ui.boot_line("OK", "ICE breaker", "armed", fast)
    console.print()
    ui.scanline()
    return downloader, bool(ffmpeg)


# ── steps ──────────────────────────────────────────────────────────────────
def step_url(dl):
    ui.section("01", "TARGET LINK")
    while True:
        url = ui.ask_text(
            "Paste a YouTube URL:",
            validate=lambda s: True if YT_RE.match(s.strip()) else "✖ that doesn't look like a YouTube video link",
        ).strip()
        try:
            with console.status(
                Text("decrypting stream manifest…", style=C_STEEL), spinner="neon", spinner_style=C_HOT
            ):
                info = dl.fetch_info(url)
            return url, info
        except dl.DownloadError as e:
            ui.error_panel("SCAN FAILED", clean_err(e))


def clean_err(e: Exception) -> str:
    msg = str(e)
    msg = re.sub(r"\x1b\[[0-9;]*m", "", msg)
    return msg.replace("ERROR: ", "").strip()


def show_info(info):
    chapters = info.get("chapters") or []
    views = info.get("view_count")
    date = info.get("upload_date") or ""
    if len(date) == 8:
        date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    rows = [
        ("TITLE", Text(info.get("title") or "?", style=Style(color=C_GLINT, bold=True))),
        ("CHANNEL", info.get("channel") or info.get("uploader") or "?"),
        ("LENGTH", hms(info.get("duration"))),
        ("VIEWS", f"{views:,}" if views else "?"),
        ("UPLOADED", date or "?"),
        ("CHAPTERS", str(len(chapters)) if chapters else "none"),
    ]
    console.print()
    console.print(ui.panel(ui.kv_table(rows), "TARGET ACQUIRED"))


def step_dir(dl, info) -> Path:
    ui.section("02", "DROP ZONE")
    default = HERE / dl.sanitize_filename(info.get("title") or "video", restricted=False)
    ui.note(f"leave blank → {default}")
    raw = ui.ask_path("Output directory:").strip().strip('"')
    path = Path(os.path.expandvars(os.path.expanduser(raw))) if raw else default
    if not path.is_absolute():
        path = (HERE / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    ui.note(f"locked → {path}", C_STEEL)
    return path


def step_format() -> str:
    ui.section("03", "PAYLOAD FORMAT")
    return ui.ask_select(
        "Extract as:",
        [
            ui.Choice("▶ MP4   // video + audio", value="mp4"),
            ui.Choice("♫ MP3   // audio only", value="mp3"),
        ],
    )


def step_quality(dl, info, mode) -> int:
    ui.section("04", "SIGNAL QUALITY")
    if mode == "mp3":
        choices = [
            ui.Choice(f"{k:>3} kbps   │  ~{human_size(dl.mp3_size(info, k)):>10}", value=k)
            for k in dl.MP3_BITRATES
        ]
        return ui.ask_select("Bitrate:", choices, default=choices[0])

    quals = dl.video_qualities(info)
    if not quals:
        ui.note("no separate video streams listed — grabbing best available")
        return 4320
    choices = []
    for q in quals:
        label = f"{q.height}p" + (str(q.fps) if q.fps > 30 else "")
        size = f"~{human_size(q.size)}" if q.size else "size ??"
        choices.append(ui.Choice(f"{label:<8}│ {q.codec:<6}│ {size:>11}", value=q.height))
    default = next((c for c in choices if c.value == 1080), choices[0])
    return ui.ask_select("Resolution:", choices, default=default)


def step_chapters(info) -> tuple[bool, bool]:
    ui.section("05", "CHAPTER SLICER")
    chapters = info.get("chapters") or []
    if not chapters:
        ui.note("no chapters embedded in this video — skipping slicer")
        return False, True

    t = ui.Table(box=ui.box.SIMPLE_HEAD, header_style=Style(color=C_HOT, bold=True), border_style=C_DIM)
    t.add_column("#", style=C_DIM, justify="right")
    t.add_column("START", style=C_STEEL)
    t.add_column("LEN", style=C_STEEL)
    t.add_column("CHAPTER", style=C_GHOST)
    show = chapters if len(chapters) <= 20 else chapters[:18]
    for i, c in enumerate(show, 1):
        t.add_row(f"{i:02d}", hms(c.get("start_time")), hms((c.get("end_time") or 0) - (c.get("start_time") or 0)), c.get("title") or "?")
    if len(show) < len(chapters):
        t.add_row("··", "", "", f"+{len(chapters) - len(show)} more")
    console.print(t)

    split = ui.ask_confirm(f"Split into {len(chapters)} files named by chapter?", default=False)
    keep = True
    if split:
        keep = ui.ask_confirm("Keep the full un-split file too?", default=False)
    return split, keep


PP_LABELS = {
    "Merger": "fusing A/V streams",
    "ExtractAudio": "transmuting → MP3",
    "Metadata": "injecting metadata",
    "EmbedThumbnail": "burning cover art",
    "SplitChapters": "slicing chapters",
    "ThumbnailsConvertor": "converting cover art",
    "FixupM3u8": "repairing stream",
    "FixupM4a": "repairing container",
    "FixupDuplicateMoov": "repairing container",
    "FixupTimestamp": "repairing timestamps",
}


def step_download(dl, job):
    ui.section("06", "EXTRACTION")
    dl_prog = ui.make_progress()
    pp_prog = ui.make_pp_progress()
    tasks: dict[str, int] = {}
    pp_tasks: dict[str, int] = {}

    def on_progress(d):
        fname = d.get("filename") or d.get("tmpfilename") or "stream"
        if fname not in tasks:
            fi = d.get("info_dict") or {}
            has_v = fi.get("vcodec") not in (None, "none")
            has_a = fi.get("acodec") not in (None, "none")
            label = "A/V STREAM  " if has_v and has_a else "VIDEO STREAM" if has_v else "AUDIO STREAM"
            tasks[fname] = dl_prog.add_task(label, total=None)
        tid = tasks[fname]
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        done = d.get("downloaded_bytes") or 0
        if d["status"] == "downloading":
            dl_prog.update(tid, total=total, completed=done)
        elif d["status"] == "finished":
            dl_prog.update(tid, total=total or done or 1, completed=total or done or 1)

    def on_pp(d):
        key = d.get("postprocessor") or "?"
        if key == "MoveFiles":
            return
        label = next((v for k, v in PP_LABELS.items() if k in key), key.lower())
        if d["status"] == "started" and key not in pp_tasks:
            pp_tasks[key] = pp_prog.add_task(label, total=None)
        elif d["status"] == "finished" and key in pp_tasks:
            pp_prog.update(pp_tasks[key], total=1, completed=1)

    with ui.Live(ui.Group(dl_prog, pp_prog), console=console, refresh_per_second=15):
        dl.run(job, on_progress, on_pp)


def step_summary(job):
    t = ui.Table.grid(padding=(0, 2))
    t.add_column(style=C_CLEAR, no_wrap=True)
    t.add_column(style=C_GHOST, overflow="fold")
    t.add_column(style=C_GLINT, justify="right", no_wrap=True)
    total = 0
    for p in job.files:
        size = p.stat().st_size
        total += size
        t.add_row("▸", p.name, human_size(size))
    if not job.files:
        t.add_row("?", "no new files detected (already downloaded?)", "")
    body = ui.Group(
        t,
        Text(""),
        Text.assemble(("  ⌂ ", C_HOT), (str(job.outdir), Style(color=C_STEEL, underline=True)), overflow="fold"),
        Text.assemble(("  Σ ", C_HOT), (f"{len(job.files)} file(s) · {human_size(total)}", C_GLINT)),
    )
    console.print()
    console.print(ui.panel(body, "PAYLOAD SECURED", colour=C_CLEAR))


def step_next(job) -> bool:
    while True:
        choice = ui.ask_select(
            "Next move:",
            [
                ui.Choice("↻ grab another", value="again"),
                ui.Choice("⌂ open output folder", value="open"),
                ui.Choice("⏻ jack out (exit)", value="exit"),
            ],
        )
        if choice == "open":
            try:
                os.startfile(job.outdir)  # type: ignore[attr-defined]
            except Exception as e:
                ui.error_panel("CAN'T OPEN", str(e))
            continue
        return choice == "again"


# ── main loop ──────────────────────────────────────────────────────────────
def main():
    dl, has_ffmpeg = boot()
    if not has_ffmpeg:
        ui.error_panel("MISSING CORE", "ffmpeg is required for merging, MP3 conversion and chapter splitting.\n"
                       "Install it with:  winget install Gyan.FFmpeg   then restart this program.")
        return
    while True:
        url, info = step_url(dl)
        show_info(info)
        outdir = step_dir(dl, info)
        mode = step_format()
        quality = step_quality(dl, info, mode)
        split, keep = step_chapters(info)
        job = dl.Job(url=url, outdir=outdir, mode=mode, quality=quality, split=split, keep_full=keep)
        try:
            step_download(dl, job)
            step_summary(job)
        except dl.DownloadError as e:
            ui.error_panel("EXTRACTION FAILED", clean_err(e))
        console.print()
        if not step_next(job):
            break
        ui.clear()
        ui.banner(animated=False)
    ui.outro()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        ui.terminated()
        sys.exit(130)
