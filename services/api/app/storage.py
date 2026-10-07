"""Document file storage: local disk for development, S3-compatible or Postgres in
production."""

from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import get_settings


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self) -> None:
        import boto3

        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key or None,
            aws_secret_access_key=settings.s3_secret_key or None,
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )

    def get(self, key: str) -> bytes:
        body: bytes = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return body

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


class DatabaseStorage:
    """Files in the ``stored_files`` table. Fine for a small deployment (the free tier of a
    hosted Postgres holds a few thousand contracts); move to S3 when it grows."""

    def put(self, key: str, data: bytes, content_type: str) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.db import SessionLocal
        from app.models import StoredFile

        with SessionLocal() as db:
            db.execute(
                insert(StoredFile)
                .values(key=key, content_type=content_type, data=data)
                .on_conflict_do_update(
                    index_elements=[StoredFile.key],
                    set_={"content_type": content_type, "data": data},
                )
            )
            db.commit()

    def get(self, key: str) -> bytes:
        from app.db import SessionLocal
        from app.models import StoredFile

        with SessionLocal() as db:
            row = db.get(StoredFile, key)
            if row is None:
                raise FileNotFoundError(key)
            return row.data

    def delete(self, key: str) -> None:
        from sqlalchemy import delete

        from app.db import SessionLocal
        from app.models import StoredFile

        with SessionLocal() as db:
            db.execute(delete(StoredFile).where(StoredFile.key == key))
            db.commit()


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3Storage()
    if settings.storage_backend == "database":
        return DatabaseStorage()
    return LocalStorage(settings.local_storage_dir)
