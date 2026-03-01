"""Object storage — S3/GCS with local filesystem fallback.

Provides a unified interface for storing uploaded files, generated audio,
and exported documents. Uses S3 or GCS when configured, otherwise
stores files on the local filesystem.

Environment variables:
    PPKE_STORAGE_BACKEND — "s3", "gcs", or "local" (default: "local")
    AWS_S3_BUCKET — S3 bucket name
    AWS_S3_PREFIX — Key prefix (default: "ppke/")
    AWS_S3_REGION — AWS region (default: "us-east-1")
    AWS_ACCESS_KEY_ID — AWS credentials
    AWS_SECRET_ACCESS_KEY — AWS credentials
    GCS_BUCKET — GCS bucket name
    GCS_PREFIX — Key prefix (default: "ppke/")
    GOOGLE_APPLICATION_CREDENTIALS — Path to GCS service account JSON
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, BinaryIO

logger = logging.getLogger(__name__)


# ── Local Storage ──


class LocalStorage:
    """Stores files on the local filesystem (default)."""

    def __init__(self, base_path: Path | None = None):
        self.base_path = base_path or Path.home() / ".ppke" / "storage"
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info("Local storage at: %s", self.base_path)

    def put(self, key: str, data: bytes | BinaryIO, content_type: str = "") -> str:
        """Store data and return the key."""
        path = self.base_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            with open(path, "wb") as f:
                shutil.copyfileobj(data, f)
        return key

    def get(self, key: str) -> bytes | None:
        """Retrieve data by key."""
        path = self.base_path / key
        if path.exists():
            return path.read_bytes()
        return None

    def get_stream(self, key: str) -> BinaryIO | None:
        """Get a file-like object for streaming."""
        path = self.base_path / key
        if path.exists():
            return open(path, "rb")
        return None

    def delete(self, key: str) -> bool:
        """Delete a stored object."""
        path = self.base_path / key
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        return (self.base_path / key).exists()

    def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys with given prefix."""
        base = self.base_path / prefix if prefix else self.base_path
        if not base.exists():
            return []
        return [
            str(p.relative_to(self.base_path))
            for p in base.rglob("*")
            if p.is_file()
        ]

    def get_url(self, key: str) -> str:
        """Return a file:// URL for local storage."""
        return f"file://{self.base_path / key}"


# ── S3 Storage ──


class S3Storage:
    """AWS S3 object storage."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "ppke/",
        region: str = "us-east-1",
    ):
        import boto3
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._client = boto3.client("s3", region_name=region)
        # Verify bucket access
        self._client.head_bucket(Bucket=bucket)
        logger.info("S3 storage connected: bucket=%s, prefix=%s", bucket, prefix)

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def put(self, key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream") -> str:
        full_key = self._key(key)
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Key": full_key, "ContentType": content_type}
        if isinstance(data, bytes):
            kwargs["Body"] = data
        else:
            kwargs["Body"] = data
        self._client.put_object(**kwargs)
        return key

    def get(self, key: str) -> bytes | None:
        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=self._key(key))
            return resp["Body"].read()
        except self._client.exceptions.NoSuchKey:
            return None
        except Exception:
            return None

    def get_stream(self, key: str) -> BinaryIO | None:
        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=self._key(key))
            return resp["Body"]
        except Exception:
            return None

    def delete(self, key: str) -> bool:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except Exception:
            return False

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except Exception:
            return False

    def list_keys(self, prefix: str = "") -> list[str]:
        full_prefix = self._key(prefix)
        keys = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"][len(self.prefix):])
        return keys

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for temporary access."""
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._key(key)},
            ExpiresIn=expires_in,
        )


# ── GCS Storage ──


class GCSStorage:
    """Google Cloud Storage."""

    def __init__(self, bucket_name: str, prefix: str = "ppke/"):
        from google.cloud import storage as gcs
        self._client = gcs.Client()
        self._bucket = self._client.bucket(bucket_name)
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        # Verify bucket access
        self._bucket.reload()
        logger.info("GCS storage connected: bucket=%s, prefix=%s", bucket_name, prefix)

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def put(self, key: str, data: bytes | BinaryIO, content_type: str = "application/octet-stream") -> str:
        blob = self._bucket.blob(self._key(key))
        blob.content_type = content_type
        if isinstance(data, bytes):
            blob.upload_from_string(data, content_type=content_type)
        else:
            blob.upload_from_file(data, content_type=content_type)
        return key

    def get(self, key: str) -> bytes | None:
        blob = self._bucket.blob(self._key(key))
        if blob.exists():
            return blob.download_as_bytes()
        return None

    def get_stream(self, key: str) -> BinaryIO | None:
        import io
        data = self.get(key)
        if data:
            return io.BytesIO(data)
        return None

    def delete(self, key: str) -> bool:
        blob = self._bucket.blob(self._key(key))
        if blob.exists():
            blob.delete()
            return True
        return False

    def exists(self, key: str) -> bool:
        return self._bucket.blob(self._key(key)).exists()

    def list_keys(self, prefix: str = "") -> list[str]:
        full_prefix = self._key(prefix)
        blobs = self._client.list_blobs(self._bucket, prefix=full_prefix)
        return [blob.name[len(self.prefix):] for blob in blobs]

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a signed URL."""
        import datetime
        blob = self._bucket.blob(self._key(key))
        return blob.generate_signed_url(expiration=datetime.timedelta(seconds=expires_in))


# ── Singleton factory ──

_storage_instance: LocalStorage | S3Storage | GCSStorage | None = None


def get_storage() -> LocalStorage | S3Storage | GCSStorage:
    """Return the global storage instance."""
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    backend = os.environ.get("PPKE_STORAGE_BACKEND", "local").lower()

    if backend == "s3":
        bucket = os.environ.get("AWS_S3_BUCKET", "")
        if not bucket:
            logger.warning("AWS_S3_BUCKET not set, falling back to local storage")
        else:
            try:
                _storage_instance = S3Storage(
                    bucket=bucket,
                    prefix=os.environ.get("AWS_S3_PREFIX", "ppke/"),
                    region=os.environ.get("AWS_S3_REGION", "us-east-1"),
                )
                return _storage_instance
            except Exception as exc:
                logger.warning("S3 init failed (%s), falling back to local", exc)

    elif backend == "gcs":
        bucket = os.environ.get("GCS_BUCKET", "")
        if not bucket:
            logger.warning("GCS_BUCKET not set, falling back to local storage")
        else:
            try:
                _storage_instance = GCSStorage(
                    bucket_name=bucket,
                    prefix=os.environ.get("GCS_PREFIX", "ppke/"),
                )
                return _storage_instance
            except Exception as exc:
                logger.warning("GCS init failed (%s), falling back to local", exc)

    _storage_instance = LocalStorage()
    return _storage_instance
