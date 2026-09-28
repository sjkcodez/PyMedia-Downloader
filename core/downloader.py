"""Download execution with live progress."""
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

from .utils import (
    VIDEOS_DIR, AUDIO_DIR, IMAGES_DIR, TEMP_DIR,
    clean_filename, unique_path, ffmpeg_available,
    human_size, url_looks_like_image,
)
from . import history


# ============================================================
# In-memory job registry
# ============================================================
JOBS = {}          # job_id -> dict
JOBS_LOCK = threading.Lock()


def _new_job(url: str, kind: str, quality: str, fmt: str, title: str = "") -> dict:
    job_id = uuid.uuid4().hex[:10]
    job = {
        "id": job_id,
        "url": url,
        "kind": kind,              # video | audio | image
        "quality": quality,
        "format": fmt,
        "title": title or url,
        "status": "queued",        # queued | downloading | processing | done | error
        "percent": 0.0,
        "speed": "",
        "eta": "",
        "downloaded": 0,
        "total": 0,
        "downloaded_str": "",
        "total_str": "",
        "message": "",
        "file_path": "",
        "file_size": 0,
        "thumbnail": "",
        "channel": "",
        "duration": 0,
        "error": "",
        "created": time.time(),
        "updated": time.time(),
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    return job


def _update(job_id: str, **kwargs):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(kwargs)
        job["updated"] = time.time()


def get_job(job_id: str) -> Optional[dict]:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def list_jobs() -> list:
    with JOBS_LOCK:
        return [dict(j) for j in sorted(
            JOBS.values(), key=lambda x: x["created"], reverse=True
        )]


# ============================================================
# Quality helpers
# ============================================================
VIDEO_QUALITY_MAP = {
    "360p":  360,
    "480p":  480,
    "720p":  720,
    "1080p": 1080,
    "2k":    1440,
    "4k":    2160,
    "best":  None,
}

AUDIO_BITRATES = {"128": "128", "192": "192", "320": "320"}

IMAGE_WIDTH_MAP = {
    "original": None,
    "720p":     1280,
    "1080p":    1920,
    "2k":       2560,
    "4k":       3840,
}


def _video_format_string(quality: str) -> str:
    h = VIDEO_QUALITY_MAP.get(quality.lower(), 1080)
    if h is None:
        return "bv*+ba/bestvideo+bestaudio/best"
    return (
        f"bv*[height<={h}]+ba/bestvideo[height<={h}]+bestaudio/"
        f"best[height<={h}]/best"
    )


def _audio_format_string() -> str:
    return "bestaudio/best"


# ============================================================
# Video / audio download (yt-dlp)
# ============================================================
def _make_progress_hook(job_id: str, phase: str = "downloading") -> Callable:
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            percent = (downloaded / total * 100.0) if total else 0.0
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            _update(
                job_id,
                status=phase,
                percent=round(percent, 1),
                speed=speed,
                eta=eta,
                downloaded=downloaded,
                total=total,
                downloaded_str=human_size(downloaded),
                total_str=human_size(total) if total else "—",
            )
        elif d["status"] == "finished":
            _update(job_id, status="processing", percent=99.9, message="Processing…")
    return hook


def _pick_output_dir(kind: str) -> Path:
    return {
        "video": VIDEOS_DIR,
        "audio": AUDIO_DIR,
        "image": IMAGES_DIR,
    }.get(kind, VIDEOS_DIR)


def start_video_or_audio_job(url: str, kind: str, quality: str, fmt: str) -> dict:
    """Create a job and start it in a background thread. Returns the job dict."""
    job = _new_job(url, kind, quality, fmt)
    t = threading.Thread(
        target=_run_ytdlp_job,
        args=(job["id"], url, kind, quality, fmt),
        daemon=True,
    )
    t.start()
    return job


def _run_ytdlp_job(job_id, url, kind, quality, fmt):
    _update(job_id, status="analyzing", message="Fetching metadata…")

    out_dir = _pick_output_dir(kind)
    outtmpl = str(out_dir / "%(title)s.%(ext)s")

    opts = {
        "outtmpl": outtmpl,
        "progress_hooks": [_make_progress_hook(job_id)],
        "noplaylist": False,     # allow playlists
        "retries": 10,
        "fragment_retries": 10,
        "continuedl": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": False,
        "windowsfilenames": True,
    }

    if kind == "audio":
        opts["format"] = _audio_format_string()
        if ffmpeg_available():
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt or "mp3",
                "preferredquality": quality or "192",
            }]
    else:
        # Video
        opts["format"] = _video_format_string(quality)
        if ffmpeg_available():
            opts["merge_output_format"] = fmt or "mp4"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # Grab the final file path
        file_path = ""
        try:
            if info.get("requested_downloads"):
                file_path = info["requested_downloads"][0].get("filepath", "")
            if not file_path:
                file_path = info.get("_filename", "") or ""
        except Exception:
            pass

        size = 0
        if file_path and Path(file_path).exists():
            size = Path(file_path).stat().st_size

        title = info.get("title") or Path(file_path).stem or "download"
        channel = info.get("uploader") or info.get("channel") or ""
        thumb = info.get("thumbnail") or ""
        duration = info.get("duration") or 0

        _update(
            job_id,
            status="done",
            percent=100.0,
            file_path=file_path,
            file_size=size,
            title=title,
            channel=channel,
            thumbnail=thumb,
            duration=duration,
            total_str=human_size(size),
            downloaded_str=human_size(size),
            message="",
        )

        history.add(
            url=url, title=title, channel=channel, kind=kind,
            fmt=fmt, quality=quality,
            file_path=file_path, file_size=size, duration=duration,
            thumbnail=thumb, status="done",
        )

    except Exception as e:
        err = str(e)[:300]
        _update(job_id, status="error", error=err, message="Download failed")
        try:
            history.add(
                url=url, title="", channel="", kind=kind, fmt=fmt,
                quality=quality, file_path="", file_size=0, duration=0,
                thumbnail="", status="error",
            )
        except Exception:
            pass


