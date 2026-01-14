# db.py
import sqlite3
from pathlib import Path
from libcal_bot.paths import DB_PATH

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS seats (
  seat_id    INTEGER PRIMARY KEY,
  seat_url   TEXT,
  seat_name  TEXT,
  power_available  INTEGER   -- 0/1/NULL
);

CREATE TABLE IF NOT EXISTS timeslots (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  seat_id         INTEGER NOT NULL,
  start_iso       TEXT NOT NULL,
  end_iso         TEXT NOT NULL,
  status          TEXT NOT NULL,
  class_name      TEXT NOT NULL,
  checksum        TEXT,
  captured_at_iso TEXT NOT NULL,
  FOREIGN KEY(seat_id) REFERENCES seats(seat_id),
  UNIQUE(seat_id, start_iso, end_iso)
);

CREATE INDEX IF NOT EXISTS idx_timeslots_lookup
ON timeslots(seat_id, start_iso, end_iso);

CREATE INDEX IF NOT EXISTS idx_seats_name
ON seats(seat_name);
"""

def init_db(path: str | None = None):
    db_path = Path(DB_PATH) if path is None else Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
