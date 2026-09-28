"""Metadata extraction via yt-dlp (no download)."""
import yt_dlp
from .utils import human_duration, human_size


def extract(url: str, cookies_from_browser: str = "") -> dict:
    """Return a metadata dict for a URL. Raises on failure."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise RuntimeError("Could not extract metadata.")

    formats = []
    for f in info.get("formats") or []:
        formats.append({
            "format_id": f.get("format_id"),
            "ext": f.get("ext"),
            "height": f.get("height"),
            "width": f.get("width"),
            "fps": f.get("fps"),
            "abr": f.get("abr"),
            "vbr": f.get("vbr"),
            "filesize": f.get("filesize") or f.get("filesize_approx"),
            "vcodec": f.get("vcodec"),
            "acodec": f.get("acodec"),
            "protocol": f.get("protocol"),
            "note": f.get("format_note"),
            "type": (
                "video" if (f.get("vcodec") and f["vcodec"] != "none")
                else "audio" if (f.get("acodec") and f["acodec"] != "none")
                else "other"
            ),
        })

    return {
        "url": url,
        "id": info.get("id"),
        "title": info.get("title"),
        "channel": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "duration_str": human_duration(info.get("duration")),
        "thumbnail": info.get("thumbnail"),
        "description": (info.get("description") or "")[:500],
        "view_count": info.get("view_count"),
        "upload_date": info.get("upload_date"),
        "webpage_url": info.get("webpage_url"),
        "extractor": info.get("extractor"),
        "extractor_key": info.get("extractor_key"),
        "is_playlist": info.get("_type") == "playlist",
        "playlist_count": info.get("playlist_count") or 0,
        "formats": formats,
    }


def extract_playlist(url: str) -> dict:
    """Return metadata for a playlist (all entries, no download)."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,   # don't fetch each video's full info
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = []
    for e in (info.get("entries") or []):
        entries.append({
            "url": e.get("url") or e.get("webpage_url"),
            "id": e.get("id"),
            "title": e.get("title"),
            "duration": e.get("duration"),
            "thumbnail": e.get("thumbnail"),
        })

    return {
        "title": info.get("title"),
        "channel": info.get("uploader"),
        "count": len(entries),
        "entries": entries,
    }
