"""SQLite-backed download history."""
import sqlite3
import threading
import time
from pathlib import Path
from .utils import BASE_DIR

DB_PATH = BASE_DIR / "logs" / "history.db"
_LOCK = threading.Lock()


SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL    NOT NULL,
    url          TEXT,
    title        TEXT,
    channel      TEXT,
    kind         TEXT,      -- video | audio | image
    format       TEXT,
    quality      TEXT,
    file_path    TEXT,
    file_size    INTEGER,
    duration     INTEGER,
    thumbnail    TEXT,
    status       TEXT       -- done | error
);

CREATE INDEX IF NOT EXISTS idx_dl_ts ON downloads(ts);
"""


def _conn():
    c = sqlite3.connect(str(DB_PATH), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _LOCK:
        c = _conn()
        try:
            c.executescript(SCHEMA)
            c.commit()
        finally:
            c.close()


def add(url, title, channel, kind, fmt, quality,
        file_path, file_size, duration, thumbnail, status="done"):
    with _LOCK:
        c = _conn()
        try:
            c.execute(
                """INSERT INTO downloads
                   (ts, url, title, channel, kind, format, quality,
                    file_path, file_size, duration, thumbnail, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (time.time(), url, title, channel, kind, fmt, quality,
                 str(file_path or ""), int(file_size or 0),
                 int(duration or 0), thumbnail or "", status),
            )
            c.commit()
        finally:
            c.close()


def list_recent(limit=100, kind=None):
    c = _conn()
    try:
        if kind:
            rows = c.execute(
                "SELECT * FROM downloads WHERE kind = ? "
                "ORDER BY ts DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM downloads ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def stats():
    c = _conn()
    try:
        total = c.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
        by_kind = dict(c.execute(
            "SELECT kind, COUNT(*) FROM downloads GROUP BY kind"
        ).fetchall())
        total_size = c.execute(
            "SELECT COALESCE(SUM(file_size), 0) FROM downloads"
        ).fetchone()[0]
        return {
            "total": total,
            "videos": by_kind.get("video", 0),
            "audio": by_kind.get("audio", 0),
            "images": by_kind.get("image", 0),
            "total_size": total_size,
        }
    finally:
        c.close()


def clear():
    with _LOCK:
        c = _conn()
        try:
            c.execute("DELETE FROM downloads")
            c.execute("DELETE FROM sqlite_sequence WHERE name='downloads'")
            c.commit()
        finally:
            c.close()


init()
