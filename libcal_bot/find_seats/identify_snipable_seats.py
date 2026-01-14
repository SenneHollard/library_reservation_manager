# libcal_bot/find_seats/identify_snipable_seats.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List

from libcal_bot.paths import DB_PATH


@dataclass(frozen=True)
class SnipCandidate:
    seat_id: int
    seat_name: Optional[str]
    seat_url: str
    start_iso: str
    end_iso: str


def identify_snipable_seats(
    release_iso: str,
    db_path: str | None = None,
    minutes: int = 30,
) -> List[SnipCandidate]:
    """
    Find seats that are UNAVAILABLE at (release_iso - minutes) start time.
    These are candidates that might become free at release_iso if user didn't check in.

    release_iso: "YYYY-MM-DD HH:MM:SS" (match your DB format)
    """
    db_path = str(DB_PATH) if db_path is None else str(db_path)

    release_dt = datetime.fromisoformat(release_iso)
    started_dt = release_dt - timedelta(minutes=minutes)
    started_iso = started_dt.isoformat(sep=" ")  # keep consistent with your DB

    sql = """
    SELECT s.seat_id, s.seat_name, s.seat_url, t.start_iso, t.end_iso
    FROM timeslots t
    JOIN seats s ON s.seat_id = t.seat_id
    WHERE t.start_iso = ?
      AND t.status = 'UNAVAILABLE'
    ORDER BY (s.seat_name IS NULL), s.seat_name, s.seat_id;
    """

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(sql, (started_iso,)).fetchall()
        return [
            SnipCandidate(
                seat_id=r[0],
                seat_name=r[1],
                seat_url=r[2],
                start_iso=r[3],
                end_iso=r[4],
            )
            for r in rows
        ]
    finally:
        conn.close()
