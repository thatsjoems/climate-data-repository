"""
Tests for app/services/storage_service.py (Module: infrastructure).

This abstraction exists specifically so a future object-storage backend can
be swapped in without touching every call site - these tests exist to make
sure LocalFileStorage's actual behaviour (what every caller in this
codebase currently depends on) stays exactly what it claims to be.
"""
import os
import pytest

from app.services.storage_service import LocalFileStorage
from app.core.config import settings


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    """Every test gets its own throwaway directory - never writes into
    this project's real uploads/ folder."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return LocalFileStorage()


def test_save_writes_the_exact_bytes_given(isolated_storage):
    key = isolated_storage.save(b"hello world", "xlsx")
    with open(key, "rb") as f:
        assert f.read() == b"hello world"


def test_save_names_the_file_with_the_given_extension(isolated_storage):
    key = isolated_storage.save(b"data", "xlsx")
    assert key.endswith(".xlsx")


def test_save_generates_its_own_name_not_derived_from_input(isolated_storage):
    # save() only accepts an extension, never a filename - so a malicious
    # caller has no path-traversal string to inject in the first place.
    # This confirms the generated name is a UUID, not anything derived
    # from caller-controlled data.
    import uuid
    key = isolated_storage.save(b"data", "xlsx")
    stem = os.path.basename(key).rsplit(".", 1)[0]
    uuid.UUID(stem)  # raises ValueError if this isn't a real UUID


def test_two_saves_never_collide(isolated_storage):
    key1 = isolated_storage.save(b"first file", "xlsx")
    key2 = isolated_storage.save(b"second file", "xlsx")
    assert key1 != key2
    with open(key1, "rb") as f:
        assert f.read() == b"first file"
    with open(key2, "rb") as f:
        assert f.read() == b"second file"


def test_read_returns_exactly_what_was_saved(isolated_storage):
    key = isolated_storage.save(b"round trip check", "xlsx")
    assert isolated_storage.read(key) == b"round trip check"


def test_delete_removes_the_file(isolated_storage):
    key = isolated_storage.save(b"to be deleted", "xlsx")
    isolated_storage.delete(key)
    assert not os.path.exists(key)


def test_delete_is_safe_on_a_key_that_was_never_saved(isolated_storage, tmp_path):
    # Best-effort cleanup, per the class's own contract - must not raise.
    nonexistent = str(tmp_path / "never-existed.xlsx")
    isolated_storage.delete(nonexistent)  # should not raise


def test_save_creates_the_upload_directory_if_missing(tmp_path, monkeypatch):
    brand_new_dir = tmp_path / "does-not-exist-yet"
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(brand_new_dir))
    storage = LocalFileStorage()
    key = storage.save(b"data", "xlsx")
    assert os.path.exists(key)
    assert os.path.isdir(str(brand_new_dir))
