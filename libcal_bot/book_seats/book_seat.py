from __future__ import annotations

import re
from playwright.sync_api import sync_playwright
import os


def fail(page, reason: str):
    raise RuntimeError(f"Booking failed, because {reason}")


def book_seat_now(
    seat_id: int,
    start_label_regex: str,
    end_value: str,
    profile: dict
) -> str:
    url = f"https://libcal.rug.nl/seat/{seat_id}"

    # validate profile keys early
    required_keys = ["first_name", "last_name", "email", "phone", "student_number"]
    missing = [k for k in required_keys if not profile.get(k)]
    if missing:
        raise RuntimeError(f"Booking failed, because missing profile fields: {', '.join(missing)}")

    with sync_playwright() as p:
        slow_mo = int(os.getenv("SLOW_MO", "0"))
        browser = p.chromium.launch(headless=True, slow_mo=slow_mo)
        page = browser.new_page()

        try:
            page.goto(url, wait_until="networkidle")

            # 1) find start slot
            start_loc = page.get_by_label(re.compile(start_label_regex))
            if start_loc.count() == 0:
                fail(page, f"start timeslot '{start_label_regex}' was not found on the page")

            # 2) click start until end dropdown appears
            end_select_locator = page.locator("select").filter(
                has=page.locator(f'option[value="{end_value}"]')
            )

            for _ in range(3):
                try:
                    start_loc.first.scroll_into_view_if_needed(timeout=10)
                except Exception:
                    pass

                try:
                    start_loc.first.click(timeout=10)
                except Exception:
                    try:
                        start_loc.first.click(timeout=10, force=True)
                    except Exception:
                        pass

                page.wait_for_timeout(300)

                if end_select_locator.count() > 0:
                    break

            if end_select_locator.count() == 0:
                fail(page, "end-time dropdown did not appear after selecting start time (click may not have registered or slot is not bookable)")

            end_select = end_select_locator.first
            try:
                end_select.select_option(end_value, timeout=10)
            except Exception:
                fail(page, f"could not select end time '{end_value}' (slot/end time not available)")

            # 3) submit times + continue
            submit_times = page.get_by_role("button", name=re.compile(r"Submit\s*Times?", re.I))
            if submit_times.count() == 0:
                fail(page, "could not find 'Submit Times' button (page flow changed)")
            submit_times.first.click(timeout=10)

            cont = page.get_by_role("button", name=re.compile(r"Continue", re.I))
            if cont.count() == 0:
                fail(page, "could not find 'Continue' button (page flow changed)")
            cont.first.click(timeout=10)

            # 4) fill form
            def fill_required(label_regex: str, value: str, field_name: str):
                loc = page.get_by_role("textbox", name=re.compile(label_regex, re.I))
                if loc.count() == 0:
                    fail(page, f"required field '{field_name}' not found")
                loc.first.fill(value, timeout=10)

            fill_required(r"First Name", profile["first_name"], "First Name")
            fill_required(r"Last Name", profile["last_name"], "Last Name")
            fill_required(r"Email", profile["email"], "Email")
            fill_required(r"phonenumber", profile["phone"], "Phone number")
            fill_required(r"S- or P-number", profile["student_number"], "S/P number")

            # 5) submit booking
            submit_booking = page.get_by_role("button", name=re.compile(r"Submit my Booking", re.I))
            if submit_booking.count() == 0:
                fail(page, "could not find 'Submit my Booking' button")
            submit_booking.first.click(timeout=10)

            page.wait_for_load_state("networkidle")

            body = page.inner_text("body").lower()
            if "confirmed" in body or "success" in body or "reservation" in body:
                return f"Booked seat {seat_id} successfully."
            return f"Submitted booking for seat {seat_id}, but no clear confirmation text was found (check booking_result.png)."

        finally:
            browser.close()
