"""
Auth router — replaces Supabase Auth.
POST /auth/signup
POST /auth/signin
POST /auth/refresh
POST /auth/forgot-password  (stub — wire up email sender)
POST /auth/reset-password
GET  /auth/me
POST /auth/signout
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
import asyncpg
import uuid

from app.core.database import get_conn
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    get_current_user_id,
)
from app.core.deps import db

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class SignUpBody(BaseModel):
    email: EmailStr
    password: str
    role: str = "corps_member"
    full_name: str = ""
    state_code: str | None = None
    phone: str | None = None
    portal_number: str | None = None
    firm_company_name: str | None = None
    num_staff: int | None = None
    industry: str | None = None
    applicant_role: str | None = None
    csr_focus: str | None = None


class SignInBody(BaseModel):
    email: EmailStr
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


class ForgotPasswordBody(BaseModel):
    email: EmailStr


class ResetPasswordBody(BaseModel):
    token: str
    new_password: str


VALID_ROLES = {"corps_member", "admin", "lgi", "media_editor", "corporate_firm"}
ROLE_ORDER  = ["lgi", "admin", "media_editor", "corporate_firm", "corps_member"]


def _determine_status(role: str, has_active_lgi: bool) -> str:
    if role == "corps_member":
        return "approved"
    if role == "lgi":
        return "pending" if has_active_lgi else "approved"
    return "pending"


async def _build_token_response(user_id: str, conn: asyncpg.Connection) -> dict:
    rows = await conn.fetch(
        "SELECT role, status FROM user_roles WHERE user_id=$1", user_id
    )
    roles = [{"role": r["role"], "status": r["status"]} for r in rows]
    profile = await conn.fetchrow(
        """SELECT id, full_name, state_code, phone, avatar_url,
                  portal_number, firm_company_name, cds_group
           FROM profiles WHERE id=$1""",
        user_id,
    )

    access  = create_access_token(user_id, {"roles": roles})
    refresh = create_refresh_token(user_id)

    return {
        "access_token":  access,
        "refresh_token": refresh,
        "token_type":    "bearer",
        "user": {
            "id":    user_id,
            "roles": roles,
            "profile": dict(profile) if profile else None,
        },
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/signup", status_code=201)
async def signup(body: SignUpBody, conn: asyncpg.Connection = Depends(db)):
    role = body.role if body.role in VALID_ROLES else "corps_member"

    # Check email uniqueness
    existing = await conn.fetchval("SELECT id FROM users WHERE email=$1", body.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # LGI singleton check
    has_active_lgi = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM user_roles WHERE role='lgi' AND status='approved')"
    )

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(body.password)

    async with conn.transaction():
        await conn.execute(
            "INSERT INTO users(id, email, password_hash) VALUES($1,$2,$3)",
            user_id, body.email, pw_hash,
        )
        # Profile
        full_name = body.full_name or body.email.split("@")[0]
        await conn.execute(
            """INSERT INTO profiles(id, full_name, state_code, phone,
                portal_number, firm_company_name, num_staff, industry,
                applicant_role, csr_focus)
               VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
            user_id, full_name, body.state_code, body.phone,
            body.portal_number, body.firm_company_name, body.num_staff,
            body.industry, body.applicant_role, body.csr_focus,
        )
        # Role
        role_status = _determine_status(role, bool(has_active_lgi))
        await conn.execute(
            "INSERT INTO user_roles(user_id, role, status) VALUES($1,$2,$3)",
            user_id, role, role_status,
        )

    return await _build_token_response(user_id, conn)


@router.post("/signin")
async def signin(body: SignInBody, conn: asyncpg.Connection = Depends(db)):
    row = await conn.fetchrow(
        "SELECT id, password_hash FROM users WHERE email=$1", body.email
    )
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return await _build_token_response(str(row["id"]), conn)


@router.post("/refresh")
async def refresh_token(body: RefreshBody, conn: asyncpg.Connection = Depends(db)):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    uid = payload["sub"]
    exists = await conn.fetchval("SELECT id FROM users WHERE id=$1", uid)
    if not exists:
        raise HTTPException(status_code=401, detail="User not found")

    return await _build_token_response(uid, conn)


@router.get("/me")
async def me(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    return await _build_token_response(uid, conn)


@router.post("/signout", status_code=204)
async def signout():
    # JWT is stateless — client discards tokens.
    # To add token revocation, store a denylist in Redis here.
    return


@router.post("/forgot-password", status_code=202)
async def forgot_password(body: ForgotPasswordBody, conn: asyncpg.Connection = Depends(db)):
    # TODO: generate a signed reset token, store in DB, and email it.
    # For now, return 202 to avoid user enumeration.
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password", status_code=200)
async def reset_password(body: ResetPasswordBody, conn: asyncpg.Connection = Depends(db)):
    # TODO: validate reset token from DB, update password
    raise HTTPException(status_code=501, detail="Email reset not yet configured")
