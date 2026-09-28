#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyMedia Downloader — Web GUI server with admin login and analytics."""
import os
import io
import time
import uuid
import secrets
import threading
import traceback
from functools import wraps
from pathlib import Path
from collections import deque, defaultdict
from datetime import timedelta

import requests
from flask import (
    Flask, render_template, request, jsonify, send_file,
    Response, redirect, url_for, flash, session, stream_with_context,
    abort,
)

from core import downloader, extractor, history, config, analytics
from core.utils import (
    DOWNLOADS_DIR, VIDEOS_DIR, AUDIO_DIR, IMAGES_DIR,
    human_size, human_duration, ffmpeg_available,
    clean_filename, unique_path,
)
import handlers


BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

# ------------------------------------------------------------------
# Session config
# ------------------------------------------------------------------
_secret = os.environ.get("PMD_SECRET_KEY", "").strip()
if not _secret:
    _secret = secrets.token_hex(32)
app.secret_key = _secret

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("PMD_FORCE_HTTPS", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)


# ------------------------------------------------------------------
# Admin credentials
# ------------------------------------------------------------------
ADMIN_USER = os.environ.get("PMD_ADMIN_USER", "admin").strip() or "admin"
ADMIN_PASS = os.environ.get("PMD_ADMIN_PASS", "").strip()
ADMIN_ENABLED = bool(ADMIN_PASS)


def _is_admin_logged_in() -> bool:
    return bool(session.get("admin_logged_in"))


def requires_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not ADMIN_ENABLED:
            flash("Admin access is disabled on this server.", "error")
            return redirect(url_for("index"))
        if not _is_admin_logged_in():
            session["next_url"] = request.full_path
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


# Login rate limiting
_login_attempts = defaultdict(deque)
_login_lock = threading.Lock()
LOGIN_MAX_ATTEMPTS = 10


def _login_rate_ok(ip: str) -> bool:
    now = time.time()
    cutoff = now - 900
    with _login_lock:
        bucket = _login_attempts[ip]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        return len(bucket) < LOGIN_MAX_ATTEMPTS


def _login_rate_record(ip: str):
    with _login_lock:
        _login_attempts[ip].append(time.time())


def _login_rate_reset(ip: str):
    with _login_lock:
        _login_attempts.pop(ip, None)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


# ------------------------------------------------------------------
# Jinja filters
# ------------------------------------------------------------------
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
        "admin_logged_in": _is_admin_logged_in(),
    }


# ------------------------------------------------------------------
# Analytics hooks
# ------------------------------------------------------------------
@app.before_request
def _analytics_before():
    skip = ("/static/", "/admin", "/health", "/api/")
    if request.path.startswith(skip):
        return

    sid = request.cookies.get("pmd_sid", "")
    is_new = not sid
    if is_new:
        sid = uuid.uuid4().hex[:16]
    g_session_id = sid
    app.config["_current_session"] = sid
    app.config["_is_new_session"] = is_new

    try:
        analytics.record_visit(
            ip=_client_ip(),
            ua=request.user_agent.string or "",
            path=request.path,
            referrer=request.referrer or "",
            session_id=sid,
        )
    except Exception:
        pass


@app.after_request
def _analytics_after(response):
    if app.config.pop("_is_new_session", False):
        response.set_cookie(
            "pmd_sid", app.config.get("_current_session", ""),
            max_age=60 * 60 * 24 * 30,
            httponly=True, samesite="Lax",
        )
    return response


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------
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


# ------------------------------------------------------------------
# ADMIN — login / logout
# ------------------------------------------------------------------
@app.route("/admin/login", methods=["GET"])
def admin_login():
    if not ADMIN_ENABLED:
        return render_template("admin_login.html", admin_disabled=True, error=None)
    if _is_admin_logged_in():
        return redirect(url_for("admin_page"))
    return render_template("admin_login.html", admin_disabled=False, error=None)


@app.route("/admin/login", methods=["POST"])
def admin_login_submit():
    if not ADMIN_ENABLED:
        return redirect(url_for("admin_login"))

    ip = _client_ip()
    if not _login_rate_ok(ip):
        return render_template(
            "admin_login.html",
            admin_disabled=False,
            error="Too many failed attempts. Please wait 15 minutes.",
        ), 429

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "")

    user_ok = secrets.compare_digest(username, ADMIN_USER)
    pass_ok = secrets.compare_digest(password, ADMIN_PASS)

    if user_ok and pass_ok:
        _login_rate_reset(ip)
        session.permanent = True
        session["admin_logged_in"] = True
        session["admin_user"] = username
        nxt = session.pop("next_url", None) or url_for("admin_page")
        return redirect(nxt)

    _login_rate_record(ip)
    return render_template(
        "admin_login.html",
        admin_disabled=False,
        error="Incorrect username or password.",
    ), 401


