# db.py
import sqlite3

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS seats (
  seat_id   INTEGER PRIMARY KEY,
  seat_url  TEXT
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
"""

def init_db(path="libcal.sqlite"):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
