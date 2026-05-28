"""
Complaints
GET    /complaints       — own or all (admin/lgi)
POST   /complaints
PATCH  /complaints/{id}/review
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import asyncpg

from app.core.deps import db, require_admin_or_lgi
from app.core.security import get_current_user_id

router = APIRouter(prefix="/complaints", tags=["complaints"])


class ComplaintCreate(BaseModel):
    subject: str
    body: str
    attachment_url: str | None = None


class ComplaintReview(BaseModel):
    status: str   # approved | rejected
    reviewer_note: str | None = None


@router.get("")
async def list_complaints(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    is_staff = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role IN ('admin','lgi') AND status='approved'", uid
    )
    if is_staff:
        rows = await conn.fetch(
            "SELECT c.*, p.full_name FROM complaints c JOIN profiles p ON p.id=c.user_id ORDER BY c.created_at DESC"
        )
    else:
        rows = await conn.fetch(
            "SELECT * FROM complaints WHERE user_id=$1 ORDER BY created_at DESC", uid
        )
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_complaint(
    body: ComplaintCreate,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        "INSERT INTO complaints(user_id, subject, body, attachment_url) VALUES($1,$2,$3,$4) RETURNING *",
        uid, body.subject, body.body, body.attachment_url,
    )
    return dict(row)


@router.patch("/{complaint_id}/review")
async def review_complaint(
    complaint_id: str,
    body: ComplaintReview,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be approved or rejected")
    row = await conn.fetchrow(
        """UPDATE complaints SET status=$2, reviewer_note=$3, reviewed_by=$4
           WHERE id=$1 RETURNING *""",
        complaint_id, body.status, body.reviewer_note, staff,
    )
    if not row:
        raise HTTPException(404, "Complaint not found")
    return dict(row)
