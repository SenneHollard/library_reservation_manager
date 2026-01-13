# app.py
import pandas as pd
import streamlit as st
from datetime import date, timedelta
import time
import json
from pathlib import Path

from libcal_actions import get_available_seats, update_availability_for_date, book_seat_now

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

st.set_page_config(page_title="LibCal Seat Booker", layout="wide")
st.title("LibCal Seat Booker (MVP)")

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
    start_time = st.text_input("Start (HH:MM)", "10:00")
with colC:
    end_time = st.text_input("Eind (HH:MM)", "13:30")

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
    if st.button("Book best seat"):
        seats = get_available_seats(x, y)
        if not seats:
            st.warning("No seats available in this interval.")
        else:
            best_name, best_url, best_id = seats[0]
            st.info(f"Trying to book seat {best_id}…")
            # Start label/end value moeten matchen met jouw LibCal UI:
            start_label_regex = rf"^{start_time}(am|pm)?\b.*"  # mogelijk aanpassen
            end_value = f"{d.isoformat()} {end_time}:00"

            try:
                profile = st.session_state.profile
                required = ["first_name", "last_name", "email", "phone", "student_number"]
                missing = [k for k in required if not profile.get(k)]
                if missing:
                    st.error(f"Please fill booking settings first: {', '.join(missing)}")
                else:
                    msg = book_seat_now(best_id, start_label_regex, end_value, st.session_state.profile)
                    st.success(msg)
                st.success(msg)
                st.markdown(best_url)
            except NotImplementedError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Booking failed: {e}")
