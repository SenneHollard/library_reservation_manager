# app.py
import json
import time
import sqlite3
from pathlib import Path
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

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
    to_libcal_label,
    next_hunting_tick,
    worker_is_running
)
from libcal_bot.worker.tasks import list_checkins, cancel_checkin, start_hunting, get_hunting_status, stop_hunting, schedule_checkin


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
    end_index = end_options.index(st.session_state.end_time)
else:
    end_index = end_options.index("22:00") if "22:00" in end_options else 0

with colC:
    end_time = st.selectbox(
        "End",
        end_options,
        index=end_index,
        key="end_time",
    )

x = f"{d.isoformat()} {start_time}:00"
end_date = d if end_time != "00:00" else (d + timedelta(days=1))
y = f"{end_date.isoformat()} {end_time}:00"

st.caption(f"Query interval: {x} → {y}")
st.divider()


# ----------------------------
# Main sections: Seats | Book | Automate
# ----------------------------

seats_col, book_col, automate_col = st.columns(3)

seats = get_available_seats(x, y)

# ==========
# Seats
# ==========
with seats_col:
    st.subheader("Seats")

    if not seats:
        st.warning("No seats available in this interval (or no data available).")
    else:
        st.success(f"{len(seats)} seats fully available.")
        df = pd.DataFrame(seats, columns=["seat_name", "seat_url", "seat_id", "power_available"])
        st.dataframe(df[["seat_name", "power_available", "seat_url"]], width="stretch")

# ==========
# Book
# ==========
with book_col:
    st.subheader("Book")

    if not seats:
        all_seats = load_all_seats_from_db()

        if not all_seats:
            st.info("No seats found in DB yet. Run seat discovery / init first.")
            chosen_name = None
            chosen_id = None
            chosen_url = None
        else:
            chosen_name = st.selectbox(
                "Choose a seat to try booking anyway",
                options=list(all_seats.keys()),
                index=None,
                placeholder="Type to search…",
                key="fallback_seat_name",
            )
            chosen_id, chosen_url = all_seats[chosen_name] if chosen_name else (None, None)

        if st.button("Book seat (try anyway)",  type="primary", key="book_anyway"):
            profile = st.session_state.profile
            required = ["first_name", "last_name", "email", "phone", "student_number"]
            missing = [k for k in required if not profile.get(k)]

            if missing:
                st.error(f"Please fill booking settings first: {', '.join(missing)}")
            elif not chosen_id:
                st.error("Please select a seat first.")
            else:
                st.info(f"Trying to book seat {chosen_name}…")
                try:
                    start_time_booking = to_libcal_label(start_time)
                    msg = book_seat_now(
                        chosen_id,
                        rf"^{start_time_booking}(am|pm)?\b.*",
                        y,
                        profile,
                    )
                    st.success(msg)
                    if chosen_url:
                        st.markdown(chosen_url)
                except Exception as e:
                    st.error(f"Booking failed: {e}")

    else:
        options = {f"{name}": (seat_id, url) for (name, url, seat_id, power) in seats}

        chosen_name = st.selectbox(
            "Choose a seat to book",
            list(options.keys()),
            key="available_seat_name",
        )
        chosen_id, chosen_url = options[chosen_name]

        if st.button(f"Book seat {chosen_name}",  type="primary", key="book_selected"):
            profile = st.session_state.profile
            required = ["first_name", "last_name", "email", "phone", "student_number"]
            missing = [k for k in required if not profile.get(k)]

            if missing:
                st.error(f"Please fill booking settings first: {', '.join(missing)}")
            else:
                st.info(f"Trying to book seat {chosen_name}…")
                try:
                    start_time_booking = to_libcal_label(start_time)
                    msg = book_seat_now(
                        chosen_id,
                        rf"^{start_time_booking}(am|pm)?\b.*",
                        y,
                        profile,
                    )
                    st.success(msg)
                    st.markdown(chosen_url)
                except Exception as e:
                    st.error(f"Booking failed: {e}")

