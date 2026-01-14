# libcal_actions.py
from __future__ import annotations
from datetime import datetime, timedelta
import streamlit as st
import time
import requests
import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional
from libcal_bot.paths import DB_PATH
from libcal_bot.fetch_availability.fetch_all_seats import init_static_data, fetch_availability, fetch_slots_with_retry
from libcal_bot.fetch_availability.db import init_db
from libcal_bot.book_seats.book_seat import book_seat_now as _book
from libcal_bot.fetch_availability.fetch_one_seat import status_from_classname

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
SELECT s.seat_name, s.seat_url, s.seat_id, s.power_available
FROM per_seat p
JOIN needed n
JOIN seats s ON s.seat_id = p.seat_id
WHERE p.k = n.n AND n.n > 0
ORDER BY
  (s.seat_name IS NULL) ASC,
  s.seat_name ASC,
  s.seat_id ASC;
"""

def get_available_seats(x: str, y: str) -> List[Tuple[Optional[str], str, int, Optional[int]]]:
    """
    Returns rows as (seat_name, seat_url, seat_id).
    seat_name may be None if not filled in the DB.
    """
    conn = sqlite3.connect(str(DB_PATH))
    try:
        return conn.execute(SQL_FULLY_AVAILABLE, {"x": x, "y": y}).fetchall()
    finally:
        conn.close()

def _seats_count(db_path: str) -> int:
    conn = init_db(db_path)
    try:
        cur = conn.execute("SELECT COUNT(*) FROM seats")
        return int(cur.fetchone()[0])
    finally:
        conn.close()

def update_availability_for_date(
    start_date: str,
    end_date: str,
    db_path: str | None = None,
    progress_cb=None,
):
    if db_path is None:
        db_path = str(DB_PATH)

    if _seats_count(db_path) == 0:
        init_static_data(db_path=db_path, progress_cb=progress_cb)

    return fetch_availability(
        start_date,
        end_date,
        db_path=db_path,
        progress_cb=progress_cb,
    )

def book_seat_now(seat_id: int, start_label_regex: str, end_value: str, profile: dict) -> str:
    from libcal_bot.book_seats.book_seat import book_seat_now as _book
    return _book(seat_id, start_label_regex, end_value, profile)

def _slot_is_available(slots: list[dict], start_iso: str, end_iso: str) -> bool:
    for it in slots:
        if it.get("start") == start_iso and it.get("end") == end_iso:
            return status_from_classname(it.get("className", "")) == "AVAILABLE"
    return False

@st.cache_data(show_spinner=False)
def load_all_seats_from_db():
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            "SELECT seat_name, seat_id, seat_url FROM seats WHERE seat_name IS NOT NULL ORDER BY seat_name ASC"
        ).fetchall()
    finally:
        conn.close()

    # mapping: seat_name -> (seat_id, seat_url)
    return {name: (seat_id, seat_url) for (name, seat_id, seat_url) in rows}
