"""File storage behind one interface. Local disk now; Cloudflare R2 on the server."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.documents.models import Document


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("bad key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = LocalStorage(get_settings().storage_dir)
    return _storage


def set_storage(s: Storage | None) -> None:
    """Tests swap in a temporary directory."""
    global _storage
    _storage = s


def store(
    db: Session,
    *,
    kind: str,
    filename: str,
    data: bytes,
    content_type: str,
    enquiry_id: uuid.UUID | None,
) -> Document:
    doc_id = uuid.uuid4()
    key = f"{enquiry_id or 'misc'}/{doc_id}/{filename}"
    get_storage().put(key, data, content_type)
    doc = Document(
        id=doc_id,
        kind=kind,
        enquiry_id=enquiry_id,
        filename=filename,
        content_type=content_type,
        storage_key=key,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )
    db.add(doc)
    db.flush()
    return doc


def read(doc: Document) -> bytes:
    return get_storage().get(doc.storage_key)
