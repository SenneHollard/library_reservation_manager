# libcal_bot/find_seats/snipe_seats.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence, List, Tuple

import requests

from libcal_bot.paths import DB_PATH
from libcal_bot.fetch_availability.fetch_all_seats import fetch_slots_with_retry
from libcal_bot.fetch_availability.fetch_one_seat import status_from_classname


# -------------------------
# Helpers
# -------------------------

def _fmt(dt: datetime) -> str:
    """Format datetime exactly like your DB timeslots format."""
    return dt.isoformat(sep=" ")


def _power_filter_sql(power_selection: Sequence[str]) -> tuple[str, list]:
    """
    Convert UI selection into SQL filter.

    Expected UI values (adapt if yours differ):
      - "Power"
      - "No power"
    If both are selected -> no filter.
    If none selected -> returns impossible filter.
    """
    sel = set(power_selection or [])

    # If empty: user selected nothing => return none
    if not sel:
        return " AND 1=0 ", []

    # If both (or unknown): no filter
    # (We treat "both" as no restriction)
    if len(sel) >= 2:
        return "", []

    # Only one selected:
    if "Power" in sel:
        return " AND s.power_available = 1 ", []
    if "No power" in sel:
        # include 0 and NULL as "no power / unknown" — you can choose to exclude NULL instead
        return " AND (s.power_available = 0 OR s.power_available IS NULL) ", []

    # fallback: no filter if values are different than expected
    return "", []


def _area_filter_sql(areas: Sequence[str]) -> tuple[str, list]:
    """
    Filter by seat_name prefixes.
    If areas like ["4.A", "4.B"] or ["4.A.", "4.B."] we match with LIKE.
    If empty -> no filter.
    """
    if not areas:
        return "", []

    likes = []
    params = []
    for a in areas:
        a = (a or "").strip()
        if not a:
            continue
        # ensure dot-format: "4.A" -> "4.A."
        if not a.endswith("."):
            a = a + "."
        likes.append("s.seat_name LIKE ?")
        params.append(a + "%")

    if not likes:
        return "", []

    return f" AND ({' OR '.join(likes)}) ", params


# -------------------------
# 1) Find snipable seats (DB)
# -------------------------

from datetime import datetime, timedelta
import sqlite3

def snipable_seats(
    start_time: datetime,
    hunting_zone: tuple[Sequence[str], Sequence[str]],  # (power_selection, areas)
    db_path: str | None = None,
) -> list[int]:
    """
    Snipable seats:
    - 일반 rule: timeslot at (start_time - 30min) is UNAVAILABLE
                 AND timeslot at (start_time - 60min) is AVAILABLE
    - exception: if start_time is 09:30, only require (start_time - 30min) UNAVAILABLE
                 (seat is always snipable in that case).
    """
    db_path = str(DB_PATH) if db_path is None else str(db_path)
    power_selection, areas = hunting_zone

    prev_start = start_time - timedelta(minutes=30)
    prev_start_iso = _fmt(prev_start)

    prevprev_start = start_time - timedelta(minutes=60)
    prevprev_start_iso = _fmt(prevprev_start)

    power_sql, power_params = _power_filter_sql(power_selection)
    area_sql, area_params = _area_filter_sql(areas)

    # Special case: start_time == 09:30 (local time)
    is_0930 = (start_time.hour == 9 and start_time.minute == 30)

    conn = sqlite3.connect(db_path)
    try:
        if is_0930:
            # Only check: previous slot is UNAVAILABLE
            sql = f"""
            SELECT DISTINCT s.seat_id
            FROM timeslots t_prev
            JOIN seats s ON s.seat_id = t_prev.seat_id
            WHERE t_prev.start_iso = ?
              AND t_prev.status = 'UNAVAILABLE'
              {power_sql}
              {area_sql}
            ORDER BY s.seat_id;
            """
            params = [prev_start_iso] + power_params + area_params
        else:
            # Check: prev is UNAVAILABLE AND prevprev is AVAILABLE
            sql = f"""
            SELECT DISTINCT s.seat_id
            FROM timeslots t_prev
            JOIN timeslots t_prevprev
              ON t_prevprev.seat_id = t_prev.seat_id
            JOIN seats s
              ON s.seat_id = t_prev.seat_id
            WHERE t_prev.start_iso = ?
              AND t_prev.status = 'UNAVAILABLE'
              AND t_prevprev.start_iso = ?
              AND t_prevprev.status = 'AVAILABLE'
              {power_sql}
              {area_sql}
            ORDER BY s.seat_id;
            """
            params = [prev_start_iso, prevprev_start_iso] + power_params + area_params

        rows = conn.execute(sql, params).fetchall()
        return [int(r[0]) for r in rows]
    finally:
        conn.close()


# -------------------------
# 2) Observe a seat (LIVE)
# -------------------------

def observe_seat(
    seat_id: int,
    start_time: datetime,
    end_time: datetime,
    start_date: str,
    end_date: str,
    session: Optional[requests.Session] = None,
) -> Optional[int]:
    """
    LIVE check via grid API (faster and more reliable than parsing seat page HTML):

    Observe the first slot of the interval and the last slot.
    If both are AVAILABLE => return seat_id else None.

    start_date/end_date: YYYY-MM-DD for the grid request
      Usually start_date = start_time.date().isoformat()
              end_date   = (start_time.date()+1).isoformat()
    """
    if end_time <= start_time:
        return None

    s = session or requests.Session()

    # fetch slots for that seat
    slots = fetch_slots_with_retry(s, seat_id, start_date, end_date)

    # first slot is [start_time, start_time+30m)
    first_start = start_time
    first_end = start_time + timedelta(minutes=30)

    # last slot is [end_time-30m, end_time)
    last_start = end_time - timedelta(minutes=30)
    last_end = end_time

    first_start_iso = _fmt(first_start)
    first_end_iso = _fmt(first_end)
    last_start_iso = _fmt(last_start)
    last_end_iso = _fmt(last_end)

    first_ok = False
    last_ok = False

    for it in slots:
        st = it.get("start")
        en = it.get("end")
        if not st or not en:
            continue

        status = status_from_classname(it.get("className", ""))

        if st == first_start_iso and en == first_end_iso:
            first_ok = (status == "AVAILABLE")

        if st == last_start_iso and en == last_end_iso:
            last_ok = (status == "AVAILABLE")

        if first_ok and last_ok:
            return seat_id

    return None
