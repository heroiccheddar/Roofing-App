"""S3 photo storage service for pin photos."""

import logging

import boto3
from botocore.exceptions import ClientError  # noqa: F401 — re-exported for callers

from app.config import settings

logger = logging.getLogger(__name__)


def get_s3_client():
    """Create S3 client using AWS credentials from config.

    In production (Fly.io), credentials are auto-discovered from the IAM role.
    For local dev, set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env.
    """
    kwargs = {"region_name": settings.S3_PHOTO_REGION}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client("s3", **kwargs)


def photo_url(s3_key: str) -> str:
    """Generate a presigned URL for the photo (valid for 1 hour).

    No public bucket policy needed — the presigned URL grants temporary
    read access using the server's AWS credentials.
    """
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_PHOTO_BUCKET, "Key": s3_key},
        ExpiresIn=3600,
    )


def upload_photo(file_bytes: bytes, s3_key: str, content_type: str) -> None:
    """Upload photo bytes to S3.

    Public read access is granted via a bucket policy — no ACL header needed.
    """
    client = get_s3_client()
    client.put_object(
        Bucket=settings.S3_PHOTO_BUCKET,
        Key=s3_key,
        Body=file_bytes,
        ContentType=content_type,
    )


def delete_photo(s3_key: str) -> None:
    """Delete a single photo from S3."""
    client = get_s3_client()
    client.delete_object(Bucket=settings.S3_PHOTO_BUCKET, Key=s3_key)


def delete_photos_batch(s3_keys: list[str]) -> None:
    """Delete multiple photos from S3 in a single request.

    No-ops silently when the key list is empty so callers do not need to guard.
    """
    if not s3_keys:
        return
    client = get_s3_client()
    objects = [{"Key": key} for key in s3_keys]
    client.delete_objects(
        Bucket=settings.S3_PHOTO_BUCKET,
        Delete={"Objects": objects},
    )
