"""JSON-backed user settings."""
import json
from pathlib import Path
from .utils import BASE_DIR

CONFIG_FILE = BASE_DIR / "config.json"

DEFAULTS = {
    "default_video_quality": "1080p",
    "default_audio_bitrate": "192",
    "default_video_format": "mp4",
    "default_audio_format": "mp3",
    "default_image_quality": "original",
    "max_concurrent_downloads": 1,
    "theme": "light",
}


def load() -> dict:
    if not CONFIG_FILE.exists():
        save(DEFAULTS)
        return dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    merged = dict(DEFAULTS)
    merged.update(data or {})
    return merged


def save(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
