"""Object storage behind a small interface so tests never need S3."""

from typing import Any, Protocol

STORABLE_LICENSES = frozenset({"CC-BY-SA-4.0", "own"})


class ObjectStorage(Protocol):
    """Minimal operations the API and the pipeline need."""

    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def presigned_url(self, key: str, expires_s: int = 900) -> str: ...


class InMemoryStorage:
    """Deterministic storage for tests and offline development."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def presigned_url(self, key: str, expires_s: int = 900) -> str:
        return f"memory://{key}?expires={expires_s}"


class S3Storage:
    """S3/MinIO storage; URLs are signed against the endpoint that clients can reach."""

    def __init__(self, endpoint: str, public_endpoint: str, bucket: str, access_key: str, secret_key: str) -> None:
        import boto3
        from botocore.config import Config

        def client(url: str) -> Any:
            return boto3.client(
                "s3",
                endpoint_url=url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name="us-east-1",
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )

        self._bucket = bucket
        self._client = client(endpoint)
        self._public_client = client(public_endpoint or endpoint)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        body: bytes = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        return body

    def presigned_url(self, key: str, expires_s: int = 900) -> str:
        url: str = self._public_client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=expires_s
        )
        return url
