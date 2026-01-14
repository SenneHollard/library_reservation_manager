# app.py
import json
import time
import sqlite3
from pathlib import Path
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from libcal_bot.paths import DB_PATH
from libcal_bot.fetch_availability.db import init_db
from libcal_bot.fetch_availability.fetch_all_seats import init_static_data
from libcal_bot.app.libcal_actions import (
    get_available_seats,
    update_availability_for_date,
    book_seat_now,
    load_all_seats_from_db,
    run_checkin_now,
    run_hunt_now,
    to_libcal_label
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

AREA_OPTIONS = [
    "1.B",
    "2.A", "2.B", "2.C",
    "3.A", "3.B", "3.C",
    "4.A", "4.B", "4.C",
]

POWER_OPTIONS = ["Power available", "No power"]  # you can select one or both


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
        key="start_time",
    )

start_idx = OPTIONS.index(st.session_state.start_time)
end_options = OPTIONS[start_idx + 1:]

# bepaal default index
if "end_time" in st.session_state and st.session_state.end_time in end_options:
    end_index =