# ==========
# Automate
# ==========
with automate_col:
    st.subheader("Automate")

    if "show_checkin_form" not in st.session_state:
        st.session_state.show_checkin_form = False
    if "show_hunt_form" not in st.session_state:
        st.session_state.show_hunt_form = False

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Plan check-in", type="primary", key="btn_auto_checkin"):
            st.session_state.show_checkin_form = True
            st.session_state.show_hunt_form = False
    with b2:
        if st.button("Start Hunting", type="primary", key="btn_start_hunting"):
            st.session_state.show_hunt_form = True
            st.session_state.show_checkin_form = False

    # --- Check-in form ---
    if st.session_state.show_checkin_form:
        with st.form("checkin_form"):
            st.markdown("#### Schedule check-in")

            checkin_date = st.date_input("Date", value=d, key="checkin_date")
            checkin_start = st.selectbox("Start time", OPTIONS, key="checkin_start")

            checkin_code = st.text_input(
                "Check-in code",
                placeholder="Enter check-in code",
                key="checkin_code",
            )

            run_now = st.checkbox("Run now", value=False, key="checkin_run_now")

            confirm = st.form_submit_button("Confirm check-in", type = 'primary')

        if confirm:
            if not checkin_code.strip():
                st.error("Please enter a check-in code.")
            elif run_now:
                with st.spinner("Running check-in now…"):
                    try:
                        msg = run_checkin_now(checkin_code)
                        st.success(msg)
                    except Exception as e:
                        st.error(f"Check-in failed: {e}")
            else:
                task_id = schedule_checkin(
                    checkin_date=str(checkin_date),
                    checkin_start=checkin_start,
                    code=checkin_code,
                )

                st.success(f"✅ Check-in scheduled (id={task_id}) for {checkin_date} at {checkin_start} (+5 min).")
    
        st.divider()

    # --- Hunting form ---
    if st.session_state.show_hunt_form:
        with st.form("hunt_form"):
            st.markdown("#### Set hunting zone")

            power_selection = st.multiselect(
                "Power available",
                options=POWER_OPTIONS,
                default=POWER_OPTIONS,
                key="hunt_power",
            )

            areas = st.multiselect(
                "Area",
                options=AREA_OPTIONS,
                default=[],
                key="hunt_areas",
            )

            confirm_hunt = st.form_submit_button("Confirm hunting",  type="primary")

            if confirm_hunt:
                start_dt = datetime.fromisoformat(x)   # jouw x/y
                end_dt = datetime.fromisoformat(y)

                profile = st.session_state.profile
                required = ["first_name", "last_name", "email", "phone", "student_number"]
                missing = [k for k in required if not profile.get(k)]

                if missing:
                    st.error(f"Fill booking settings first (needed for auto-book): {', '.join(missing)}")
                else:
                    # 1) Preview (NO booking)
                    with st.spinner("Previewing hunting… counting candidates"):
                        try:
                            preview = run_hunt_now(
                                start_dt=start_dt,
                                end_dt=end_dt,
                                hunting_power=power_selection,
                                hunting_areas=areas,
                                profile=profile,
                                try_book=False,   # <- preview only
                            )
                        except Exception as e:
                            st.error(f"Preview failed: {e}")
                            preview = None

                    # 2) Start background hunting
                    payload = dict(
                        start_dt=start_dt,
                        end_dt=end_dt,
                        hunting_power=power_selection,
                        hunting_areas=areas,
                        profile=profile,
                        try_book=True,
                    )
                    start_hunting(payload=payload)

                    # 3) Message: candidates + next run time
                    TZ = ZoneInfo("Europe/Amsterdam")
                    nxt = next_hunting_tick(datetime.now(TZ), minutes=(0, 30))
                    if preview is not None:
                        st.success(
                            f"✅ Hunting activated. Candidates now: {preview.get('candidates', '?')}. "
                            f"Next attempt at {nxt.strftime('%H:%M')}."
                        )
                    else:
                        st.success(
                            f"✅ Hunting activated. Next attempt at {nxt.strftime('%H:%M')}."
                        )

                st.session_state.show_hunt_form = False
    
    # -----------------------
    # Scheduled check-ins list
    # -----------------------
    st.markdown("### Scheduled & Status")
    checkins = list_checkins(limit=100)  # all statuses
    if not checkins:
        st.info("No scheduled check-ins yet.")
    else:
        st.markdown("#### Cancel a pending check-in")
        pending = [c for c in checkins if c["status"] == "pending"]
        if not pending:
            st.caption("No pending check-ins to cancel.")
        else:
            # show buttons per pending checkin
            for c in pending:
                c1, c2, c3 = st.columns([2, 2, 1])
                with c1:
                    st.write(f"ID **{c['id']}**")
                with c2:
                    st.write(f"Runs at **{c['run_at_iso']}**")
                with c3:
                    if st.button("Cancel", key=f"cancel_checkin_{c['id']}"):
                        ok = cancel_checkin(checkin_id=c["id"])
                        if ok:
                            st.success(f"Cancelled check-in {c['id']}.")
                        else:
                            st.warning("Could not cancel (maybe it already started).")
                        st.rerun()

    # -----------------------
    # Hunting status + stop
    # -----------------------
    st.divider()
    st.markdown("#### Hunting status")

    hs = get_hunting_status()
    if hs.get("active"):
        st.success("🟢 Hunting is ACTIVE")
        st.write(f"Started: {hs.get('created_at_iso')}")
        st.write(f"Last run: {hs.get('last_run_at_iso')}")
        if hs.get("error"):
            st.error(f"Last error: {hs['error']}")
        if hs.get("booked"):
            st.success(f"Booked: {hs['booked']}")
        if st.button("Stop hunting", type="primary", key="btn_stop_hunting"):
            stop_hunting(reason="Stopped from UI")
            st.success("Hunting stopped.")
            st.rerun()
    else:
        st.info("🔴 Hunting is NOT active")
        if hs.get("stopped_at_iso"):
            st.caption(f"Stopped at: {hs.get('stopped_at_iso')}")
        if hs.get("error"):
            st.caption(f"Last error: {hs.get('error')}")
        if hs.get("booked"):
            st.caption(f"Last booked: {hs.get('booked')}")


