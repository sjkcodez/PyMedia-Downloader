#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyMedia Downloader — Web GUI server."""
import os
import sys
import shutil
from pathlib import Path

from flask import (
    Flask, render_template, request, jsonify, send_file,
    Response, redirect, url_for,
)

from core import downloader, extractor, history, config
from core.utils import (
    DOWNLOADS_DIR, VIDEOS_DIR, AUDIO_DIR, IMAGES_DIR,
    human_size, human_duration, ffmpeg_available,
)
import handlers


BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


# ============================================================
# Jinja helpers
# ============================================================
@app.template_filter("human_size")
def _filter_human_size(v):
    return human_size(v)


@app.template_filter("human_duration")
def _filter_human_duration(v):
    return human_duration(v)


@app.context_processor
def _inject_globals():
    return {
        "ffmpeg_ok": ffmpeg_available(),
    }


# ============================================================
# Pages
# ============================================================
@app.route("/")
def index():
    return render_template("index.html", active="home")


@app.route("/history")
def history_page():
    return render_template("history.html", active="history")


@app.route("/settings")
def settings_page():
    return render_template(
        "settings.html",
        active="settings",
        cfg=config.load(),
    )


@app.route("/admin")
def admin_page():
    stats = history.stats()
    jobs = downloader.list_jobs()
    active_jobs = [j for j in jobs if j["status"] in ("queued", "analyzing",
                                                     "downloading", "processing")]
    recent = jobs[:10]
    return render_template(
        "admin.html",
        active="admin",
        stats=stats,
        active_jobs=active_jobs,
        recent=recent,
    )


# ============================================================
# File serving (download results, previews)
# ============================================================
@app.route("/download")
def download_file():
    return handlers.api_download_file()


# ============================================================
# APIs
# ============================================================
@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    return handlers.api_analyze()


@app.route("/api/download", methods=["POST"])
def api_download():
    return handlers.api_download()


@app.route("/api/job/<job_id>", methods=["GET"])
def api_job(job_id):
    return handlers.api_job(job_id)


@app.route("/api/jobs", methods=["GET"])
def api_jobs():
    return handlers.api_jobs()


@app.route("/api/history", methods=["GET"])
def api_history():
    return handlers.api_history()


@app.route("/api/history/stats", methods=["GET"])
def api_history_stats():
    return handlers.api_history_stats()


@app.route("/api/history/clear", methods=["POST"])
def api_history_clear():
    return handlers.api_history_clear()


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    return handlers.api_config()


@app.route("/health")
def health():
    return jsonify({"status": "ok", "ffmpeg": ffmpeg_available()}), 200


# ============================================================
# Error handling
# ============================================================
@app.errorhandler(413)
def _too_large(_):
    return jsonify({"error": "Request too large."}), 413


@app.errorhandler(500)
def _internal(_):
    return jsonify({"error": "Internal server error."}), 500


# ============================================================
# Entry point
# ============================================================
if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("  PyMedia Downloader — Web GUI")
    print(f"  Open:   http://127.0.0.1:{port}")
    print(f"  Admin:  http://127.0.0.1:{port}/admin")
    print(f"  ffmpeg: {'available' if ffmpeg_available() else 'MISSING (no merging / MP3)'}")
    print("=" * 60)
    serve(app, host="0.0.0.0", port=port, threads=8, channel_timeout=300)
