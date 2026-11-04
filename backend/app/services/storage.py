
"""التعامل مع تخزين الملفات باستخدام MinIO عبر S3."""

import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings


log = logging.getLogger(__name__)

_s3 = None


def _client():
    """إنشاء S3 client وإعادة استخدامه."""

    global _s3

    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            endpoint_url=settings.MINIO_ENDPOINT,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            region_name="us-east-1",
        )

    return _s3


def ensure_bucket():
    """التأكد من وجود Bucket وإنشاؤه عند عدم وجوده."""

    client = _client()

    try:
        client.head_bucket(Bucket=settings.MINIO_BUCKET)
        log.info("MinIO bucket is ready: %s", settings.MINIO_BUCKET)

    except ClientError as exc:
        error = exc.response.get("Error", {})
        code = str(error.get("Code", ""))
        status = exc.response.get("ResponseMetadata", {}).get(
            "HTTPStatusCode"
        )

        if code not in ("404", "NoSuchBucket", "NotFound") and status != 404:
            log.exception("Could not access MinIO bucket")
            raise

        try:
            client.create_bucket(Bucket=settings.MINIO_BUCKET)
            log.info("MinIO bucket created: %s", settings.MINIO_BUCKET)

        except ClientError as create_error:
            create_code = create_error.response.get(
                "Error", {}
            ).get("Code")

            if create_code not in (
                "BucketAlreadyOwnedByYou",
                "BucketAlreadyExists",
            ):
                raise


def put(
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
):
    """رفع ملف إلى MinIO."""

    if not key:
        raise ValueError("مفتاح التخزين غير صالح")

    if not isinstance(data, bytes) or not data:
        raise ValueError("محتوى الملف غير صالح أو فارغ")

    _client().put_object(
        Bucket=settings.MINIO_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def get(key: str) -> bytes:
    """تنزيل ملف من MinIO وإرجاع محتواه."""

    if not key:
        raise ValueError("مفتاح التخزين غير صالح")

    response = _client().get_object(
        Bucket=settings.MINIO_BUCKET,
        Key=key,
    )

    body = response["Body"]

    try:
        return body.read()
    finally:
        body.close()


def delete(key: str):
    """حذف ملف من MinIO."""

    if not key:
        raise ValueError("مفتاح التخزين غير صالح")

    _client().delete_object(
        Bucket=settings.MINIO_BUCKET,
        Key=key,
    )