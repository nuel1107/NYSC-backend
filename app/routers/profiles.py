"""
Profiles router
GET    /profiles/me
PATCH  /profiles/me
GET    /profiles/{user_id}    (admin/lgi — full; authenticated — public fields)
GET    /profiles              (admin/lgi — list all)
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import asyncpg

from app.core.deps import db, require_admin_or_lgi
from app.core.security import get_current_user_id

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    state_code: str | None = None
    phone: str | None = None
    batch: str | None = None
    stream: str | None = None
    cds_group: str | None = None
    avatar_url: str | None = None
    portal_number: str | None = None
    firm_company_name: str | None = None
    num_staff: int | None = None
    industry: str | None = None
    applicant_role: str | None = None
    csr_focus: str | None = None


@router.get("/me")
async def get_my_profile(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow("SELECT * FROM profiles WHERE id=$1", uid)
    if not row:
        raise HTTPException(404, "Profile not found")
    return dict(row)


@router.patch("/me")
async def update_my_profile(
    body: ProfileUpdate,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")

    set_clause = ", ".join(f"{k}=${i+2}" for i, k in enumerate(updates))
    values = list(updates.values())
    await conn.execute(
        f"UPDATE profiles SET {set_clause} WHERE id=$1",
        uid, *values,
    )
    row = await conn.fetchrow("SELECT * FROM profiles WHERE id=$1", uid)
    return dict(row)


@router.get("")
async def list_profiles(
    staff_uid: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        """SELECT p.*, u.email,
                  ARRAY_AGG(ur.role) FILTER (WHERE ur.status='approved') AS roles
           FROM profiles p
           JOIN users u ON u.id = p.id
           LEFT JOIN user_roles ur ON ur.user_id = p.id
           GROUP BY p.id, u.email
           ORDER BY p.created_at DESC"""
    )
    return [dict(r) for r in rows]


@router.get("/{user_id}")
async def get_profile(
    user_id: str,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    # Check if requester is admin/lgi
    staff = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role IN ('admin','lgi') AND status='approved'",
        uid,
    )
    if staff or uid == user_id:
        row = await conn.fetchrow("SELECT * FROM profiles WHERE id=$1", user_id)
    else:
        # Public-only fields (mirrors profiles_public view)
        row = await conn.fetchrow(
            "SELECT id, full_name, avatar_url, cds_group, state_code FROM profiles WHERE id=$1",
            user_id,
        )
    if not row:
        raise HTTPException(404, "Profile not found")
    return dict(row)
