"""
Corporate firms + job postings
GET    /firms/me               — own firm
POST   /firms                  — create firm
PATCH  /firms/{id}/review      — admin/lgi
GET    /firms/{id}/documents
POST   /firms/{id}/documents

GET    /jobs                   — active jobs (authenticated)
POST   /jobs                   — create (firm owner, approved)
PATCH  /jobs/{id}
DELETE /jobs/{id}
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
import asyncpg

from app.core.deps import db, require_admin_or_lgi
from app.core.security import get_current_user_id

firms_router = APIRouter(prefix="/firms", tags=["firms"])
jobs_router  = APIRouter(prefix="/jobs",  tags=["jobs"])


class FirmCreate(BaseModel):
    company_name: str
    email: EmailStr
    phone: str | None = None
    num_staff: int | None = None
    industry: str | None = None
    applicant_role: str | None = None
    csr_focus: str | None = None


class FirmReview(BaseModel):
    status: str  # approved | rejected


class DocumentCreate(BaseModel):
    doc_name: str
    url: str


class JobCreate(BaseModel):
    title: str
    description: str
    job_type: str = "full_time"
    location: str | None = None


class JobUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    job_type: str | None = None
    location: str | None = None
    is_active: bool | None = None


@firms_router.get("/me")
async def my_firm(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow("SELECT * FROM corporate_firms WHERE owner_id=$1", uid)
    return dict(row) if row else None


@firms_router.post("", status_code=201)
async def create_firm(
    body: FirmCreate,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    exists = await conn.fetchval("SELECT 1 FROM corporate_firms WHERE owner_id=$1", uid)
    if exists:
        raise HTTPException(409, "Firm already registered for this account")
    row = await conn.fetchrow(
        """INSERT INTO corporate_firms(owner_id, company_name, email, phone, num_staff,
                                       industry, applicant_role, csr_focus)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *""",
        uid, body.company_name, body.email, body.phone, body.num_staff,
        body.industry, body.applicant_role, body.csr_focus,
    )
    return dict(row)


@firms_router.get("")
async def list_firms(
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch("SELECT * FROM corporate_firms ORDER BY created_at DESC")
    return [dict(r) for r in rows]


@firms_router.patch("/{firm_id}/review")
async def review_firm(
    firm_id: str,
    body: FirmReview,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be approved or rejected")
    row = await conn.fetchrow(
        "UPDATE corporate_firms SET status=$2, reviewed_by=$3 WHERE id=$1 RETURNING *",
        firm_id, body.status, staff,
    )
    if not row:
        raise HTTPException(404, "Firm not found")
    return dict(row)


@firms_router.get("/{firm_id}/documents")
async def list_documents(
    firm_id: str,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    firm = await conn.fetchrow("SELECT owner_id FROM corporate_firms WHERE id=$1", firm_id)
    if not firm:
        raise HTTPException(404, "Firm not found")
    is_staff = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role IN ('admin','lgi') AND status='approved'", uid
    )
    if str(firm["owner_id"]) != uid and not is_staff:
        raise HTTPException(403, "Forbidden")
    rows = await conn.fetch("SELECT * FROM firm_documents WHERE firm_id=$1", firm_id)
    return [dict(r) for r in rows]


@firms_router.post("/{firm_id}/documents", status_code=201)
async def add_document(
    firm_id: str,
    body: DocumentCreate,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    firm = await conn.fetchrow("SELECT owner_id FROM corporate_firms WHERE id=$1", firm_id)
    if not firm or str(firm["owner_id"]) != uid:
        raise HTTPException(403, "Not your firm")
    row = await conn.fetchrow(
        "INSERT INTO firm_documents(firm_id, doc_name, url) VALUES($1,$2,$3) RETURNING *",
        firm_id, body.doc_name, body.url,
    )
    return dict(row)


# ── Jobs ──────────────────────────────────────────────────────────────────────

@jobs_router.get("")
async def list_jobs(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        """SELECT jp.*, cf.company_name FROM job_postings jp
           JOIN corporate_firms cf ON cf.id = jp.firm_id
           WHERE jp.is_active=true ORDER BY jp.created_at DESC"""
    )
    return [dict(r) for r in rows]


@jobs_router.post("", status_code=201)
async def create_job(
    body: JobCreate,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    firm = await conn.fetchrow(
        "SELECT id, status FROM corporate_firms WHERE owner_id=$1", uid
    )
    if not firm:
        raise HTTPException(403, "No registered firm")
    if firm["status"] != "approved":
        raise HTTPException(403, "Firm not yet approved")
    row = await conn.fetchrow(
        """INSERT INTO job_postings(firm_id, title, description, job_type, location)
           VALUES($1,$2,$3,$4,$5) RETURNING *""",
        firm["id"], body.title, body.description, body.job_type, body.location,
    )
    return dict(row)


@jobs_router.patch("/{job_id}")
async def update_job(
    job_id: str,
    body: JobUpdate,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    job = await conn.fetchrow(
        "SELECT jp.*, cf.owner_id FROM job_postings jp JOIN corporate_firms cf ON cf.id=jp.firm_id WHERE jp.id=$1",
        job_id,
    )
    if not job:
        raise HTTPException(404, "Job not found")
    is_staff = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role IN ('admin','lgi') AND status='approved'", uid
    )
    if str(job["owner_id"]) != uid and not is_staff:
        raise HTTPException(403, "Forbidden")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields")
    set_clause = ", ".join(f"{k}=${i+2}" for i, k in enumerate(updates))
    row = await conn.fetchrow(
        f"UPDATE job_postings SET {set_clause} WHERE id=$1 RETURNING *",
        job_id, *updates.values(),
    )
    return dict(row)


@jobs_router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: str,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    job = await conn.fetchrow(
        "SELECT jp.id, cf.owner_id FROM job_postings jp JOIN corporate_firms cf ON cf.id=jp.firm_id WHERE jp.id=$1",
        job_id,
    )
    if not job:
        raise HTTPException(404, "Job not found")
    is_staff = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role IN ('admin','lgi') AND status='approved'", uid
    )
    if str(job["owner_id"]) != uid and not is_staff:
        raise HTTPException(403, "Forbidden")
    await conn.execute("DELETE FROM job_postings WHERE id=$1", job_id)
