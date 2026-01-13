# discover_allseat_id.py
from __future__ import annotations
import re
import requests

SEAT_LIST_PAGE = "https://libcal.rug.nl/seats"

def fetch_all_seat_ids() -> list[int]:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; seat-availability-fetch/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://libcal.rug.nl/",
    })

    r = s.get(SEAT_LIST_PAGE, timeout=30)
    r.raise_for_status()
    html = r.text

    # 1) klassieke seat links
    ids = {int(m.group(1)) for m in re.finditer(r"/seat/(\d+)", html)}

    # 2) fallback: soms staan IDs in data-attributes of JSON blobs
    if not ids:
        ids |= {int(x) for x in re.findall(r'data-(?:seat|space)-id="(\d+)"', html)}
    if not ids:
        ids |= {int(x) for x in re.findall(r'"seatId"\s*:\s*(\d+)', html)}
    if not ids:
        ids |= {int(x) for x in re.findall(r'"id"\s*:\s*(\d+)', html)}

    return sorted(ids)

if __name__ == "__main__":
    seat_ids = fetch_all_seat_ids()
    print(f"Found {len(seat_ids)} seats.")
    print(seat_ids[:20])
