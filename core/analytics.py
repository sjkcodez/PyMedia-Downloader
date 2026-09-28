"""Anonymous analytics for PyMedia Downloader.

Tracks:
  • Page visits (path, IP, UA, device, OS, browser, referrer, session_id)
  • Aggregate queries for the admin dashboard

Download records already exist in core/history.py — this module reads
them for reporting.
"""
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from .utils import BASE_DIR

DB_PATH = BASE_DIR / "logs" / "analytics.db"
_LOCK = threading.Lock()


SCHEMA = """
CREATE TABLE IF NOT EXISTS visits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL    NOT NULL,
    ip          TEXT,
    user_agent  TEXT,
    device      TEXT,
    os          TEXT,
    browser     TEXT,
    path        TEXT,
    referrer    TEXT,
    session_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_visits_ts ON visits(ts);
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


# ============================================================
# User-Agent parsing
# ============================================================
def _detect_device(ua: str) -> str:
    u = (ua or "").lower()
    if not u:
        return "unknown"
    if "ipad" in u or ("android" in u and "mobile" not in u) or "tablet" in u:
        return "tablet"
    if "mobile" in u or any(x in u for x in (
        "iphone", "ipod", "windows phone", "blackberry", "opera mini"
    )):
        return "mobile"
    return "desktop"


def _detect_os(ua: str) -> str:
    u = (ua or "").lower()
    if "windows" in u:
        return "Windows"
    if "iphone" in u or "ipad" in u or "ios" in u:
        return "iOS"
    if "mac os x" in u or "macintosh" in u:
        return "macOS"
    if "android" in u:
        return "Android"
    if "linux" in u:
        return "Linux"
    return "unknown"


def _detect_browser(ua: str) -> str:
    u = (ua or "").lower()
    if "edg/" in u or "edgios" in u or "edga" in u:
        return "Edge"
    if "opr/" in u or "opera" in u:
        return "Opera"
    if "firefox" in u:
        return "Firefox"
    if "chrome" in u or "crios" in u:
        return "Chrome"
    if "safari" in u:
        return "Safari"
    return "unknown"


# ============================================================
# Recording
# ============================================================
def record_visit(ip: str, ua: str, path: str, referrer: str, session_id: str):
    try:
        with _LOCK:
            c = _conn()
            try:
                c.execute(
                    """INSERT INTO visits
                       (ts, ip, user_agent, device, os, browser, path, referrer, session_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        time.time(), ip or "", ua or "",
                        _detect_device(ua), _detect_os(ua), _detect_browser(ua),
                        path or "", referrer or "", session_id or "",
                    ),
                )
                c.commit()
            finally:
                c.close()
    except Exception:
        pass


# ============================================================
# Stats
# ============================================================
def _since_ts(days: float) -> float:
    if days <= 0:
        return 0.0
    return time.time() - days * 86400


def get_visit_stats(days: float = 7.0) -> dict:
    """Return visit stats + a daily series for the line chart."""
    since = _since_ts(days)
    out = {
        "total": 0,
        "unique": 0,
        "devices": [],
        "browsers": [],
        "os": [],
        "daily": [],
    }

    c = _conn()
    try:
        out["total"] = c.execute(
            "SELECT COUNT(*) FROM visits WHERE ts >= ?", (since,)
        ).fetchone()[0]

        out["unique"] = c.execute(
            "SELECT COUNT(DISTINCT session_id) FROM visits "
            "WHERE ts >= ? AND session_id != ''", (since,)
        ).fetchone()[0]

        out["devices"] = _group(c, "visits", "device", since)
        out["browsers"] = _group(c, "visits", "browser", since)
        out["os"] = _group(c, "visits", "os", since)

        n_days = int(min(max(days, 1), 30))
        out["daily"] = _daily_counts(c, "visits", n_days)
    finally:
        c.close()
    return out


def _group(c, table: str, column: str, since: float):
    rows = c.execute(
        f"SELECT {column} AS k, COUNT(*) AS n FROM {table} "
        f"WHERE ts >= ? GROUP BY {column} ORDER BY n DESC LIMIT 10",
        (since,),
    ).fetchall()
    total = sum(r["n"] for r in rows) or 1
    return [
        {"name": r["k"] or "unknown", "count": r["n"], "pct": r["n"] / total * 100.0}
        for r in rows
    ]


def _daily_counts(c, table: str, days: int):
    out = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        day_ts = day.timestamp()
        next_ts = day_ts + 86400
        n = c.execute(
            f"SELECT COUNT(*) FROM {table} WHERE ts >= ? AND ts < ?",
            (day_ts, next_ts),
        ).fetchone()[0]
        out.append({
            "date": day.strftime("%Y-%m-%d"),
            "label": day.strftime("%b %d"),
            "count": n,
        })
    return out


def daily_downloads(days: int = 7) -> list:
    """Daily download counts (from history.py's downloads table)."""
    try:
        from . import history
    except Exception:
        return []
    conn = history._conn()  # internal use, fine here
    try:
        return _daily_counts(conn, "downloads", days)
    finally:
        conn.close()


def reset_all():
    """Wipe all visit records."""
    with _LOCK:
        c = _conn()
        try:
            c.execute("DELETE FROM visits")
            c.execute("DELETE FROM sqlite_sequence WHERE name='visits'")
            c.commit()
        finally:
            c.close()


init()
