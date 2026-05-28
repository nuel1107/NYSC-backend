"""
Roles router
GET    /roles/my-roles
POST   /roles/request        (request a new role — non-privileged)
GET    /roles/pending         (admin/lgi)
PATCH  /roles/{id}/approve   (admin/lgi)
PATCH  /roles/{id}/reject    (admin/lgi)
POST   /roles/lgi-assign     (lgi only)
DELETE /roles/lgi-remove     (lgi only)
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import asyncpg
import uuid

from app.core.deps import db, require_admin_or_lgi, require_lgi
from app.core.security import get_current_user_id

router = APIRouter(prefix="/roles", tags=["roles"])

NON_PRIVILEGED = {"corps_member", "media_editor", "corporate_firm"}
ALL_ROLES      = {"corps_member", "admin", "lgi", "media_editor", "corporate_firm"}


class RoleRequest(BaseModel):
    role: str


class AssignBody(BaseModel):
    user_id: str
    role: str
    status: str = "approved"


class RemoveBody(BaseModel):
    user_id: str
    role: str


@router.get("/my-roles")
async def my_roles(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        "SELECT id, role, status, created_at FROM user_roles WHERE user_id=$1", uid
    )
    return [dict(r) for r in rows]


@router.post("/request", status_code=201)
async def request_role(
    body: RoleRequest,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    if body.role not in NON_PRIVILEGED:
        raise HTTPException(403, "Cannot self-request privileged roles (admin/lgi)")

    exists = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role=$2", uid, body.role
    )
    if exists:
        raise HTTPException(409, "Role already assigned or pending")

    await conn.execute(
        "INSERT INTO user_roles(user_id, role, status) VALUES($1,$2,'pending')",
        uid, body.role,
    )
    return {"message": "Role request submitted"}


@router.get("/pending")
async def pending_roles(
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        """SELECT ur.*, p.full_name, u.email
           FROM user_roles ur
           JOIN profiles p ON p.id = ur.user_id
           JOIN users u ON u.id = ur.user_id
           WHERE ur.status = 'pending'
           ORDER BY ur.created_at"""
    )
    return [dict(r) for r in rows]


@router.patch("/{role_id}/approve")
async def approve_role(
    role_id: str,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow("SELECT * FROM user_roles WHERE id=$1", role_id)
    if not row:
        raise HTTPException(404, "Role not found")

    # Admins cannot approve lgi roles — only LGI can
    if row["role"] == "lgi":
        is_lgi = await conn.fetchval(
            "SELECT 1 FROM user_roles WHERE user_id=$1 AND role='lgi' AND status='approved'", staff
        )
        if not is_lgi:
            raise HTTPException(403, "Only LGI can approve LGI role")

    await conn.execute(
        "UPDATE user_roles SET status='approved' WHERE id=$1", role_id
    )
    return {"message": "Role approved"}


@router.patch("/{role_id}/reject")
async def reject_role(
    role_id: str,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    result = await conn.execute(
        "UPDATE user_roles SET status='rejected' WHERE id=$1", role_id
    )
    if result == "UPDATE 0":
        raise HTTPException(404, "Role not found")
    return {"message": "Role rejected"}


@router.post("/lgi-assign")
async def lgi_assign(
    body: AssignBody,
    lgi_uid: str = Depends(require_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    if body.role not in ALL_ROLES:
        raise HTTPException(400, "Invalid role")
    await conn.execute(
        """INSERT INTO user_roles(user_id, role, status) VALUES($1,$2,$3)
           ON CONFLICT (user_id, role) DO UPDATE SET status = EXCLUDED.status""",
        body.user_id, body.role, body.status,
    )
    return {"message": f"Role {body.role} set to {body.status}"}


@router.delete("/lgi-remove")
async def lgi_remove(
    body: RemoveBody,
    lgi_uid: str = Depends(require_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    await conn.execute(
        "DELETE FROM user_roles WHERE user_id=$1 AND role=$2", body.user_id, body.role
    )
    return {"message": "Role removed"}
