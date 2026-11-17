"""NEON//GRAB — yt-dlp engine wrapper."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError, sanitize_filename  # noqa: F401  (re-exported)

MP3_BITRATES = [320, 256, 192, 128]


class QuietLogger:
    """Swallow yt-dlp's console chatter so it doesn't tear up the UI."""

    def __init__(self):
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        self.errors.append(msg)


def base_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "logger": QuietLogger(),
        # yt-dlp needs a JS runtime for YouTube; use whichever is installed.
        "js_runtimes": {"deno": {}, "node": {}},
    }


# ── info / quality menus ───────────────────────────────────────────────────
def fetch_info(url: str) -> dict:
    with yt_dlp.YoutubeDL(base_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist":
        raise DownloadError("That link is a playlist. Paste a single video URL.")
    return info


def _fmt_size(f: dict, duration: float) -> float:
    size = f.get("filesize") or f.get("filesize_approx")
    if size:
        return float(size)
    if f.get("tbr") and duration:
        return f["tbr"] * 1000 / 8 * duration
    return 0.0


def _codec_name(vcodec: str) -> str:
    v = (vcodec or "").lower()
    if v.startswith(("avc", "h264")):
        return "H.264"
    if v.startswith(("vp09", "vp9")):
        return "VP9"
    if v.startswith("av01"):
        return "AV1"
    if v.startswith(("hev", "hvc", "h265")):
        return "H.265"
    return v.split(".")[0].upper() or "?"


def _is_video(f):
    return f.get("vcodec") not in (None, "none") and f.get("height")


def _is_audio_only(f):
    return f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")


@dataclass
class VideoQuality:
    height: int
    fps: int
    codec: str
    size: float  # bytes, 0 if unknown


def video_qualities(info: dict) -> list[VideoQuality]:
    """One entry per available height, mirroring how download() will pick formats."""
    formats = info.get("formats") or []
    duration = info.get("duration") or 0
    audio = [f for f in formats if _is_audio_only(f)]
    # mp4 downloads prefer AAC (m4a) audio
    aac = [f for f in audio if (f.get("acodec") or "").startswith("mp4a")] or audio
    audio_size = max((_fmt_size(f, duration) for f in aac), default=0.0)

    by_height: dict[int, list[dict]] = {}
    for f in formats:
        if _is_video(f):
            by_height.setdefault(int(f["height"]), []).append(f)

    out = []
    for h in sorted(by_height, reverse=True):
        cands = by_height[h]
        top_fps = max(int(f.get("fps") or 0) for f in cands)
        cands = [f for f in cands if int(f.get("fps") or 0) == top_fps]
        h264 = [f for f in cands if _codec_name(f.get("vcodec")) == "H.264"]
        pool = h264 or cands
        best = max(pool, key=lambda f: (f.get("tbr") or 0))
        muxed = best.get("acodec") not in (None, "none")
        size = _fmt_size(best, duration) + (0 if muxed else audio_size)
        out.append(VideoQuality(h, top_fps, _codec_name(best.get("vcodec")), size))
    return out


def mp3_size(info: dict, kbps: int) -> float:
    return (info.get("duration") or 0) * kbps * 1000 / 8


# ── download ───────────────────────────────────────────────────────────────
@dataclass
class Job:
    url: str
    outdir: Path
    mode: str  # "mp4" | "mp3"
    quality: int  # height for mp4, kbps for mp3
    split: bool = False
    keep_full: bool = True
    files: list[Path] = field(default_factory=list)


def build_opts(job: Job, progress_hook, pp_hook) -> dict:
    opts = base_opts()
    opts.update(
        {
            "paths": {"home": str(job.outdir), "temp": str(job.outdir)},
            "outtmpl": {
                "default": "%(title)s.%(ext)s",
                "chapter": "%(section_number)02d - %(section_title)s.%(ext)s",
            },
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [pp_hook],
            "writethumbnail": True,
            "windowsfilenames": True,
        }
    )
    pps: list[dict] = [{"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}]
    if job.mode == "mp4":
        h = job.quality
        opts["format"] = f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b"
        opts["format_sort"] = [f"res:{h}", "fps", "vcodec:h264", "acodec:aac"]
        opts["merge_output_format"] = "mp4"
        pps.append({"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": True})
    else:
        opts["format"] = "bestaudio/best"
        pps.append({"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": str(job.quality)})
        pps.append({"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": False})
    pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    if job.split:
        pps.append({"key": "FFmpegSplitChapters", "force_keyframes": False})
    opts["postprocessors"] = pps
    return opts


def _snapshot(d: Path) -> set[Path]:
    return {p for p in d.iterdir() if p.is_file()} if d.exists() else set()


def run(job: Job, progress_hook, pp_hook) -> Job:
    job.outdir.mkdir(parents=True, exist_ok=True)
    before = _snapshot(job.outdir)
    with yt_dlp.YoutubeDL(build_opts(job, progress_hook, pp_hook)) as ydl:
        info = ydl.extract_info(job.url, download=True)

    downloads = info.get("requested_downloads") or [info]
    full_files = [Path(d["filepath"]) for d in downloads if d.get("filepath")]
    chapter_files = [
        Path(c["filepath"])
        for d in downloads
        for c in (d.get("chapters") or [])
        if c.get("filepath")
    ]

    new_files = _snapshot(job.outdir) - before
    junk_ext = {".part", ".ytdl", ".jpg", ".webp", ".png"}
    files = {p for p in new_files if p.suffix.lower() not in junk_ext}
    files |= {p for p in full_files + chapter_files if p.exists()}

    if job.split and not job.keep_full:
        split_ok = any(p.exists() for p in chapter_files) or len(files) > 1
        if split_ok:
            for p in full_files:
                if p.exists() and p not in chapter_files:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
                    files.discard(p)

    job.files = sorted((p for p in files if p.exists()), key=lambda p: p.name.lower())
    return job
