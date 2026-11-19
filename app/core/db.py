"""SQLite storage: sessions (dialog state), bookings, closed slots."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    user_key   TEXT PRIMARY KEY,          -- "<channel>:<user id>"
    lang       TEXT,
    state      TEXT NOT NULL DEFAULT 'new',
    data       TEXT NOT NULL DEFAULT '{}',
    last_in    TEXT                       -- last inbound message (UTC ISO), for the WhatsApp 24h window
);
CREATE TABLE IF NOT EXISTS bookings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    user_key    TEXT NOT NULL,
    service_id  TEXT NOT NULL,
    master_id   TEXT NOT NULL,
    start       TEXT NOT NULL,            -- local time "YYYY-MM-DDTHH:MM"
    end         TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',   -- active | cancelled
    reminded_24 INTEGER NOT NULL DEFAULT 0,
    reminded_2  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_bookings_master ON bookings(master_id, start);
CREATE TABLE IF NOT EXISTS blocks (
    master_id TEXT NOT NULL,
    start     TEXT NOT NULL,              -- local "YYYY-MM-DDTHH:MM", one slot step long
    PRIMARY KEY (master_id, start)
);
"""


class DB:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL") if path != ":memory:" else None
        self.conn.executescript(SCHEMA)
        self.lock = threading.RLock()

    # ---- sessions -------------------------------------------------
    def get_session(self, user_key: str) -> dict:
        row = self.conn.execute("SELECT * FROM sessions WHERE user_key=?", (user_key,)).fetchone()
        if not row:
            return {"user_key": user_key, "lang": None, "state": "new", "data": {}, "last_in": None}
        d = dict(row)
        d["data"] = json.loads(d["data"])
        return d

    def save_session(self, s: dict) -> None:
        self.conn.execute(
            "INSERT INTO sessions(user_key, lang, state, data, last_in) VALUES(?,?,?,?,?) "
            "ON CONFLICT(user_key) DO UPDATE SET lang=excluded.lang, state=excluded.state, "
            "data=excluded.data, last_in=excluded.last_in",
            (s["user_key"], s["lang"], s["state"], json.dumps(s["data"]), s.get("last_in")),
        )

    # ---- bookings -------------------------------------------------
    def bookings_for_master_day(self, master_id: str, day: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM bookings WHERE master_id=? AND status='active' AND start LIKE ? ORDER BY start",
            (master_id, day + "%"),
        ).fetchall()

    def blocks_for_master_day(self, master_id: str, day: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT start FROM blocks WHERE master_id=? AND start LIKE ?", (master_id, day + "%")
        ).fetchall()
        return [r["start"] for r in rows]

    def get_booking(self, code: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM bookings WHERE code=?", (code,)).fetchone()

    def user_upcoming(self, user_key: str, now_local: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM bookings WHERE user_key=? AND status='active' AND start>? ORDER BY start",
            (user_key, now_local),
        ).fetchall()

    def active_between(self, lo: str, hi: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM bookings WHERE status='active' AND start>? AND start<=? ORDER BY start", (lo, hi)
        ).fetchall()

    def insert_booking(self, code, user_key, service_id, master_id, start, end, created_at) -> None:
        self.conn.execute(
            "INSERT INTO bookings(code,user_key,service_id,master_id,start,end,created_at) VALUES(?,?,?,?,?,?,?)",
            (code, user_key, service_id, master_id, start, end, created_at),
        )

    def move_booking(self, code: str, start: str, end: str) -> None:
        self.conn.execute(
            "UPDATE bookings SET start=?, end=?, reminded_24=0, reminded_2=0 WHERE code=?", (start, end, code)
        )

    def cancel_booking(self, code: str) -> None:
        self.conn.execute("UPDATE bookings SET status='cancelled' WHERE code=?", (code,))

    def mark_reminded(self, code: str, which: str) -> None:
        col = {"24": "reminded_24", "2": "reminded_2"}[which]
        self.conn.execute(f"UPDATE bookings SET {col}=1 WHERE code=?", (code,))

    # ---- blocks ---------------------------------------------------
    def add_block(self, master_id: str, start: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO blocks(master_id,start) VALUES(?,?)", (master_id, start))

    def remove_block(self, master_id: str, start: str) -> None:
        self.conn.execute("DELETE FROM blocks WHERE master_id=? AND start=?", (master_id, start))
