from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from .config import Settings
from .errors import CoworkerError


def validate_key(key: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9/_.-]{1,510}", key) or ".." in key.split("/"):
        raise ValueError("Invalid object key")
    return key


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str, max_bytes: int) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def download_url(self, key: str, filename: str, content_type: str) -> str | None: ...


class LocalObjectStore:
    """Development/tests only; production settings reject local storage."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key):
        path = (self.root / validate_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Object is outside storage root")
        return path

    def put(self, key, data, content_type):
        destination = self.path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, key, max_bytes):
        with self.path(key).open("rb") as handle:
            result = handle.read(max_bytes + 1)
        if len(result) > max_bytes:
            raise CoworkerError("file_too_large", "This file exceeds the processing limit.", 413)
        return result

    def delete(self, key):
        self.path(key).unlink(missing_ok=True)

    def download_url(self, key, filename, content_type):
        return None


class S3ObjectStore:
    def __init__(self, settings: Settings, client=None):
        import boto3
        from botocore.config import Config
        self.bucket = settings.storage_bucket
        self.client = client or boto3.client(
            "s3", endpoint_url=settings.storage_endpoint, region_name=settings.storage_region,
            config=Config(connect_timeout=5, read_timeout=20, retries={"max_attempts": 2}, signature_version="s3v4"),
        )

    def put(self, key, data, content_type):
        self.client.put_object(
            Bucket=self.bucket, Key=validate_key(key), Body=data, ContentType=content_type,
            Metadata={"sha256": hashlib.sha256(data).hexdigest()},
        )

    def get(self, key, max_bytes):
        response = self.client.get_object(Bucket=self.bucket, Key=validate_key(key))
        body = response["Body"]
        try:
            if response.get("ContentLength", 0) > max_bytes:
                raise CoworkerError("file_too_large", "This file exceeds the processing limit.", 413)
            result = body.read(max_bytes + 1)
            if len(result) > max_bytes:
                raise CoworkerError("file_too_large", "This file exceeds the processing limit.", 413)
            return result
        finally:
            body.close()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=validate_key(key))

    def download_url(self, key, filename, content_type):
        # Filename comes from our exporter, never from the request's query string.
        return self.client.generate_presigned_url("get_object", Params={
            "Bucket": self.bucket, "Key": validate_key(key),
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
            "ResponseContentType": content_type,
        }, ExpiresIn=60)


def make_storage(settings: Settings) -> ObjectStore:
    return LocalObjectStore(settings.local_storage_path) if settings.storage_backend == "local" else S3ObjectStore(settings)
