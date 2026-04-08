"""
Cloudflare R2 client (S3-compatible).

- Stream upload: downloads from CDN URL → streams directly to R2, never buffers full video in memory
- Pre-signed URLs: generated fresh per request (24h expiry), never stored in DB
- Key naming: users/{user_id}/competitors/{handle}/{ad_library_id}.mp4
"""

import logging
from typing import Optional

import boto3
import httpx
from botocore.exceptions import ClientError

from config import settings

logger = logging.getLogger(__name__)

MAX_VIDEO_BYTES = settings.MAX_VIDEO_SIZE_MB * 1024 * 1024
PRESIGNED_URL_EXPIRY = 86400  # 24 hours


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def build_r2_key(user_id: str, handle: str, ad_library_id: str, extension: str = "mp4") -> str:
    return f"users/{user_id}/competitors/{handle}/{ad_library_id}.{extension}"


async def stream_upload(cdn_url: str, r2_key: str) -> int:
    """
    Stream a video from cdn_url directly to R2 via multipart upload.
    Never buffers the full file in memory.
    Returns the number of bytes uploaded.

    Raises ValueError if the file exceeds MAX_VIDEO_SIZE_MB.
    Raises RuntimeError on upload failure.
    """
    s3 = _s3_client()

    mpu = s3.create_multipart_upload(Bucket=settings.R2_BUCKET_NAME, Key=r2_key)
    upload_id = mpu["UploadId"]
    parts = []
    part_number = 1
    total_bytes = 0
    chunk_size = 8 * 1024 * 1024  # 8MB chunks

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("GET", cdn_url) as response:
                response.raise_for_status()
                buffer = b""

                async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                    buffer += chunk
                    total_bytes += len(chunk)

                    if total_bytes > MAX_VIDEO_BYTES:
                        raise ValueError(
                            f"Video exceeds {settings.MAX_VIDEO_SIZE_MB}MB limit "
                            f"({total_bytes / 1024 / 1024:.1f}MB so far)"
                        )

                    if len(buffer) >= chunk_size:
                        part = s3.upload_part(
                            Bucket=settings.R2_BUCKET_NAME,
                            Key=r2_key,
                            UploadId=upload_id,
                            PartNumber=part_number,
                            Body=buffer,
                        )
                        parts.append({"PartNumber": part_number, "ETag": part["ETag"]})
                        part_number += 1
                        buffer = b""

                # Upload final chunk
                if buffer:
                    part = s3.upload_part(
                        Bucket=settings.R2_BUCKET_NAME,
                        Key=r2_key,
                        UploadId=upload_id,
                        PartNumber=part_number,
                        Body=buffer,
                    )
                    parts.append({"PartNumber": part_number, "ETag": part["ETag"]})

        s3.complete_multipart_upload(
            Bucket=settings.R2_BUCKET_NAME,
            Key=r2_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
        logger.info("R2 upload complete: %s (%d bytes)", r2_key, total_bytes)
        return total_bytes

    except Exception as e:
        # Always abort the multipart upload to avoid storage charges for incomplete uploads
        try:
            s3.abort_multipart_upload(
                Bucket=settings.R2_BUCKET_NAME,
                Key=r2_key,
                UploadId=upload_id,
            )
        except ClientError:
            pass
        raise RuntimeError(f"R2 upload failed for {r2_key}: {e}") from e


def generate_presigned_url(r2_key: str, expiry: int = PRESIGNED_URL_EXPIRY) -> str:
    """
    Generate a pre-signed GET URL for a stored object.
    Called fresh on every frontend request — never stored in DB.
    """
    s3 = _s3_client()
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.R2_BUCKET_NAME, "Key": r2_key},
            ExpiresIn=expiry,
        )
        return url
    except ClientError as e:
        raise RuntimeError(f"Failed to generate pre-signed URL for {r2_key}: {e}") from e


def get_object_bytes(r2_key: str) -> bytes:
    """
    Download an object from R2 into memory.
    Used for vision frame extraction (videos are small enough after ffmpeg extraction).
    """
    s3 = _s3_client()
    try:
        response = s3.get_object(Bucket=settings.R2_BUCKET_NAME, Key=r2_key)
        return response["Body"].read()
    except ClientError as e:
        raise RuntimeError(f"Failed to download {r2_key} from R2: {e}") from e


def delete_object(r2_key: str) -> None:
    """Hard delete an object from R2. Used for cleanup only."""
    s3 = _s3_client()
    try:
        s3.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=r2_key)
        logger.info("R2 deleted: %s", r2_key)
    except ClientError as e:
        logger.warning("R2 delete failed for %s: %s", r2_key, e)


def object_exists(r2_key: str) -> bool:
    """Check if an object exists in R2 without downloading it."""
    s3 = _s3_client()
    try:
        s3.head_object(Bucket=settings.R2_BUCKET_NAME, Key=r2_key)
        return True
    except ClientError:
        return False
