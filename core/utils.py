"""Shared helpers for PyMedia Downloader."""
import os
import re
import sys
import shutil
import subprocess
import platform
import logging
from pathlib import Path

# ---------- Directories ----------
BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
VIDEOS_DIR = DOWNLOADS_DIR / "videos"
AUDIO_DIR = DOWNLOADS_DIR / "audio"
IMAGES_DIR = DOWNLOADS_DIR / "images"
TEMP_DIR = BASE_DIR / "temp"
LOGS_DIR = BASE_DIR / "logs"

for d in (VIDEOS_DIR, AUDIO_DIR, IMAGES_DIR, TEMP_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("PyMedia")


# ---------- Filename handling ----------
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def clean_filename(name: str, max_length: int = 180) -> str:
    """Return a filesystem-safe filename."""
    name = _INVALID.sub("", name or "file")
    name = name.strip(" .")
    if len(name) > max_length:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 8:
            name = stem[: max_length - len(ext) - 1] + "." + ext
        else:
            name = name[:max_length]
    return name or "file"


def unique_path(path: Path) -> Path:
    """Return `path`, or `path (1)`, `path (2)` if it already exists."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    parent = path.parent
    for i in range(1, 1000):
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    return path


# ---------- External binaries ----------
def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffmpeg_path():
    return shutil.which("ffmpeg")


def os_name() -> str:
    return platform.system()


# ---------- Human-readable sizes ----------
def human_size(num_bytes) -> str:
    try:
        num_bytes = float(num_bytes)
    except (TypeError, ValueError):
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def human_duration(seconds) -> str:
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "—"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ---------- Detection helpers ----------
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".gif",
    ".webp", ".bmp", ".tif", ".tiff", ".svg", ".ico",
    ".avif", ".heic", ".heif",
}

VIDEO_EXTS = {
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv",
    ".m4v", ".3gp", ".wmv", ".mpg", ".mpeg",
}

AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus"}


def url_looks_like_image(url: str) -> bool:
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in IMAGE_EXTS)
