# discover_seats.py
from __future__ import annotations
import re
import time
import requests
from typing import Optional

SEAT_LIST_PAGE = "https://libcal.rug.nl/seats"


def fetch_all_seat_ids(session: Optional[requests.Session] = None) -> list[int]:
    s = session or requests.Session()
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


def _strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_seat_name(name: str) -> str:
    # "4.A.20 (UB City Centre, ...)" -> "4.A.20"
    name = name.strip()
    if " (" in name:
        name = name.split(" (", 1)[0]
    return name.strip()


def extract_seat_name_from_seat_page(html: str) -> Optional[str]:
    """
    Tries multiple patterns because LibCal pages vary and may not put the seat name in <h1>.
    """
    # A) <h1>
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if m:
        name = _strip_tags(m.group(1))
        if name:
            return normalize_seat_name(name)


    # B) common named elements (heuristics)
    # Sometimes the name is in an element like: <span class="item-title">4.C.02</span>
    for pat in [
        r'class="[^"]*(?:space|seat)[^"]*(?:name|title)[^"]*"[^>]*>(.*?)</',
        r'class="[^"]*item-title[^"]*"[^>]*>(.*?)</',
        r'data-space-name="([^"]+)"',
        r'data-seat-name="([^"]+)"',
    ]:
        m = re.search(pat, html, re.I | re.S)
        if m:
            candidate = _strip_tags(m.group(1))
            if candidate:
                return candidate

    # C) <title> fallback
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if m:
        title = _strip_tags(m.group(1))
        if title:
            # try to extract middle part: "LibCal - 4.C.02 - ..."
            parts = [p.strip() for p in re.split(r"[-|•]", title) if p.strip()]
            if len(parts) >= 2:
                return parts[1]
            return title

    return None

def fetch_seat_name_from_html(html: str) -> Optional[str]:
    # single source of truth for seat-name parsing
    return extract_seat_name_from_seat_page(html)


def fetch_seat_name(session: requests.Session, seat_id: int) -> Optional[str]:
    url = f"https://libcal.rug.nl/seat/{seat_id}"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return fetch_seat_name_from_html(r.text)


def fetch_all_seats_with_names(
    polite_sleep: float = 0.05,
    limit: Optional[int] = None,
    debug_first_failure_to_file: bool = True,
) -> list[tuple[int, str, Optional[str]]]:
    """
    Returns list of (seat_id, seat_url, seat_name_or_none)
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; seat-discovery/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://libcal.rug.nl/seats",
    })

    seat_ids = fetch_all_seat_ids(session=s)
    if limit is not None:
        seat_ids = seat_ids[:limit]

    out: list[tuple[int, str, Optional[str]]] = []
    first_fail_saved = False

    for i, seat_id in enumerate(seat_ids, 1):
        seat_url = f"https://libcal.rug.nl/seat/{seat_id}"
        try:
            seat_name = fetch_seat_name(s, seat_id)
            if seat_name is None and debug_first_failure_to_file and not first_fail_saved:
                # save HTML once to inspect where the name actually is
                r = s.get(seat_url, timeout=30)
                with open("debug_one_seat.html", "w", encoding="utf-8") as f:
                    f.write(r.text)
                first_fail_saved = True
            out.append((seat_id, seat_url, seat_name))
        except Exception as e:
            out.append((seat_id, seat_url, None))
        time.sleep(polite_sleep)

    return out

def find_if_power_available(html: str) -> bool:
    """
    Returns True iff the seat page contains the text 'Power Available'
    (case-insensitive). Otherwise False.
    """
    return "power available" in html.lower()
