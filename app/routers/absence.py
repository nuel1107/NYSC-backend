"""
Absence requests
GET    /absence              — own (corps) or all (admin/lgi)
POST   /absence              — create
PATCH  /absence/{id}/review  — admin/lgi
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import date
import asyncpg

from app.core.deps import db, require_admin_or_lgi
from app.core.security import get_current_user_id

router = APIRouter(prefix="/absence", tags=["absence"])


class AbsenceCreate(BaseModel):
    reason: str
    start_date: date
    end_date: date
    attachment_url: str | None = None


class AbsenceReview(BaseModel):
    status: str   # approved | rejected
    reviewer_note: str | None = None


@router.get("")
async def list_absence(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    is_staff = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role IN ('admin','lgi') AND status='approved'", uid
    )
    if is_staff:
        rows = await conn.fetch(
            """SELECT ar.*, p.full_name FROM absence_requests ar
               JOIN profiles p ON p.id = ar.user_id
               ORDER BY ar.created_at DESC"""
        )
    else:
        rows = await conn.fetch(
            "SELECT * FROM absence_requests WHERE user_id=$1 ORDER BY created_at DESC", uid
        )
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_absence(
    body: AbsenceCreate,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        """INSERT INTO absence_requests(user_id, reason, start_date, end_date, attachment_url)
           VALUES($1,$2,$3,$4,$5) RETURNING *""",
        uid, body.reason, body.start_date, body.end_date, body.attachment_url,
    )
    return dict(row)


@router.patch("/{request_id}/review")
async def review_absence(
    request_id: str,
    body: AbsenceReview,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be approved or rejected")
    row = await conn.fetchrow(
        """UPDATE absence_requests SET status=$2, reviewer_note=$3, reviewed_by=$4
           WHERE id=$1 RETURNING *""",
        request_id, body.status, body.reviewer_note, staff,
    )
    if not row:
        raise HTTPException(404, "Request not found")
    return dict(row)
