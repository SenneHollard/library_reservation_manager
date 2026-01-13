# find_available_seats.py
import sqlite3
from typing import List, Tuple


SQL_FULLY_AVAILABLE = """
WITH interval_slots AS (
  SELECT start_iso, end_iso
  FROM timeslots
  WHERE start_iso >= :x
    AND end_iso   <= :y
  GROUP BY start_iso, end_iso
),
needed AS (
  SELECT COUNT(*) AS n FROM interval_slots
),
per_seat AS (
  SELECT seat_id, COUNT(*) AS k
  FROM timeslots
  WHERE status = 'AVAILABLE'
    AND start_iso >= :x
    AND end_iso   <= :y
  GROUP BY seat_id
)
SELECT s.seat_id, s.seat_url
FROM per_seat p
JOIN needed n
JOIN seats s ON s.seat_id = p.seat_id
WHERE p.k = n.n
  AND n.n > 0
ORDER BY s.seat_id;
"""

def seats_fully_available(db_path: str, x: str, y: str) -> List[Tuple[int, str]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(SQL_FULLY_AVAILABLE, {"x": x, "y": y}).fetchall()
        return [(int(seat_id), str(seat_url)) for seat_id, seat_url in rows]
    finally:
        conn.close()

if __name__ == "__main__":
    # voorbeeld: morgen 10:00–13:30
    x = "2026-01-13 10:00:00"
    y = "2026-01-13 13:30:00"

    seats = seats_fully_available("libcal.sqlite", x, y)
    print(f"{len(seats)} seats fully available from {x} to {y}")
    for seat_id, url in seats[:25]:
        print(seat_id, url)
