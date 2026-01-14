from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from libcal_bot.fetch_availability.db import init_db

TZ = ZoneInfo("Europe/Amsterdam")

SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduled_checkins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_at_iso TEXT NOT NULL,                 -- tz-aware ISO datetime
  code TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending|running|done|failed|cancelled
  created_at_iso TEXT NOT NULL,
  started_at_iso TEXT,
  finished_at_iso TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_checkins_due
ON scheduled_checkins(status, run_at_iso);

-- Keep it simple: exactly ONE global hunting state row (id=1)
CREATE TABLE IF NOT EXISTS hunting_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  active INTEGER NOT NULL DEFAULT 0,        -- 0/1
  payload_json TEXT NOT NULL DEFAULT '{}',  -- JSON-safe payload for run_hunt_now
  created_at_iso TEXT,
  last_run_at_iso TEXT,
  stopped_at_iso TEXT,
  booked_json TEXT,
  error TEXT
);
INSERT OR IGNORE INTO hunting_state(id, active, payload_json)
VALUES(1, 0, '{}');
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _now_iso(tz: ZoneInfo = TZ) -> str:
    return datetime.now(tz).isoformat()


# =========================
# Check-in scheduling + dispatch
# =========================

def schedule_checkin(
    *,
    checkin_date: str,     # "YYYY-MM-DD"
    checkin_start: str,    # "HH:MM"
    code: str,
    db_path: str | None = None,
    tz: ZoneInfo = TZ,
) -> int:
    """
    Schedules automatic check-in at (chosen date+time + 5 minutes).
    Returns the scheduled_checkins.id
    """
    code = code.strip()
    if not code:
        raise ValueError("Check-in code is empty")

    planned_dt = datetime.fromisoformat(f"{checkin_date}T{checkin_start}").replace(tzinfo=tz)
    run_at = planned_dt + timedelta(minutes=5)

    conn = init_db(db_path)
    try:
        _ensure_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO scheduled_checkins(run_at_iso, code, status, created_at_iso)
            VALUES(?, ?, 'pending', ?)
            """,
            (run_at.isoformat(), code, _now_iso(tz)),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def dispatch_due_checkins(
    *,
    run_checkin_now: Callable[[str], Any],
    db_path: str | None = None,
    tz: ZoneInfo = TZ,
    max_per_tick: int = 3,
) -> int:
    """
    Worker calls this every minute.
    Runs due pending checkins and marks status done/failed.
    Returns number processed in this tick.
    """
    conn = init_db(db_path)
    try:
        _ensure_schema(conn)
        now_iso = _now_iso(tz)

        rows = conn.execute(
            """
            SELECT id, code
            FROM scheduled_checkins
            WHERE status='pending' AND run_at_iso <= ?
            ORDER BY run_at_iso ASC
            LIMIT ?
            """,
            (now_iso, max_per_tick),
        ).fetchall()

        processed = 0

        for (cid, code) in rows:
            cid = int(cid)

            # Claim (avoid double execution if multiple workers ever exist)
            cur = conn.execute(
                """
                UPDATE scheduled_checkins
                SET status='running', started_at_iso=?
                WHERE id=? AND status='pending'
                """,
                (_now_iso(tz), cid),
            )
            conn.commit()
            if (cur.rowcount or 0) == 0:
                continue

            try:
                run_checkin_now(str(code))

                conn.execute(
                    """
                    UPDATE scheduled_checkins
                    SET status='done', finished_at_iso=?, error=NULL
                    WHERE id=?
                    """,
                    (_now_iso(tz), cid),
                )
                conn.commit()

            except Exception as e:
                conn.execute(
                    """
                    UPDATE scheduled_checkins
                    SET status='failed', finished_at_iso=?, error=?
                    WHERE id=?
                    """,
                    (_now_iso(tz), str(e)[:2000], cid),
                )
                conn.commit()

            processed += 1

        return processed
    finally:
        conn.close()


# =========================
# Hunting control + tick
# =========================

def start_hunting(
    *,
    payload: dict[str, Any],
    db_path: str | None = None,
    tz: ZoneInfo = TZ,
) -> None:
    """
    Turn hunting ON and store payload for run_hunt_now.

    Important: payload must be JSON-serializable.
    If payload includes datetime objects under keys 'start_dt'/'end_dt',
    we convert them to ISO strings as 'start_dt_iso'/'end_dt_iso'.
    """
    p = dict(payload)

    # Convert datetime objects to ISO strings if present
    start_dt = p.get("start_dt")
    end_dt = p.get("end_dt")
    if isinstance(start_dt, datetime):
        p["start_dt_iso"] = start_dt.astimezone(tz).isoformat()
        p.pop("start_dt", None)
    if isinstance(end_dt, datetime):
        p["end_dt_iso"] = end_dt.astimezone(tz).isoformat()
        p.pop("end_dt", None)

    # Validate presence
    if not p.get("start_dt_iso") or not p.get("end_dt_iso"):
        raise ValueError("Hunting payload must include start_dt/end_dt (datetime) or start_dt_iso/end_dt_iso (strings).")

    conn = init_db(db_path)
    try:
        _ensure_schema(conn)
        conn.execute(
            """
            UPDATE hunting_state
            SET active=1,
                payload_json=?,
                created_at_iso=?,
                last_run_at_iso=NULL,
                stopped_at_iso=NULL,
                booked_json=NULL,
                error=NULL
            WHERE id=1
            """,
            (json.dumps(p), _now_iso(tz)),
        )
        conn.commit()
    finally:
        conn.close()


def stop_hunting(
    *,
    reason: str | None = None,
    db_path: str | None = None,
    tz: ZoneInfo = TZ,
) -> None:
    conn = init_db(db_path)
    try:
        _ensure_schema(conn)
        conn.execute(
            """
            UPDATE hunting_state
            SET active=0,
                stopped_at_iso=?,
                error=?
            WHERE id=1
            """,
            (_now_iso(tz), reason),
        )
        conn.commit()
    finally:
        conn.close()


def active_hunting(
    *,
    run_hunt_now: Callable[..., dict[str, Any]],
    db_path: str | None = None,
    tz: ZoneInfo = TZ,
) -> dict[str, Any] | None:
    """
    One hunting 'tick'. Worker calls this every 30 minutes.

    If hunting is not active -> returns None
    If active -> calls run_hunt_now(...) with stored payload.
    If booking succeeds (result.get("booked")) -> hunting is automatically turned OFF.
    """
    conn = init_db(db_path)
    try:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT active, payload_json FROM hunting_state WHERE id=1"
        ).fetchone()

        if not row:
            return None

        active = int(row[0])
        if active != 1:
            return None

        payload = json.loads(row[1] or "{}")

        # Parse dt ISO back to datetime objects for your run_hunt_now signature
        start_iso = payload.get("start_dt_iso")
        end_iso = payload.get("end_dt_iso")
        if not start_iso or not end_iso:
            raise ValueError("Stored hunting payload missing start_dt_iso/end_dt_iso")

        start_dt = datetime.fromisoformat(start_iso)
        end_dt = datetime.fromisoformat(end_iso)

        now = datetime.now(tz)

        # Stop if current time is within 2 hours of end_dt
        if now >= end_dt.astimezone(tz) - timedelta(hours=2):
            conn.execute(
                """
                UPDATE hunting_state
                SET active=0,
                    stopped_at_iso=?,
                    error=?
                WHERE id=1
                """,
                (_now_iso(tz), "Stopped automatically: within 2 hours of end_time"),
            )
            conn.commit()
            return {
                "msg": "Stopped hunting automatically (within 2 hours of end_time).",
                "candidates": 0,
                "checked": 0,
                "found": None,
                "booked": None,
            }

        kwargs = dict(payload)
        kwargs.pop("start_dt_iso", None)
        kwargs.pop("end_dt_iso", None)
        kwargs["start_dt"] = start_dt
        kwargs["end_dt"] = end_dt

        try:
            result = run_hunt_now(**kwargs)

            conn.execute(
                "UPDATE hunting_state SET last_run_at_iso=? WHERE id=1",
                (_now_iso(tz),),
            )

            if result.get("booked"):
                conn.execute(
                    """
                    UPDATE hunting_state
                    SET active=0,
                        stopped_at_iso=?,
                        booked_json=?,
                        error=NULL
                    WHERE id=1
                    """,
                    (_now_iso(tz), json.dumps(result.get("booked"))),
                )

            conn.commit()
            return result

        except Exception as e:
            conn.execute(
                "UPDATE hunting_state SET error=? WHERE id=1",
                (str(e)[:2000],),
            )
            conn.commit()
            raise
    finally:
        conn.close()


def list_checkins(
    *,
    db_path: str | None = None,
    limit: int = 50,
    status: str | None = None,  # 'pending'|'running'|'done'|'failed'|'cancelled' or None
) -> list[dict[str, Any]]:
    conn = init_db(db_path)
    try:
        _ensure_schema(conn)
        if status is None:
            rows = conn.execute(
                """
                SELECT id, run_at_iso, status, created_at_iso, started_at_iso, finished_at_iso, error
                FROM scheduled_checkins
                ORDER BY run_at_iso ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, run_at_iso, status, created_at_iso, started_at_iso, finished_at_iso, error
                FROM scheduled_checkins
                WHERE status=?
                ORDER BY run_at_iso ASC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()

        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                dict(
                    id=int(r[0]),
                    run_at_iso=r[1],
                    status=r[2],
                    created_at_iso=r[3],
                    started_at_iso=r[4],
                    finished_at_iso=r[5],
                    error=r[6],
                )
            )
        return out
    finally:
        conn.close()


