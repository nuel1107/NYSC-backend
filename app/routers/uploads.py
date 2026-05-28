"""
File upload router (Cloudflare R2 / S3-compatible)
POST /uploads/presign    — get a presigned PUT URL (client uploads directly)
POST /uploads/confirm    — (optional) confirm upload and return public URL
"""
import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import get_current_user_id

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_BUCKETS = {
    "absence-attachments",
    "complaint-attachments",
    "firm-documents",
    "news-media",
    "community-media",
    "avatars",
}


class PresignRequest(BaseModel):
    bucket: str
    filename: str
    content_type: str


def _get_s3():
    s = get_settings()
    if not s.S3_ENDPOINT_URL:
        raise HTTPException(503, "File storage not configured")
    return boto3.client(
        "s3",
        endpoint_url=s.S3_ENDPOINT_URL,
        aws_access_key_id=s.S3_ACCESS_KEY_ID,
        aws_secret_access_key=s.S3_SECRET_ACCESS_KEY,
    )


@router.post("/presign")
async def presign_upload(
    body: PresignRequest,
    uid: str = Depends(get_current_user_id),
):
    if body.bucket not in ALLOWED_BUCKETS:
        raise HTTPException(400, "Invalid bucket")

    settings = get_settings()
    s3 = _get_s3()
    # Scope file under uid to prevent path traversal
    key = f"{uid}/{body.filename}"

    try:
        url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": body.bucket,
                "Key": key,
                "ContentType": body.content_type,
            },
            ExpiresIn=300,  # 5 minutes
        )
    except ClientError as e:
        raise HTTPException(500, str(e))

    public_url = f"{settings.S3_PUBLIC_BASE_URL}/{body.bucket}/{key}"
    return {"upload_url": url, "public_url": public_url, "key": key}
