# libcal_bot/book_seats/automatic_checkin.py
from __future__ import annotations

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


CHECKIN_URL = "https://libcal.rug.nl/r/checkin"


class CheckinError(RuntimeError):
    pass

