"""
Shared FastAPI dependencies: current user, role guards, DB connection.
"""
from fastapi import Depends, HTTPException, status
import asyncpg
from app.core.database import get_conn
from app.core.security import get_current_user_id
from contextlib import asynccontextmanager


# ── DB connection as a dependency ────────────────────────────────────────────
async def db() -> asyncpg.Connection:
    async with get_conn() as conn:
        yield conn


# ── Current user ID (UUID string) ────────────────────────────────────────────
CurrentUID = Depends(get_current_user_id)


# ── Role helper ──────────────────────────────────────────────────────────────
async def _get_approved_roles(uid: str, conn: asyncpg.Connection) -> list[str]:
    rows = await conn.fetch(
        "SELECT role FROM user_roles WHERE user_id=$1 AND status='approved'", uid
    )
    return [r["role"] for r in rows]


def require_roles(*allowed_roles: str):
    """
    Returns a dependency that raises 403 if the current user lacks one of
    the allowed roles.
    """
    async def guard(
        uid: str = Depends(get_current_user_id),
        conn: asyncpg.Connection = Depends(db),
    ) -> str:
        roles = await _get_approved_roles(uid, conn)
        if not any(r in roles for r in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {allowed_roles}",
            )
        return uid
    return guard


# Convenience guards
require_admin_or_lgi = require_roles("admin", "lgi")
require_lgi          = require_roles("lgi")
require_media        = require_roles("admin", "lgi", "media_editor")
