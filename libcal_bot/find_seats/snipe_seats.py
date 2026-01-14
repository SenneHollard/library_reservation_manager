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
 