# ----------------------------
# Bottom: Data (advanced / debug)
# ----------------------------

st.divider()
st.markdown("### Data")

if worker_is_running():
    st.success(
        "Background worker is running — availability is updated automatically. "
        "Manual refresh is usually unnecessary."
    )
else:
    st.warning(
        "⚠️ Background worker not detected. "
        "Automatic updates may not be running."
    )

st.caption(
    "Availability is normally updated automatically in the background. "
    "Use this only if you want to force a manual refresh."
)

with st.expander("Advanced: force refresh availability", expanded=False):
    if st.button(
        "Force refresh availability (advanced)",
        type="secondary",
        key="force_refresh_availability",
    ):
        progress = st.progress(0)
        status = st.empty()
        started = time.time()

        def cb(i, total, seat_id, failed):
            pct = int((i / total) * 100) if total else 0
            progress.progress(pct)
            status.write(
                f"Refreshing availability {i}/{total} "
                f"(failed: {failed}) — last seat: {seat_id}"
            )

        with st.spinner("Forcing availability refresh…"):
            total, failed = update_availability_for_date(
                d.isoformat(),
                (d + timedelta(days=1)).isoformat(),
                progress_cb=cb,
            )

        elapsed = time.time() - started
        st.success(
            f"Refresh complete. "
            f"Processed {total} seats, failed {failed}. "
            f"Took {elapsed:.1f}s."
        )
