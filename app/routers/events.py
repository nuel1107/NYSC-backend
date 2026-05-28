"""
Events + geofenced attendance router
GET    /events               (authenticated)
POST   /events               (admin/lgi)
PATCH  /events/{id}          (admin/lgi)
DELETE /events/{id}          (admin/lgi)
POST   /events/{id}/lock     (admin/lgi)
POST   /events/{id}/unlock   (admin/lgi)

GET    /events/{id}/attendance         (admin/lgi)
POST   /events/{id}/attendance/clock-in
PATCH  /events/{id}/attendance/clock-out
GET    /events/{id}/attendance/me
"""
import math
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime
import asyncpg

from app.core.deps import db, require_admin_or_lgi
from app.core.security import get_current_user_id

router = APIRouter(prefix="/events", tags=["events"])


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class EventBody(BaseModel):
    name: str
    description: str | None = None
    latitude: float
    longitude: float
    radius_m: int = 100
    starts_at: datetime
    ends_at: datetime


class ClockInBody(BaseModel):
    latitude: float
    longitude: float


class ClockOutBody(BaseModel):
    latitude: float
    longitude: float


@router.get("")
async def list_events(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        "SELECT * FROM events ORDER BY starts_at DESC LIMIT 100"
    )
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_event(
    body: EventBody,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        """INSERT INTO events(name, description, latitude, longitude, radius_m,
                              starts_at, ends_at, created_by)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *""",
        body.name, body.description, body.latitude, body.longitude,
        body.radius_m, body.starts_at, body.ends_at, staff,
    )
    return dict(row)


@router.patch("/{event_id}")
async def update_event(
    event_id: str,
    body: EventBody,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        """UPDATE events SET name=$2, description=$3, latitude=$4, longitude=$5,
                             radius_m=$6, starts_at=$7, ends_at=$8
           WHERE id=$1 RETURNING *""",
        event_id, body.name, body.description, body.latitude, body.longitude,
        body.radius_m, body.starts_at, body.ends_at,
    )
    if not row:
        raise HTTPException(404, "Event not found")
    return dict(row)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    await conn.execute("DELETE FROM events WHERE id=$1", event_id)


@router.post("/{event_id}/lock")
async def lock_event(
    event_id: str,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    event = await conn.fetchrow("SELECT * FROM events WHERE id=$1", event_id)
    if not event:
        raise HTTPException(404, "Event not found")

    # LGI lock cannot be overridden by admin
    is_lgi = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role='lgi' AND status='approved'", staff
    )
    if event["locked_by_role"] == "lgi" and not is_lgi:
        raise HTTPException(403, "Locked by LGI; only LGI can change this")

    locked_role = "lgi" if is_lgi else "admin"
    await conn.execute(
        "UPDATE events SET attendance_locked=true, locked_by_role=$2, locked_by=$3 WHERE id=$1",
        event_id, locked_role, staff,
    )
    return {"message": "Event locked"}


@router.post("/{event_id}/unlock")
async def unlock_event(
    event_id: str,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    event = await conn.fetchrow("SELECT * FROM events WHERE id=$1", event_id)
    if not event:
        raise HTTPException(404, "Event not found")

    is_lgi = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role='lgi' AND status='approved'", staff
    )
    if event["locked_by_role"] == "lgi" and not is_lgi:
        raise HTTPException(403, "Locked by LGI; only LGI can unlock")

    await conn.execute(
        "UPDATE events SET attendance_locked=false, locked_by_role=NULL, locked_by=NULL WHERE id=$1",
        event_id,
    )
    return {"message": "Event unlocked"}


# ── Attendance ────────────────────────────────────────────────────────────────

@router.get("/{event_id}/attendance")
async def get_attendance(
    event_id: str,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        """SELECT ea.*, p.full_name, p.state_code
           FROM event_attendance ea
           JOIN profiles p ON p.id = ea.user_id
           WHERE ea.event_id=$1 ORDER BY ea.clock_in_at""",
        event_id,
    )
    return [dict(r) for r in rows]


@router.get("/{event_id}/attendance/me")
async def my_attendance(
    event_id: str,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        "SELECT * FROM event_attendance WHERE event_id=$1 AND user_id=$2", event_id, uid
    )
    return dict(row) if row else None


@router.post("/{event_id}/attendance/clock-in", status_code=201)
async def clock_in(
    event_id: str,
    body: ClockInBody,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    event = await conn.fetchrow("SELECT * FROM events WHERE id=$1", event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    if event["attendance_locked"]:
        raise HTTPException(400, "Attendance is locked for this event")

    # Geofence check
    dist = haversine_m(body.latitude, body.longitude, event["latitude"], event["longitude"])
    if dist > event["radius_m"]:
        raise HTTPException(400, f"Outside event geofence ({round(dist)}m away, max {event['radius_m']}m)")

    row = await conn.fetchrow(
        """INSERT INTO event_attendance(event_id, user_id, clock_in_at, clock_in_lat, clock_in_lng)
           VALUES($1,$2,now(),$3,$4)
           ON CONFLICT (event_id, user_id) DO NOTHING
           RETURNING *""",
        event_id, uid, body.latitude, body.longitude,
    )
    if not row:
        raise HTTPException(409, "Already clocked in")
    return dict(row)


@router.patch("/{event_id}/attendance/clock-out")
async def clock_out(
    event_id: str,
    body: ClockOutBody,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    event = await conn.fetchrow("SELECT * FROM events WHERE id=$1", event_id)
    if not event:
        raise HTTPException(404, "Event not found")

    dist = haversine_m(body.latitude, body.longitude, event["latitude"], event["longitude"])
    if dist > event["radius_m"]:
        raise HTTPException(400, f"Outside event geofence ({round(dist)}m away, max {event['radius_m']}m)")

    row = await conn.fetchrow(
        """UPDATE event_attendance
           SET clock_out_at=now(), clock_out_lat=$3, clock_out_lng=$4
           WHERE event_id=$1 AND user_id=$2 AND clock_in_at IS NOT NULL
           RETURNING *""",
        event_id, uid, body.latitude, body.longitude,
    )
    if not row:
        raise HTTPException(400, "Must clock in first")
    return dict(row)
