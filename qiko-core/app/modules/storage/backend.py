"""Storage backends. S3 in prod (no local filesystem state); an in-memory backend for dev/tests.
Both enforce tenant-scoped keys."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import get_settings
from app.modules.storage.keys import assert_tenant_scoped


class StorageBackend(Protocol):
    def put(self, tenant: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    def get(self, tenant: str, key: str) -> bytes: ...
    def delete(self, tenant: str, key: str) -> None: ...


@dataclass
class InMemoryStorage:
    _objects: dict[str, bytes] = field(default_factory=dict)

    def put(self, tenant: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        assert_tenant_scoped(tenant, key)
        self._objects[key] = data
        return key

    def get(self, tenant: str, key: str) -> bytes:
        assert_tenant_scoped(tenant, key)
        return self._objects[key]

    def delete(self, tenant: str, key: str) -> None:
        assert_tenant_scoped(tenant, key)
        self._objects.pop(key, None)


@dataclass
class S3Storage:
    bucket: str = ""
    region: str = ""

    def __post_init__(self) -> None:
        s = get_settings()
        self.region = self.region or s.aws_region

    def _client(self):  # pragma: no cover - requires AWS credentials/network
        import boto3

        return boto3.client("s3", region_name=self.region)

    def put(self, tenant: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:  # pragma: no cover - network
        assert_tenant_scoped(tenant, key)
        self._client().put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get(self, tenant: str, key: str) -> bytes:  # pragma: no cover - network
        assert_tenant_scoped(tenant, key)
        return self._client().get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, tenant: str, key: str) -> None:  # pragma: no cover - network
        assert_tenant_scoped(tenant, key)
        self._client().delete_object(Bucket=self.bucket, Key=key)

    def presigned_get_url(self, tenant: str, key: str, *, expires: int = 3600) -> str:  # pragma: no cover - needs creds
        assert_tenant_scoped(tenant, key)
        return self._client().generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires)
