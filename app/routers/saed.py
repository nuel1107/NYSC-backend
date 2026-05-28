"""
SAED module: skills, courses, tutor applications, clubs, memberships, CDS rankings
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import asyncpg

from app.core.deps import db, require_admin_or_lgi
from app.core.security import get_current_user_id

router = APIRouter(prefix="/saed", tags=["saed"])


# ── Skills ────────────────────────────────────────────────────────────────────

class SkillCreate(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None


@router.get("/skills")
async def list_skills(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch("SELECT * FROM skills WHERE is_active=true ORDER BY name")
    return [dict(r) for r in rows]


@router.post("/skills", status_code=201)
async def create_skill(
    body: SkillCreate,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        "INSERT INTO skills(name, description, category) VALUES($1,$2,$3) RETURNING *",
        body.name, body.description, body.category,
    )
    return dict(row)


# ── Courses ───────────────────────────────────────────────────────────────────

class CourseCreate(BaseModel):
    skill_id: str | None = None
    title: str
    body: str | None = None
    resource_url: str | None = None


@router.get("/courses")
async def list_courses(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        """SELECT c.*, s.name AS skill_name FROM courses c
           LEFT JOIN skills s ON s.id=c.skill_id ORDER BY c.created_at DESC"""
    )
    return [dict(r) for r in rows]


@router.post("/courses", status_code=201)
async def create_course(
    body: CourseCreate,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        "INSERT INTO courses(skill_id, title, body, resource_url, created_by) VALUES($1,$2,$3,$4,$5) RETURNING *",
        body.skill_id, body.title, body.body, body.resource_url, staff,
    )
    return dict(row)


# ── Tutor Applications ────────────────────────────────────────────────────────

class TutorApply(BaseModel):
    skill_id: str
    pitch: str


@router.get("/tutor-applications")
async def list_tutor_apps(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    is_staff = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role IN ('admin','lgi') AND status='approved'", uid
    )
    if is_staff:
        rows = await conn.fetch(
            "SELECT ta.*, p.full_name FROM tutor_applications ta JOIN profiles p ON p.id=ta.user_id ORDER BY ta.created_at DESC"
        )
    else:
        rows = await conn.fetch(
            "SELECT * FROM tutor_applications WHERE user_id=$1", uid
        )
    return [dict(r) for r in rows]


@router.post("/tutor-applications", status_code=201)
async def apply_tutor(
    body: TutorApply,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    try:
        row = await conn.fetchrow(
            "INSERT INTO tutor_applications(user_id, skill_id, pitch) VALUES($1,$2,$3) RETURNING *",
            uid, body.skill_id, body.pitch,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "Already applied for this skill")
    return dict(row)


@router.patch("/tutor-applications/{app_id}/review")
async def review_tutor(
    app_id: str,
    status: str,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    if status not in ("approved", "rejected"):
        raise HTTPException(400, "Invalid status")
    row = await conn.fetchrow(
        "UPDATE tutor_applications SET status=$2, reviewed_by=$3 WHERE id=$1 RETURNING *",
        app_id, status, staff,
    )
    if not row:
        raise HTTPException(404, "Application not found")
    return dict(row)


# ── Clubs ─────────────────────────────────────────────────────────────────────

class ClubCreate(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    cover_url: str | None = None


@router.get("/clubs")
async def list_clubs(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch("SELECT * FROM clubs WHERE is_active=true ORDER BY name")
    return [dict(r) for r in rows]


@router.post("/clubs", status_code=201)
async def create_club(
    body: ClubCreate,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        "INSERT INTO clubs(name, description, category, cover_url) VALUES($1,$2,$3,$4) RETURNING *",
        body.name, body.description, body.category, body.cover_url,
    )
    return dict(row)


@router.post("/clubs/{club_id}/join", status_code=201)
async def join_club(
    club_id: str,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    try:
        row = await conn.fetchrow(
            "INSERT INTO club_memberships(club_id, user_id) VALUES($1,$2) RETURNING *",
            club_id, uid,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "Already a member")
    return dict(row)


@router.delete("/clubs/{club_id}/leave", status_code=204)
async def leave_club(
    club_id: str,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    await conn.execute(
        "DELETE FROM club_memberships WHERE club_id=$1 AND user_id=$2", club_id, uid
    )


@router.patch("/clubs/memberships/{membership_id}/approve")
async def approve_membership(
    membership_id: str,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        "UPDATE club_memberships SET status='approved' WHERE id=$1 RETURNING *", membership_id
    )
    if not row:
        raise HTTPException(404, "Membership not found")
    return dict(row)


# ── CDS Rankings ──────────────────────────────────────────────────────────────

class RankingCreate(BaseModel):
    period_year: int
    period_month: int
    rank: int
    cds_group: str
    notes: str | None = None
    benefits: str | None = None


@router.get("/cds-rankings")
async def list_rankings(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        "SELECT * FROM cds_rankings ORDER BY period_year DESC, period_month DESC, rank ASC"
    )
    return [dict(r) for r in rows]


@router.post("/cds-rankings", status_code=201)
async def create_ranking(
    body: RankingCreate,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    try:
        row = await conn.fetchrow(
            """INSERT INTO cds_rankings(period_year, period_month, rank, cds_group, notes, benefits, updated_by)
               VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING *""",
            body.period_year, body.period_month, body.rank,
            body.cds_group, body.notes, body.benefits, staff,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "Ranking already exists for this period/rank")
    return dict(row)