@app.route("/admin/logout", methods=["GET", "POST"])
def admin_logout():
    session.pop("admin_logged_in", None)
    session.pop("admin_user", None)
    flash("Signed out.", "success")
    return redirect(url_for("index"))


# ------------------------------------------------------------------
# ADMIN — dashboard (protected)
# ------------------------------------------------------------------
@app.route("/admin")
@requires_admin
def admin_page():
    try:
        days = float(request.args.get("days", "7"))
    except Exception:
        days = 7.0
    if days not in (1.0, 7.0, 30.0, 0.0):
        days = 7.0

    visit_stats = analytics.get_visit_stats(days=days)
    download_stats = history.stats()
    jobs = downloader.list_jobs()
    active_jobs = [j for j in jobs if j["status"] in
                   ("queued", "analyzing", "downloading", "processing")]
    recent = jobs[:10]

    n_days = int(min(max(days, 1), 30))
    daily_downloads = analytics.daily_downloads(days=n_days)

    return render_template(
        "admin.html",
        active="admin",
        days=days,
        stats=download_stats,
        visits=visit_stats,
        daily_downloads=daily_downloads,
        active_jobs=active_jobs,
        recent=recent,
        admin_user=session.get("admin_user", "admin"),
    )


@app.route("/admin/analytics/reset", methods=["POST"])
@requires_admin
def admin_analytics_reset():
    try:
        analytics.reset_all()
        flash("Visit analytics reset.", "success")
    except Exception as e:
        flash(f"Reset failed: {e}", "error")
    return redirect(url_for("admin_page"))


# ------------------------------------------------------------------
# File serving
# ------------------------------------------------------------------
@app.route("/download")
def download_file():
    return handlers.api_download_file()


# ============================================================
# Direct streaming proxy
#   Bypasses the server's disk — pipes bytes straight through.
#   Used for direct file URLs (MP4, MP3, images).
# ============================================================
@app.route("/api/stream")
def api_stream():
    url = (request.args.get("url") or "").strip()
    suggested = (request.args.get("name") or "").strip()

    if not url.startswith(("http://", "https://")):
        abort(400, "Invalid URL.")

    try:
        upstream = requests.get(
            url, stream=True, timeout=60,
            headers={"User-Agent": "Mozilla/5.0 (PyMediaDownloader)"},
        )
        upstream.raise_for_status()
    except requests.RequestException as e:
        abort(502, f"Upstream error: {e}")

    # Determine filename from URL or Content-Disposition
    filename = suggested
    if not filename:
        cd = upstream.headers.get("Content-Disposition", "")
        if "filename=" in cd:
            filename = cd.split("filename=")[-1].strip('"; ')
        if not filename:
            filename = Path(url.split("?")[0]).name or "download"
    filename = clean_filename(filename)

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")
    content_length = upstream.headers.get("Content-Length", "")

    # Log it
    try:
        history.add(
            url=url, title=filename, channel="", kind=_guess_kind(filename),
            fmt=Path(filename).suffix.lstrip("."), quality="original",
            file_path=f"streamed:{url}", file_size=int(content_length or 0),
            duration=0, thumbnail="", status="done",
        )
    except Exception:
        pass

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": content_type,
        "X-Content-Type-Options": "nosniff",
    }
    if content_length:
        headers["Content-Length"] = content_length

    return Response(stream_with_context(generate()), headers=headers)


def _guess_kind(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in (".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v", ".flv"):
        return "video"
    if ext in (".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".aac"):
        return "audio"
    return "image"


# ------------------------------------------------------------------
# APIs
# ------------------------------------------------------------------
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


# ------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------
@app.errorhandler(413)
def _too_large(_):
    return jsonify({"error": "Request too large."}), 413


@app.errorhandler(500)
def _internal(_):
    return jsonify({"error": "Internal server error."}), 500


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("  PyMedia Downloader — Web GUI")
    print(f"  Open:   http://127.0.0.1:{port}")
    print(f"  Admin:  http://127.0.0.1:{port}/admin")
    print(f"  ffmpeg: {'available' if ffmpeg_available() else 'MISSING'}")
    print(f"  Admin pw: {'set' if ADMIN_ENABLED else 'NOT SET (admin disabled)'}")
    print("=" * 60)
    serve(app, host="0.0.0.0", port=port, threads=8, channel_timeout=600)
