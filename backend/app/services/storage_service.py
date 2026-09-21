"""
File storage abstraction (Module: infrastructure).

Every uploaded submission file is currently saved to a local directory
inside the backend container (settings.UPLOAD_DIR). That is fine for a
single-container deployment, but has two real limits worth naming
honestly rather than hiding behind a generic "os.path" call at every
call site: (1) running more than one backend replica means each one only
sees the files IT saved, not the others', and (2) the files have no
redundancy beyond whatever backs up the Docker volume itself.

This module does not solve those by itself - that needs real object-storage
credentials (S3 or equivalent) this project cannot provision on BOT's
behalf. What it does is the same thing email_service.py already does for
SMTP: put a single, narrow interface between "the rest of the app" and
"where files actually live", so that plugging in real object storage later
is a change in ONE place (a new StorageBackend implementation + one config
value), not a search-and-replace through every endpoint that touches a file.

Usage elsewhere in the codebase:
    from app.services.storage_service import storage
    key = storage.save(file_bytes, "some-name.xlsx")   # returns a stored key/path
    data = storage.read(key)                            # bytes back out
    storage.delete(key)                                 # remove it
"""
import os
import uuid
from abc import ABC, abstractmethod

from app.core.config import settings


class StorageBackend(ABC):
    @abstractmethod
    def save(self, file_bytes: bytes, suggested_extension: str) -> str:
        """Persists the file, returns a key to retrieve it by later. For
        LocalFileStorage this is a real filesystem path (so today's direct
        os.path.exists()/FileResponse(...) callers keep working unchanged);
        a future object-storage backend would return its own key/URL
        instead, at which point read()/delete() - and the one or two
        call sites that currently open a path directly - would move to
        going through this class too."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Safe to call even if the key no longer exists - deletion is best-effort cleanup, not a guarantee callers should depend on."""


class LocalFileStorage(StorageBackend):
    """Today's actual behaviour, unchanged - files under settings.UPLOAD_DIR,
    named by a generated UUID so a client's own filename is never trusted
    as part of a filesystem path."""

    def save(self, file_bytes: bytes, suggested_extension: str) -> str:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        ext = suggested_extension.lstrip(".") or "bin"
        key = f"{uuid.uuid4()}.{ext}"
        path = os.path.join(settings.UPLOAD_DIR, key)
        with open(path, "wb") as f:
            f.write(file_bytes)
        return path

    def read(self, key: str) -> bytes:
        with open(key, "rb") as f:
            return f.read()

    def delete(self, key: str) -> None:
        if os.path.exists(key):
            os.remove(key)


# A future S3Storage(StorageBackend) (or Azure Blob / GCS equivalent) would
# implement the same three methods and be selected here via a
# settings.STORAGE_BACKEND value once BOT provides real object-storage
# credentials - no other file in this codebase would need to change.
storage: StorageBackend = LocalFileStorage()
