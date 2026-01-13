from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional
from paths import DB_PATH
from fetch_availability.fetch_all_seats import run_bulk_fetch
from book_seats.book_seat import book_seat_now as _book

SQL_FULLY_AVAILABLE = """
WITH interval_slots AS (
  SELECT start_iso, end_iso
  FROM timeslots
  WHERE start_iso >= :x
    AND end_iso   <= :y
  GROUP BY start_iso, end_iso
),
needed AS (SELECT COUNT(*) AS n FROM interval_slots),
per_seat AS (
  SELECT seat_id, COUNT(*) AS k
  FROM timeslots
  WHERE status = 'AVAILABLE'
    AND start_iso >= :x
    AND end_iso   <= :y
  GROUP BY seat_id
)
SELECT s.seat_name, s.seat_url, s.seat_id
FROM per_seat p
JOIN needed n
JOIN seats s ON s.seat_id = p.seat_id
WHERE p.k = n.n AND n.n > 0
ORDER BY
  -- Put seats with missing names last, otherwise sort by name
  (s.seat_name IS NULL) ASC,
  s.seat_name ASC,
  s.seat_id ASC;
"""

def get_available_seats(x: str, y: str) -> List[Tuple[Optional[str], str, int]]:
    """
    Returns rows as (seat_name, seat_url, seat_id).
    seat_name may be None if not filled in the DB.
    """
    conn = sqlite3.connect(str(DB_PATH))
    try:
        return conn.execute(SQL_FULLY_AVAILABLE, {"x": x, "y": y}).fetchall()
    finally:
        conn.close()

def update_availability_for_date(start_date: str, end_date: str, progress_cb=None):
    from fetch_availability.fetch_all_seats import run_bulk_fetch
    return run_bulk_fetch(start_date, end_date, db_path=str(DB_PATH), progress_cb=progress_cb)

def book_seat_now(seat_id: int, start_label_regex: str, end_value: str, profile: dict) -> str:
    from fetch_availability.book_seat import book_seat_now as _book
    return _book(seat_id, start_label_regex, end_value, profile)
