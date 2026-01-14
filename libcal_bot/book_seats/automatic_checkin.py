# libcal_bot/book_seats/automatic_checkin.py
from __future__ import annotations

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


CHECKIN_URL = "https://libcal.rug.nl/r/checkin"


class CheckinError(RuntimeError):
    pass


def checkin_now(code: str, headless: bool = True, slow_mo: int = 0) -> str:
    """
    Opens https://libcal.rug.nl/r/checkin, enters the check-in code, submits, and closes the browser.

    Returns a short status message on success.
    Raises CheckinError on failure.
    """
    code = (code or "").strip()
    if not code:
        raise CheckinError("Empty check-in code.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto(CHECKIN_URL, wait_until="domcontentloaded", timeout=30_000)

            # --- Find the input field ---
            # LibCal pages can vary; try a few robust selectors.
            input_locator = (
                page.locator("input[name='code']").first
                .or_(page.locator("input#code").first)
                .or_(page.locator("input[type='text']").first)
            )

            try:
                input_locator.wait_for(state="visible", timeout=10_000)
            except PlaywrightTimeoutError:
                raise CheckinError("Could not find a visible check-in input field on the page.")

            input_locator.fill(code)

            # --- Find a submit/check-in button ---
            # Try button with text first; fallback to submit input/button.
            button_locator = (
                page.get_by_role("button", name="Check In").first
                .or_(page.get_by_role("button", name="Check in").first)
                .or_(page.locator("button[type='submit']").first)
                .or_(page.locator("input[type='submit']").first)
            )

            try:
                button_locator.wait_for(state="visible", timeout=5_000)
            except PlaywrightTimeoutError:
                raise CheckinError("Could not find a Check In / submit button.")

            button_locator.click()

            # --- Determine result ---
            # We don't know exact DOM/messages, so we look for common success/failure cues.
            # Adjust these strings if you see different text in the page.
            page.wait_for_timeout(1200)  # small wait for response render

            body_text = page.locator("body").inner_text().lower()

            # Typical outcomes (guessing common phrasing)
            success_markers = [
                "checked in",
                "success",
                "you are checked in",
                "check-in complete",
            ]
            error_markers = [
                "invalid",
                "not found",
                "expired",
                "error",
                "already checked in",
                "unable",
            ]

            if any(m in body_text for m in success_markers) and "invalid" not in body_text:
                return "✅ Check-in successful."

            # If it contains "already checked in", treat as OK-ish:
            if "already checked in" in body_text:
                return "✅ Already checked in."

            if any(m in body_text for m in error_markers):
                raise CheckinError("Check-in failed (page shows an error).")

            # If we can't confidently parse: return neutral but not error
            return "⚠️ Submitted check-in code, but could not confirm result from page text. Please verify manually."

        finally:
            context.close()
            browser.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="LibCal check-in automation")
    parser.add_argument("code", help="Check-in code (string)")
    parser.add_argument("--headed", action="store_true", help="Run with a visible browser window")
    parser.add_argument("--slowmo", type=int, default=0, help="Slow motion in ms (debug)")
    args = parser.parse_args()

    msg = checkin_now(args.code, headless=not args.headed, slow_mo=args.slowmo)
    print(msg)


if __name__ == "__main__":
    main()