# ============================================================
# Image download
# ============================================================
def start_image_job(url: str, quality: str = "original", fmt: str = "") -> dict:
    job = _new_job(url, "image", quality, fmt)
    t = threading.Thread(
        target=_run_image_job,
        args=(job["id"], url, quality, fmt),
        daemon=True,
    )
    t.start()
    return job


def _run_image_job(job_id, url, quality, fmt):
    import requests
    from PIL import Image
    import io

    _update(job_id, status="downloading", message="Fetching image…")

    try:
        r = requests.get(
            url, stream=True, timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (PyMediaDownloader)"},
        )
        r.raise_for_status()

        total = int(r.headers.get("Content-Length", 0) or 0)
        buf = io.BytesIO()
        downloaded = 0
        for chunk in r.iter_content(8192):
            if chunk:
                buf.write(chunk)
                downloaded += len(chunk)
                pct = (downloaded / total * 100.0) if total else 0.0
                _update(
                    job_id,
                    percent=round(pct, 1),
                    downloaded_str=human_size(downloaded),
                    total_str=human_size(total) if total else "—",
                )

        _update(job_id, status="processing", percent=99.0, message="Saving…")
        buf.seek(0)

        # Determine output filename
        base = clean_filename(Path(url.split("?")[0]).name or "image")
        stem = Path(base).stem or "image"

        target_w = IMAGE_WIDTH_MAP.get(quality.lower(), None)

        # Default format: keep original if it's a Pillow-known format
        try:
            img = Image.open(buf)
            img.load()
        except Exception:
            # Not a Pillow-parseable image (SVG, etc.) — save as-is
            ext = Path(base).suffix or ".bin"
            out_path = unique_path(IMAGES_DIR / f"{stem}{ext}")
            out_path.write_bytes(buf.getvalue())
            size = out_path.stat().st_size
            _update(job_id, status="done", percent=100.0,
                    file_path=str(out_path), file_size=size,
                    title=stem, total_str=human_size(size),
                    downloaded_str=human_size(size), message="")
            history.add(url=url, title=stem, channel="", kind="image",
                        fmt=ext.lstrip("."), quality=quality,
                        file_path=str(out_path), file_size=size,
                        duration=0, thumbnail=url, status="done")
            return

        # Resize if requested
        if target_w and img.width > target_w:
            ratio = target_w / img.width
            new_h = int(img.height * ratio)
            img = img.resize((target_w, new_h), Image.LANCZOS)

        # Convert format if requested
        out_ext = (fmt or "").lower().lstrip(".")
        if not out_ext:
            out_ext = (img.format or "PNG").lower()
            if out_ext == "jpeg":
                out_ext = "jpg"

        # Handle mode
        if out_ext in ("jpg", "jpeg"):
            if img.mode in ("RGBA", "P"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.convert("RGBA").split()[-1])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

        out_path = unique_path(IMAGES_DIR / f"{stem}.{out_ext}")
        save_kwargs = {}
        if out_ext in ("jpg", "jpeg"):
            save_kwargs["quality"] = 92
            save_kwargs["optimize"] = True
        img.save(out_path, **save_kwargs)

        size = out_path.stat().st_size
        _update(job_id, status="done", percent=100.0,
                file_path=str(out_path), file_size=size,
                title=stem, total_str=human_size(size),
                downloaded_str=human_size(size), message="")
        history.add(url=url, title=stem, channel="", kind="image",
                    fmt=out_ext, quality=quality,
                    file_path=str(out_path), file_size=size,
                    duration=0, thumbnail=url, status="done")

    except Exception as e:
        err = str(e)[:300]
        _update(job_id, status="error", error=err, message="Download failed")
        history.add(url=url, title="", channel="", kind="image",
                    fmt=fmt, quality=quality, file_path="",
                    file_size=0, duration=0, thumbnail="",
                    status="error")


# ============================================================
# Dispatcher
# ============================================================
def start_job(url: str, kind: str, quality: str, fmt: str) -> dict:
    """Start the right kind of job based on kind or URL."""
    if kind == "image" or url_looks_like_image(url):
        return start_image_job(url, quality=quality, fmt=fmt)
    return start_video_or_audio_job(url, kind=kind, quality=quality, fmt=fmt)