def cancel_checkin(
    *,
    checkin_id: int,
    db_path: str | None = None,
) -> bool:
    """
    Cancel only if still pending (safe).
    Returns True if cancelled.
    """
    conn = init_db(db_path)
    try:
        _ensure_schema(conn)
        cur = conn.execute(
            """
            UPDATE scheduled_checkins
            SET status='cancelled', finished_at_iso=?
            WHERE id=? AND status='pending'
            """,
            (_now_iso(TZ), int(checkin_id)),
        )
        conn.commit()
        return (cur.rowcount or 0) > 0
    finally:
        conn.close()


def get_hunting_status(*, db_path: str | None = None) -> dict[str, Any]:
    conn = init_db(db_path)
    try:
        _ensure_schema(conn)
        row = conn.execute(
            """
            SELECT active, payload_json, created_at_iso, last_run_at_iso, stopped_at_iso, booked_json, error
            FROM hunting_state
            WHERE id=1
            """
        ).fetchone()

        if not row:
            return {"active": False}

        active = bool(int(row[0]))
        payload_json = row[1] or "{}"
        booked_json = row[5]

        return {
            "active": active,
            "payload": json.loads(payload_json),
            "created_at_iso": row[2],
            "last_run_at_iso": row[3],
            "stopped_at_iso": row[4],
            "booked": json.loads(booked_json) if booked_json else None,
            "error": row[6],
        }
    finally:
        conn.close()
