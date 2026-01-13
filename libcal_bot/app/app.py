# app.py
import pandas as pd
import streamlit as st
from datetime import date, timedelta, time
import time
import json
from pathlib import Path
from libcal_bot.paths import DB_PATH, PROFILE_PATH

from libcal_bot.app.libcal_actions import get_available_seats, update_availability_for_date, book_seat_now

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


def half_hour_options(start="08:00", end="22:00"):
    # returns ["08:00", "08:30", ..., "22:00"]
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

OPTIONS = half_hour_options("08:00", "22:00")


st.set_page_config(page_title="LibCal Seat Booker", layout="wide")
st.title("LibCal Seat Booker")

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

# Inputs
colA, colB, colC = st.columns(3)

with colA:
    d = st.date_input("Datum", value=date(2026, 1, 13))
with colB:
    start_time = st.selectbox("Start", OPTIONS, index=OPTIONS.index("10:00") if "10:00" in OPTIONS else 0)

# End options: only times AFTER start (so end > start)
start_idx = OPTIONS.index(start_time)
end_options = OPTIONS[start_idx + 1:]  # strictly later than start

with colC:
    default_end = "22:00"
    end_time = st.selectbox(
        "Eind",
        end_options,
        index=end_options.index(default_end) if default_end in end_options else 0
    )

# Build strings
x = f"{d.isoformat()} {start_time}:00"
y = f"{d.isoformat()} {end_time}:00"

st.caption(f"Query interval: {x} → {y}")

btn1, btn2, btn3 = st.columns(3)

with btn1:
    if st.button("Update availability", type="primary"):
        progress = st.progress(0)
        status = st.empty()
        started = time.time()

        def cb(i, total, seat_id, failed):
            pct = int((i / total) * 100) if total else 0
            progress.progress(pct)
            status.write(f"Processed {i}/{total} seats (failed: {failed}) — last seat: {seat_id}")

        with st.spinner("Fetching availability… this can take a while"):
            total, failed = update_availability_for_date(
                d.isoformat(),
                (d + timedelta(days=1)).isoformat(),
                progress_cb=cb
            )

        elapsed = time.time() - started
        st.success(f"Availability updated. Processed {total} seats, failed {failed}. Took {elapsed:.1f}s.")

with btn2:
    if st.button("Show available seats"):
        seats = get_available_seats(x, y)
        st.success(f"{len(seats)} seats fully available.")
        df = pd.DataFrame(seats, columns=["seat_name", "seat_url", "seat_id"])
        st.dataframe(df[["seat_name", "seat_url"]], use_container_width=True)

with btn3:
    seats = get_available_seats(x, y)

    if not seats:
        st.warning("No seats available in this interval.")
    else:
        # seats bevat tuples: (seat_name, seat_url, seat_id)
        options = {
            f"{name}": (seat_id, url)
            for (name, url, seat_id) in seats
        }

        chosen_name = st.selectbox("Choose a seat to book", list(options.keys()))
        chosen_id, chosen_url = options[chosen_name]

        if st.button(f"Book seat {chosen_name}"):
            start_label_regex = rf"^{start_time}(am|pm)?\b.*"  # evt aanpassen aan LibCal labels
            end_value = f"{d.isoformat()} {end_time}:00"

            profile = st.session_state.profile
            required = ["first_name", "last_name", "email", "phone", "student_number"]
            missing = [k for k in required if not profile.get(k)]

            if missing:
                st.error(f"Please fill booking settings first: {', '.join(missing)}")
            else:
                st.info(f"Trying to book seat {chosen_name}…")
                try:
                    msg = book_seat_now(chosen_id, start_label_regex, end_value, profile)
                    st.success(msg)
                    st.markdown(chosen_url)
                except Exception as e:
                    st.error(f"Booking failed: {e}")
