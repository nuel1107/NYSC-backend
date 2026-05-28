"""
Device binding router
GET    /devices/me              — user's current active device
POST   /devices/reconcile       — register device on first login
POST   /devices/change-request  — request device change
GET    /devices/change-requests (admin/lgi)
PATCH  /devices/change-requests/{id}/approve
PATCH  /devices/change-requests/{id}/reject
DELETE /devices/{id}            (admin/lgi — revoke device)
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import asyncpg

from app.core.deps import db, require_admin_or_lgi
from app.core.security import get_current_user_id

router = APIRouter(prefix="/devices", tags=["devices"])


class ReconcileBody(BaseModel):
    fingerprint: str
    label: str | None = None


class ChangeRequestBody(BaseModel):
    new_fingerprint: str
    new_label: str | None = None
    reason: str
    path: str = "old_device"


class ReviewBody(BaseModel):
    status: str  # approved | rejected


@router.post("/reconcile")
async def reconcile_device(
    body: ReconcileBody,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    # LGI skips device binding
    is_lgi = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role='lgi' AND status='approved'", uid
    )
    if is_lgi:
        return {"state": "skipped"}

    active = await conn.fetchrow(
        "SELECT id, fingerprint FROM user_devices WHERE user_id=$1 AND is_active=true", uid
    )

    if not active:
        await conn.execute(
            "INSERT INTO user_devices(user_id, fingerprint, label, is_active) VALUES($1,$2,$3,true)",
            uid, body.fingerprint, body.label,
        )
        return {"state": "ok"}

    if active["fingerprint"] == body.fingerprint:
        # Touch last_seen
        await conn.execute(
            "UPDATE user_devices SET last_seen=now() WHERE id=$1", active["id"]
        )
        return {"state": "ok"}

    # Different device — locked
    return {"state": "locked", "activeFingerprint": active["fingerprint"]}


@router.get("/me")
async def my_device(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        "SELECT * FROM user_devices WHERE user_id=$1 AND is_active=true", uid
    )
    return dict(row) if row else None


@router.post("/change-request", status_code=201)
async def request_device_change(
    body: ChangeRequestBody,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        """INSERT INTO device_change_requests(user_id, new_fingerprint, new_label, reason, path)
           VALUES($1,$2,$3,$4,$5) RETURNING *""",
        uid, body.new_fingerprint, body.new_label, body.reason, body.path,
    )
    return dict(row)


@router.get("/change-requests")
async def list_change_requests(
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        """SELECT dcr.*, p.full_name FROM device_change_requests dcr
           JOIN profiles p ON p.id = dcr.user_id
           WHERE dcr.status='pending' ORDER BY dcr.created_at"""
    )
    return [dict(r) for r in rows]


@router.patch("/change-requests/{req_id}/approve")
async def approve_device_change(
    req_id: str,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    req = await conn.fetchrow(
        "SELECT * FROM device_change_requests WHERE id=$1", req_id
    )
    if not req:
        raise HTTPException(404, "Request not found")

    async with conn.transaction():
        # Deactivate old device
        await conn.execute(
            "UPDATE user_devices SET is_active=false WHERE user_id=$1 AND is_active=true",
            req["user_id"],
        )
        # Register new device
        await conn.execute(
            "INSERT INTO user_devices(user_id, fingerprint, label, is_active) VALUES($1,$2,$3,true)",
            req["user_id"], req["new_fingerprint"], req["new_label"],
        )
        # Mark request approved
        await conn.execute(
            "UPDATE device_change_requests SET status='approved', reviewed_by=$2, reviewed_at=now() WHERE id=$1",
            req_id, staff,
        )
    return {"message": "Device change approved"}


@router.patch("/change-requests/{req_id}/reject")
async def reject_device_change(
    req_id: str,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    await conn.execute(
        "UPDATE device_change_requests SET status='rejected', reviewed_by=$2, reviewed_at=now() WHERE id=$1",
        req_id, staff,
    )
    return {"message": "Request rejected"}
