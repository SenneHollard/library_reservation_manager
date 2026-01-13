# fetch_all_seats.py
from __future__ import annotations

import time
import sqlite3
from datetime import datetime, timezone

import requests

from db import init_db
from discover_allseat_id import fetch_all_seat_ids
from fetch_one_seat import GRID_URL, status_from_classname, upsert_seat


def fetch_slots_with_retry(
    session: requests.Session,
    seat_id: int,
    start_date: str,
    end_date: str,
    lid=1443, gid=3634, eid=10948, zone=0,
    page_index=0, page_size=200,
    max_retries: int = 5,
) -> list[dict]:
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

    for attempt in range(max_retries):
        r = session.post(GRID_URL, data=data, timeout=30)

        # Rate-limit / tijdelijke server errors -> exponential backoff
        if r.status_code in (429, 500, 502, 503, 504):
            wait = min(60, 1.5 ** attempt)
            time.sleep(wait)
            continue

        r.raise_for_status()
        return r.json().get("slots", [])

    # laatste poging: raise voor debugging
    r.raise_for_status()
    return []


def upsert_timeslots(conn: sqlite3.Connection, seat_id: int, slots: list[dict]):
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


def main():
    # pas aan naar de dag die je wil
    start_date = "2026-01-13"
    end_date   = "2026-01-14"

    seat_ids = fetch_all_seat_ids()
    print(f"Found {len(seat_ids)} seats.")

    conn = init_db("libcal.sqlite")

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; seat-availability-fetch/1.0)",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://libcal.rug.nl",
        "Referer": "https://libcal.rug.nl/seats",
    })

    batch_size = 25          # commit elke 25 seats
    polite_sleep = 0.15      # throttle (0.1–0.5 is typisch ok)

    try:
        conn.execute("BEGIN")
        for i, seat_id in enumerate(seat_ids, 1):
            seat_url = f"https://libcal.rug.nl/seat/{seat_id}"
            upsert_seat(conn, seat_id, seat_url)

            try:
                slots = fetch_slots_with_retry(s, seat_id, start_date, end_date)
                upsert_timeslots(conn, seat_id, slots)
            except Exception as e:
                print(f"[{i}/{len(seat_ids)}] seat {seat_id} FAILED: {e}")

            if i % batch_size == 0:
                conn.commit()
                conn.execute("BEGIN")
                print(f"Processed {i}/{len(seat_ids)} seats...")

            time.sleep(polite_sleep)

        conn.commit()
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
