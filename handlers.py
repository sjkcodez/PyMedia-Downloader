"""Web handlers for PyMedia Downloader."""
from pathlib import Path
from flask import jsonify, send_file, request

from core import downloader, extractor, history, config, analytics
from core.utils import DOWNLOADS_DIR, human_size


def api_analyze():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL."}), 400

    try:
        info = extractor.extract(url)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    video_formats = [f for f in info["formats"] if f["type"] == "video"]
    audio_formats = [f for f in info["formats"] if f["type"] == "audio"]

    return jsonify({
        "ok": True,
        "info": {
            "title": info["title"],
            "channel": info["channel"],
            "duration_str": info["duration_str"],
            "duration": info["duration"],
            "thumbnail": info["thumbnail"],
            "webpage_url": info["webpage_url"],
            "extractor": info["extractor"],
            "is_playlist": info["is_playlist"],
            "playlist_count": info["playlist_count"],
            "video_count": len(video_formats),
            "audio_count": len(audio_formats),
            "view_count": info["view_count"],
            "upload_date": info["upload_date"],
        },
    })


def api_download():
    data = request.get_json(silent=True) or {}
    urls = data.get("urls") or []
    if isinstance(urls, str):
        urls = [urls]
    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()]
    urls = [u for u in urls if u.startswith(("http://", "https://"))]
    if not urls:
        return jsonify({"error": "No valid URLs provided."}), 400

    kind = (data.get("kind") or "video").lower()
    quality = (data.get("quality") or "1080p").strip()
    fmt = (data.get("format") or "").strip()

    if not fmt:
        fmt = {"video": "mp4", "audio": "mp3", "image": ""}.get(kind, "mp4")

    jobs = []
    for url in urls:
        job = downloader.start_job(url, kind=kind, quality=quality, fmt=fmt)
        jobs.append({"id": job["id"], "url": url, "title": url})

    return jsonify({"ok": True, "jobs": jobs, "count": len(jobs)})


def api_job(job_id):
    job = downloader.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    return jsonify(job)


def api_jobs():
    return jsonify({"jobs": downloader.list_jobs()})


def api_download_file():
    rel = request.args.get("path", "")
    if not rel:
        return "Missing path.", 400
    p = Path(rel).resolve()
    try:
        p.relative_to(DOWNLOADS_DIR.resolve())
    except ValueError:
        return "Access denied.", 403
    if not p.exists() or not p.is_file():
        return "File not found.", 404
    return send_file(p, as_attachment=True, download_name=p.name)


def api_history():
    kind = request.args.get("kind") or None
    try:
        limit = int(request.args.get("limit", "100"))
    except ValueError:
        limit = 100
    rows = history.list_recent(limit=limit, kind=kind)
    return jsonify({"history": rows})


def api_history_stats():
    return jsonify(history.stats())


def api_history_clear():
    history.clear()
    return jsonify({"ok": True})


def api_config():
    if request.method == "GET":
        return jsonify(config.load())
    data = request.get_json(silent=True) or {}
    cfg = config.load()
    cfg.update({k: v for k, v in data.items() if k in cfg})
    config.save(cfg)
    return jsonify({"ok": True, "config": cfg})
