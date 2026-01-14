import json
import time
import sqlite3
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from libcal_bot.paths import DB_PATH
from libcal_bot.fetch_availability.db import init_db
from libcal_bot.fetch_availability.fetch_all_seats import init_static_data
from libcal_bot.app.libcal_actions import (
    get_available_seats,
    update_availability_for_date,
    book_seat_now,
)

# ----------------------------
# Profile handling
# ----------------------------

PROFILE_PATH = Path(__file__).resolve().parent / "user_profile.json"


def load_profile() -> dict:
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return {
        "first_name": "",
        "last_name": "",
        "email": "",
        "phone": "",
        "student_number": "",
    }


def save_profile(profile: dict) -> None:
    PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")


# ----------------------------
# Time helpers
# ----------------------------

def half_hour_options(start="09:00", end="23:30"):
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))

    opts = []
    h, m = sh, sm
    while (h, m) <= (eh, em):
        opts.append(f"{h:02d}:{m:02d}")
        m += 30
        if m >= 60:
            h += 1
            m -= 60
    return opts


OPTIONS = half_hour_options("09:00", "23:30") + ["00:00"]


# ----------------------------
# Database readiness check
# ----------------------------


def db_ready() -> tuple[bool, str]:
    # maak DB + schema altijd aan
    conn = init_db(str(DB_PATH))
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='seats'")
        if cur.fetchone() is None:
            return False, "Database schema ontbreekt (geen seats tabel)."

        n = conn.execute("SELECT COUNT(*) FROM seats").fetchone()[0]
        if n == 0:
            return False, "Database bestaat, maar seats zijn nog leeg. Initialiseer dataset."
        return True, f"Database OK ({n} seats)."
    except sqlite3.Error as e:
        return False, f"Database error: {e}"
    finally:
        conn.close()



# ----------------------------
# Streamlit app start
# ----------------------------

st.set_page_config(page_title="LibCal Seat Booker", layout="wide")
st.title("LibCal Seat Booker")

ok, msg = db_ready()

# ----------------------------
# First-run initialisation
# ----------------------------

if not ok:
    st.warning(msg)
    st.info(
        "The database is not initialised yet. "
        "Click below to build the static seat dataset (this may take a few minutes)."
    )

    if st.button("Initialise dataset", type="primary"):
        progress = st.progress(0)
        status = st.empty()
        started = time.time()

        def cb(i, total, seat_id, failed):
            pct = int((i / total) * 100) if total else 0
            progress.progress(pct)
            status.write(
                f"Initialising seats {i}/{total} "
                f"(failed: {failed}) — last seat: {seat_id}"
            )

        with st.spinner("Initialising static seat data…"):
            total, failed = init_static_data(
                db_path=DB_PATH,
                progress_cb=cb,
            )

        elapsed = time.time() - started
        st.success(
            f"Static dataset initialised. "
            f"Processed {total} seats, failed {failed}. "
            f"Took {elapsed:.1f}s."
        )

        st.rerun()

    st.stop()


# ----------------------------
# Sidebar: user profile
# ----------------------------

st.sidebar.header("Booking settings")

if "profile" not in st.session_state:
    st.session_state.profile = load_profile()

p = st.session_state.profile

p["first_name"] = st.sidebar.text_input("First name", value=p["first_name"])
p["last_name"] = st.sidebar.text_input("Last name", value=p["last_name"])
p["email"] = st.sidebar.text_input("Email", value=p["email"])
p["phone"] = st.sidebar.text_input("Phone", value=p["phone"])
p["student_number"] = st.sidebar.text_input("Student number", value=p["student_number"])

if st.sidebar.button("Save profile"):
    save_profile(p)
    st.sidebar.success("Saved locally.")


# ----------------------------
# Main inputs
# ----------------------------

colA, colB, colC = st.columns(3)

with colA:
    d = st.date_input("Date", value=date.today())

with colB:
    start_time = st.selectbox(
        "Start",
        OPTIONS,
        index=OPTIONS.index("10:00") if "10:00" in OPTIONS else 0,
    )

start_idx = OPTIONS.index(start_time)
end_options = OPTIONS[start_idx + 1:]

with colC:
    end_time = st.selectbox(
        "End",
        end_options,
        index=end_options.index("22:00") if "22:00" in end_options else 0,
    )

x = f"{d.isoformat()} {start_time}:00"
end_date = d if end_time != "00:00" else (d + timedelta(days=1))
y = f"{end_date.isoformat()} {end_time}:00"

st.caption(f"Query interval: {x} → {y}")


# ----------------------------
# Actions
# ----------------------------

btn1, btn2, btn3 = st.columns(3)

with btn1:
    if st.button("Update availability", type="primary"):
        progress = st.progress(0)
        status = st.empty()
        started = time.time()

        def cb(i, total, seat_id, failed):
            pct = int((i / total) * 100) if total else 0
            progress.progress(pct)
            status.write(
                f"Updating availability {i}/{total} "
                f"(failed: {failed})"
                f"last seat: {seat_id}"
            )

        with st.spinner("Fetching availability…"):
            total, failed = update_availability_for_date(
                d.isoformat(),
                (d + timedelta(days=1)).isoformat(),
                progress_cb=cb,
            )

        elapsed = time.time() - started
        st.success(
            f"Availability updated. "
            f"Processed {total} seats, failed {failed}. "
            f"Took {elapsed:.1f}s."
        )

with btn2:
    if st.button("Show available seats"):
        seats = get_available_seats(x, y)
        st.success(f"{len(seats)} seats fully available.")
        df = pd.DataFrame(seats, columns=["seat_name", "seat_url", "seat_id", "power_available"])
        st.dataframe(df[["seat_name", "power_available", "seat_url"]], use_container_width=True)

with btn3:
    seats = get_available_seats(x, y)

    if not seats:
        st.warning("No seats available in this interval.")
    else:
        options = {f"{name}": (seat_id, url) for (name, url, seat_id, power) in seats}

        chosen_name = st.selectbox("Choose a seat to book", list(options.keys()))
        chosen_id, chosen_url = options[chosen_name]

        if st.button(f"Book seat {chosen_name}"):
            profile = st.session_state.profile
            required = ["first_name", "last_name", "email", "phone", "student_number"]
            missing = [k for k in required if not profile.get(k)]

            if missing:
                st.error(f"Please fill booking settings first: {', '.join(missing)}")
            else:
                st.info(f"Trying to book seat {chosen_name}…")
                try:
                    msg = book_seat_now(
                        chosen_id,
                        rf"^{start_time}(am|pm)?\b.*",
                        y,
                        profile,
                    )
                    st.success(msg)
                    st.markdown(chosen_url)
                except Exception as e:
                    st.error(f"Booking failed: {e}")
