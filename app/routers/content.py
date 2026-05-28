"""
News articles, community posts, notifications, impact metrics
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import asyncpg

from app.core.deps import db, require_admin_or_lgi, require_media
from app.core.security import get_current_user_id

# ── NEWS ─────────────────────────────────────────────────────────────────────

news_router = APIRouter(prefix="/news", tags=["news"])


class NewsCreate(BaseModel):
    title: str
    excerpt: str | None = None
    body: str
    cover_url: str | None = None
    published: bool = False


class NewsUpdate(BaseModel):
    title: str | None = None
    excerpt: str | None = None
    body: str | None = None
    cover_url: str | None = None
    published: bool | None = None


@news_router.get("")
async def list_news(
    published_only: bool = Query(True),
    uid: Optional[str] = None,
    conn: asyncpg.Connection = Depends(db),
):
    # Public endpoint — no auth required for published news
    if published_only:
        rows = await conn.fetch(
            "SELECT * FROM news_articles WHERE published=true ORDER BY created_at DESC"
        )
    else:
        rows = await conn.fetch("SELECT * FROM news_articles ORDER BY created_at DESC")
    return [dict(r) for r in rows]


@news_router.get("/{article_id}")
async def get_article(article_id: str, conn: asyncpg.Connection = Depends(db)):
    row = await conn.fetchrow(
        "SELECT * FROM news_articles WHERE id=$1 AND published=true", article_id
    )
    if not row:
        raise HTTPException(404, "Article not found")
    return dict(row)


@news_router.post("", status_code=201)
async def create_article(
    body: NewsCreate,
    staff: str = Depends(require_media),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        """INSERT INTO news_articles(title, excerpt, body, cover_url, published, author_id)
           VALUES($1,$2,$3,$4,$5,$6) RETURNING *""",
        body.title, body.excerpt, body.body, body.cover_url, body.published, staff,
    )
    return dict(row)


@news_router.patch("/{article_id}")
async def update_article(
    article_id: str,
    body: NewsUpdate,
    staff: str = Depends(require_media),
    conn: asyncpg.Connection = Depends(db),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields")
    set_clause = ", ".join(f"{k}=${i+2}" for i, k in enumerate(updates))
    row = await conn.fetchrow(
        f"UPDATE news_articles SET {set_clause} WHERE id=$1 RETURNING *",
        article_id, *updates.values(),
    )
    if not row:
        raise HTTPException(404, "Article not found")
    return dict(row)


@news_router.delete("/{article_id}", status_code=204)
async def delete_article(
    article_id: str,
    staff: str = Depends(require_media),
    conn: asyncpg.Connection = Depends(db),
):
    await conn.execute("DELETE FROM news_articles WHERE id=$1", article_id)


# ── COMMUNITY POSTS ───────────────────────────────────────────────────────────

community_router = APIRouter(prefix="/community", tags=["community"])


class PostCreate(BaseModel):
    content: str
    image_url: str | None = None


@community_router.get("")
async def list_posts(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        """SELECT cp.*, p.full_name, p.avatar_url
           FROM community_posts cp JOIN profiles p ON p.id=cp.user_id
           ORDER BY cp.created_at DESC LIMIT 50"""
    )
    return [dict(r) for r in rows]


@community_router.post("", status_code=201)
async def create_post(
    body: PostCreate,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        "INSERT INTO community_posts(user_id, content, image_url) VALUES($1,$2,$3) RETURNING *",
        uid, body.content, body.image_url,
    )
    return dict(row)


@community_router.delete("/{post_id}", status_code=204)
async def delete_post(
    post_id: str,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow("SELECT user_id FROM community_posts WHERE id=$1", post_id)
    if not row:
        raise HTTPException(404, "Post not found")
    is_staff = await conn.fetchval(
        "SELECT 1 FROM user_roles WHERE user_id=$1 AND role IN ('admin','lgi') AND status='approved'", uid
    )
    if str(row["user_id"]) != uid and not is_staff:
        raise HTTPException(403, "Not your post")
    await conn.execute("DELETE FROM community_posts WHERE id=$1", post_id)


# ── NOTIFICATIONS ─────────────────────────────────────────────────────────────

notif_router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotifCreate(BaseModel):
    title: str
    body: str
    target_user_id: str | None = None
    is_global: bool = False


@notif_router.get("")
async def list_notifications(
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    rows = await conn.fetch(
        """SELECT n.*,
             EXISTS(SELECT 1 FROM notification_reads nr WHERE nr.notification_id=n.id AND nr.user_id=$1) AS is_read
           FROM notifications n
           WHERE n.is_global=true OR n.target_user_id=$1
           ORDER BY n.created_at DESC""",
        uid,
    )
    return [dict(r) for r in rows]


@notif_router.post("", status_code=201)
async def create_notification(
    body: NotifCreate,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        """INSERT INTO notifications(title, body, target_user_id, is_global, created_by)
           VALUES($1,$2,$3,$4,$5) RETURNING *""",
        body.title, body.body, body.target_user_id, body.is_global, staff,
    )
    return dict(row)


@notif_router.post("/{notif_id}/read", status_code=204)
async def mark_read(
    notif_id: str,
    uid: str = Depends(get_current_user_id),
    conn: asyncpg.Connection = Depends(db),
):
    await conn.execute(
        "INSERT INTO notification_reads(notification_id, user_id) VALUES($1,$2) ON CONFLICT DO NOTHING",
        notif_id, uid,
    )


# ── IMPACT METRICS ────────────────────────────────────────────────────────────

metrics_router = APIRouter(prefix="/metrics", tags=["metrics"])


class MetricUpdate(BaseModel):
    value: float


@metrics_router.get("")
async def list_metrics(conn: asyncpg.Connection = Depends(db)):
    rows = await conn.fetch("SELECT * FROM impact_metrics ORDER BY display_order")
    return [dict(r) for r in rows]


@metrics_router.patch("/{metric_id}")
async def update_metric(
    metric_id: str,
    body: MetricUpdate,
    staff: str = Depends(require_admin_or_lgi),
    conn: asyncpg.Connection = Depends(db),
):
    row = await conn.fetchrow(
        "UPDATE impact_metrics SET value=$2 WHERE id=$1 RETURNING *",
        metric_id, body.value,
    )
    if not row:
        raise HTTPException(404, "Metric not found")
    # Log change
    await conn.execute(
        "INSERT INTO impact_metric_changes(metric_id, changed_by, old_value, new_value) VALUES($1,$2,$3,$4)",
        metric_id, staff, row["value"], body.value,
    )
    return dict(row)
