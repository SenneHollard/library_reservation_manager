# fetch_one_seat.py
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
import requests
from fetch_availability.db import init_db
from fetch_availability.discover_seats import fetch_seat_name


GRID_URL = "https://libcal.rug.nl/spaces/availability/grid"

def status_from_classname(class_name: str) -> str:
    cn = (class_name or "").lower()
    if "checkout" in cn:
        return "UNAVAILABLE"
    if "unavailable" in cn:
        return "AVAILABLE"
    # fallback: onbekend -> treat as UNAVAILABLE (conservatief)
    return "AVAILABLE"

def fetch_slots(seat_id: int, start_date: str, end_date: str,
                lid=1443, gid=3634, eid=10948, zone=0, page_index=0, page_size=200) -> list[dict]:
    """
    start_date/end_date: 'YYYY-MM-DD'
    end_date is typically next day to capture a single day.
    """
    data = {
        "lid": str(lid),
        "gid": str(gid),
        "eid": str(eid),
        "seat": "true",
        "seatId": str(seat_id),
        "zone": str(zone),
        "start": start_date,
        "end": end_date,
        "pageIndex": str(page_index),
        "pageSize": str(page_size),
    }

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; seat-availability-fetch/1.0)",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://libcal.rug.nl",
        "Referer": f"https://libcal.rug.nl/seat/{seat_id}",
    })

    r = s.post(GRID_URL, data=data, timeout=30)
    r.raise_for_status()
    payload = r.json()
    return payload.get("slots", [])

def upsert_seat(
    conn: sqlite3.Connection,
    seat_id: int,
    seat_url: str,
    seat_name: str | None = None,
):
    conn.execute(
        """
        INSERT INTO seats(seat_id, seat_url, seat_name)
        VALUES(?, ?, ?)
        ON CONFLICT(seat_id) DO UPDATE SET
          seat_url = excluded.seat_url,
          seat_name = COALESCE(excluded.seat_name, seats.seat_name)
        """,
        (seat_id, seat_url, seat_name),
    )


def insert_snapshot(conn: sqlite3.Connection, seat_id: int, slots: list[dict]):
    captured_at = datetime.now(timezone.utc).isoformat()

    for it in slots:
        start = it.get("start")
        end = it.get("end")
        class_name = it.get("className", "")
        checksum = it.get("checksum")
        status = status_from_classname(class_name)

        if not start or not end:
            continue

        conn.execute(
            """
            INSERT INTO timeslots(seat_id, start_iso, end_iso, status, class_name, checksum, captured_at_iso)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(seat_id, start_iso, end_iso)
            DO UPDATE SET
              status=excluded.status,
              class_name=excluded.class_name,
              checksum=excluded.checksum,
              captured_at_iso=excluded.captured_at_iso
            """,
            (seat_id, start, end, status, class_name, checksum, captured_at),
        )

    conn.commit()

def main():
    seat_id = 49526
    seat_url = "https://libcal.rug.nl/seat/49526"

    # Voor één dag: end = volgende dag
    start_date = "2026-01-13"
    end_date = "2026-01-14"

    conn = init_db("libcal.sqlite")
    try:
        with requests.Session() as s:
            seat_name = fetch_seat_name(s, seat_id)

        upsert_seat(conn, seat_id, seat_url, seat_name)

        slots = fetch_slots(seat_id, start_date, end_date)
        insert_snapshot(conn, seat_id, slots)

        print(f"Fetched {len(slots)} slots and stored snapshot. seat_name={seat_name}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
