# fetch_all_seats.py
from __future__ import annotations
import time
import requests
import sqlite3
from datetime import datetime, timezone

from libcal_bot.fetch_availability.db import init_db
from libcal_bot.fetch_availability.discover_seats import fetch_all_seat_ids
from libcal_bot.fetch_availability.fetch_one_seat import GRID_URL, status_from_classname, upsert_seat


def fetch_slots_with_retry(session: requests.Session, seat_id: int, start_date: str, end_date: str,
                           lid=1443, gid=3634, eid=10948, zone=0, max_retries: int = 5) -> list[dict]:
    data = {
        "lid": str(lid),
        "gid": str(gid),
        "eid": str(eid),
        "seat": "true",
        "seatId": str(seat_id),
        "zone": str(zone),
        "start": start_date,
        "end": end_date,
        "pageIndex": "0",
        "pageSize": "200",
    }

    for attempt in range(max_retries):
        r = session.post(GRID_URL, data=data, timeout=30)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 1.5 ** attempt))
            continue
        r.raise_for_status()
        return r.json().get("slots", [])
    r.raise_for_status()
    return []


def upsert_timeslots(conn: sqlite3.Connection, seat_id: int, slots: list[dict]):
    captured_at = datetime.now(timezone.utc).isoformat()
    for it in slots:
        start = it.get("start")
        end = it.get("end")
        if not start or not end:
            continue
        class_name = it.get("className", "")
        checksum = it.get("checksum")
        status = status_from_classname(class_name)

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


def run_bulk_fetch(start_date: str, end_date: str, db_path: str | None = None,
                   batch_size: int = 25, polite_sleep: float = 0.15,
                   progress_cb=None) -> tuple[int, int]:
    """
    Returns (processed_count, failed_count)
    progress_cb: function(i, total, seat_id, failed_count) -> None
    """
    seat_ids = fetch_all_seat_ids()
    total = len(seat_ids)
    failed = 0

    conn = init_db(db_path)

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; seat-availability-fetch/1.0)",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://libcal.rug.nl",
        "Referer": "https://libcal.rug.nl/seats",
    })

    try:
        conn.execute("BEGIN")
        for i, seat_id in enumerate(seat_ids, 1):
            seat_url = f"https://libcal.rug.nl/seat/{seat_id}"
            seat_name = None
            try:
                seat_name = fetch_seat_name(s, seat_id)   # let op: s is requests.Session
            except Exception:
                seat_name = None

            upsert_seat(conn, seat_id, seat_url, seat_name)

            try:
                slots = fetch_slots_with_retry(s, seat_id, start_date, end_date)
                upsert_timeslots(conn, seat_id, slots)
            except Exception as e:
                failed += 1
                print(f"[{i}/{total}] seat {seat_id} FAILED: {e}")

            if i % batch_size == 0:
                conn.commit()
                conn.execute("BEGIN")

            if progress_cb is not None:
                progress_cb(i, total, seat_id, failed)

            time.sleep(polite_sleep)

        conn.commit()
        if progress_cb is not None:
            progress_cb(total, total, seat_ids[-1] if total else None, failed)

        return total, failed
    finally:
        conn.close()


def main():
    processed, failed = run_bulk_fetch("2026-01-13", "2026-01-14")
    print(f"Done. Processed {processed} seats, failed {failed}.")


if __name__ == "__main__":
    main()
