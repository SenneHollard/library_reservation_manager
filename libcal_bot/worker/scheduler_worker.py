# libcal_bot/worker/scheduler_worker.py
from __future__ import annotations
import os
import logging
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from libcal_bot.app.libcal_actions import run_checkin_now, run_hunt_now
from libcal_bot.worker.tasks import dispatch_due_checkins, active_hunting

from libcal_bot.fetch_availability.fetch_all_seats import clean_up, fetch_availability

TZ = ZoneInfo("Europe/Amsterdam")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

def nightly_job(db_path: str | None = None):
    # 1) Cleanup: verwijder alles vóór vandaag (UTC)
    today_utc = datetime.now(timezone.utc).date().isoformat()
    deleted = clean_up(db_path=db_path, delete_before=today_utc)
    logging.info("Nightly cleanup deleted rows=%s (cutoff_utc=%s)", deleted, today_utc)

    # 2) Update: komende 5 dagen (lokale tijd)
    now_local = datetime.now(TZ)
    start_day = now_local.date()
    end_day = start_day + timedelta(days=5)  # end is exclusive in veel APIs; jouw call gebruikt strings

    # Als jouw LibCal endpoint een inclusive end verwacht, gebruik dan +4 i.p.v. +5.
    # In jouw fetch_slots_with_retry gaat 'end' mee naar LibCal; vaak is dat een einddatum.
    start_date = start_day.isoformat()
    end_date = end_day.isoformat()

    logging.info("Nightly availability update: start=%s end=%s", start_date, end_date)
    processed, failed = fetch_availability(
        start_date=start_date,
        end_date=end_date,
        db_path=db_path,
    )
    logging.info("Nightly availability update done: processed=%s failed=%s", processed, failed)


def update_today_job(db_path: str | None = None):
    today = datetime.now(TZ).date()
    start_date = today.isoformat()
    end_date = (today + timedelta(days=1)).isoformat()

    logging.info(
        "Updating today availability: start=%s end=%s",
        start_date,
        end_date,
    )

    processed, failed = fetch_availability(
        start_date=start_date,
        end_date=end_date,
        db_path=db_path,
    )

    logging.info(
        "Update today done: processed=%s failed=%s",
        processed,
        failed,
    )

def dispatch_checkins_job():
    n = dispatch_due_checkins(run_checkin_now=run_checkin_now)
    if n:
        logging.info("Ran %s scheduled checkin(s)", n)

def hunting_tick_job():
    result = active_hunting(run_hunt_now=run_hunt_now)
    if result is not None:
        logging.info("Hunting tick result: %s", result.get("msg", "ok"))

def main():
    os.makedirs("data", exist_ok=True)

    scheduler = BlockingScheduler(
        timezone=TZ,
        jobstores={"default": SQLAlchemyJobStore(url="sqlite:///data/jobs.sqlite")},
    )

    # Nacht: 04:05
    scheduler.add_job(
        nightly_job,
        trigger="cron",
        hour=4,
        minute=5,
        id="nightly_job",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60 * 60,
    )

    # Overdag elke 30 min (08:45–20:45)
    scheduler.add_job(
        update_today_job,
        trigger="cron",
        hour="8-20",
        minute="15,45",
        id="update_today_halfhour",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60 * 20,
    )

    scheduler.add_job(
        dispatch_checkins_job,
        trigger="cron",
        second=0,
        id="dispatch_checkins",
        replace_existing=True)

    scheduler.add_job(
        hunting_tick_job,
        trigger="cron",
        hour="9-20",
        minute="0,30",
        id="hunting_tick",
        replace_existing=True,
    )

    logging.info("Scheduler started.")
    scheduler.start()

if __name__ == "__main__":
    main()
