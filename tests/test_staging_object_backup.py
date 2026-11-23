"""Day 2 local tests for full-byte private-object archive/restore.

These never contact hosted Supabase S3 and never attest to hosted D02.T09.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.coworker.storage import LocalObjectStore
from scripts import staging_object_backup as backup


SRC = hashlib.sha256(b"synthetic-source-bucket").hexdigest()
DST = hashlib.sha256(b"disposable-target-bucket").hexdigest()


def _source(tmp_path: Path):
    store = LocalObjectStore(tmp_path / "source")
    payloads = {
        "owner-a/inputs/v1/source.pdf": b"%PDF-1.4\nSYNTHETIC_OWNER_A\n%%EOF\n",
        "owner-b/inputs/v2/source.txt": "বাংলা and English\n".encode("utf-8"),
    }
    for key, payload in payloads.items():
        store.put(key, payload, "application/octet-stream")
    return store, payloads


def _archive(tmp_path: Path):
    store, payloads = _source(tmp_path)
    archive = tmp_path / "private-backup"
    manifest = backup.archive_store(store, SRC, archive)
    return archive, manifest, payloads


def test_local_archive_and_distinct_empty_restore_read_back_every_byte(tmp_path):
    archive, manifest, payloads = _archive(tmp_path)
    assert manifest["schema_version"] == 1
    assert manifest["status"] == "archived"
    assert manifest["source_storage_fingerprint"] == SRC
    assert manifest["object_count"] == 2
    assert manifest["total_bytes"] == sum(map(len, payloads.values()))
    assert sorted(row["key"] for row in manifest["objects"]) == sorted(payloads)
    assert stat.S_IMODE(archive.stat().st_mode) == 0o700
    assert stat.S_IMODE((archive / "manifest.json").stat().st_mode) == 0o600
    assert all(
        stat.S_IMODE((archive / "objects" / row["file"]).stat().st_mode) == 0o600
        and row["sha256"] == hashlib.sha256(payloads[row["key"]]).hexdigest()
        for row in manifest["objects"]
    )

    destination = LocalObjectStore(tmp_path / "isolated-target")
    receipt = tmp_path / "restore-receipt.json"
    restored = backup.restore_store(destination, DST, archive, receipt)
    assert restored["status"] == "verified"
    assert restored["source_storage_fingerprint"] == SRC
    assert restored["target_storage_fingerprint"] == DST
    assert restored["object_count"] == 2
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert json.loads(receipt.read_text()) == restored
    assert [o.key for o in destination.inventory()] == sorted(payloads)
    for key, body in payloads.items():
        assert destination.get(key, len(body)) == body


def test_empty_source_never_qualifies_an_archive(tmp_path):
    source = LocalObjectStore(tmp_path / "empty")
    archive = tmp_path / "private-backup"
    with pytest.raises(backup.ObjectArchiveError, match="empty"):
        backup.archive_store(source, SRC, archive)
    assert not (archive / "manifest.json").exists()


def test_explicit_empty_baseline_archive_and_restore_are_marked_baseline_only(tmp_path):
    source = LocalObjectStore(tmp_path / "empty-source")
    archive = tmp_path / "preseed-baseline"
    manifest = backup.archive_store(source, SRC, archive, allow_empty_baseline=True)
    assert manifest["status"] == "baseline_archived"
    assert manifest["object_count"] == 0
    assert manifest["total_bytes"] == 0
    assert manifest["objects"] == []
    assert json.loads((archive / "manifest.json").read_text()) == manifest
    verified, rows, _sha = backup._manifest(archive)
    assert verified == manifest and rows == []

    target = SpyTarget(tmp_path / "empty-target")
    receipt = tmp_path / "baseline-receipt.json"
    with pytest.raises(backup.ObjectArchiveError, match="baseline"):
        backup.restore_store(target, DST, archive, receipt)
    assert not receipt.exists() and target.puts == []

    result = backup.restore_store(
        target, DST, archive, receipt, allow_empty_baseline=True,
    )
    assert result["status"] == "baseline_verified"
    assert result["object_count"] == 0
    assert result["total_bytes"] == 0
    assert result["objects"] == []
    assert json.loads(receipt.read_text()) == result
    assert target.puts == [] and target.inventory() == []


def test_baseline_mode_rejects_nonempty_source(tmp_path):
    source, _ = _source(tmp_path)
    with pytest.raises(backup.ObjectArchiveError, match="baseline"):
        backup.archive_store(source, SRC, tmp_path / "nonempty", allow_empty_baseline=True)


def test_baseline_restore_rejects_occupied_target_and_same_resource(tmp_path):
    source = LocalObjectStore(tmp_path / "empty-source")
    archive = tmp_path / "empty-archive"
    backup.archive_store(source, SRC, archive, allow_empty_baseline=True)
    occupied = SpyTarget(tmp_path / "occupied-target")
    occupied.wrapped.put("owner-a/inputs/v1/keep.txt", b"keep", "text/plain")
    receipt = tmp_path / "baseline-receipt.json"
    with pytest.raises(backup.ObjectArchiveError, match="empty"):
        backup.restore_store(
            occupied, DST, archive, receipt, allow_empty_baseline=True,
        )
    assert not receipt.exists() and occupied.puts == []

    empty = SpyTarget(tmp_path / "same-target")
    with pytest.raises(backup.ObjectArchiveError, match="distinct"):
        backup.restore_store(
            empty, SRC, archive, receipt, allow_empty_baseline=True,
        )
    assert not receipt.exists() and empty.puts == []


def test_baseline_restore_mode_never_relabels_a_nonempty_archive(tmp_path):
    archive, _, _ = _archive(tmp_path)
    target = SpyTarget(tmp_path / "target")
    receipt = tmp_path / "receipt.json"
    with pytest.raises(backup.ObjectArchiveError, match="baseline"):
        backup.restore_store(
            target, DST, archive, receipt, allow_empty_baseline=True,
        )
    assert target.puts == [] and not receipt.exists()


def test_manifest_rejects_forged_baseline_status_object_count_pairs(tmp_path):
    source = LocalObjectStore(tmp_path / "empty-source")
    empty_archive = tmp_path / "zero-archive"
    baseline = backup.archive_store(source, SRC, empty_archive, allow_empty_baseline=True)
    baseline["status"] = "archived"
    (empty_archive / "manifest.json").write_text(json.dumps(baseline), encoding="utf-8")
    with pytest.raises(backup.ObjectArchiveError, match="baseline"):
        backup._manifest(empty_archive)

    nonempty_archive, normal, _ = _archive(tmp_path)
    normal["status"] = "baseline_archived"
    (nonempty_archive / "manifest.json").write_text(json.dumps(normal), encoding="utf-8")
    with pytest.raises(backup.ObjectArchiveError, match="baseline"):
        backup._manifest(nonempty_archive)


def test_source_mutation_during_archive_is_rejected(tmp_path):
    source, _ = _source(tmp_path)
    archive = tmp_path / "private-backup"

    class ChangingStore:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.listings = 0

        def inventory(self):
            self.listings += 1
            if self.listings == 2:
                self.wrapped.put("owner-b/inputs/v3/late.txt", b"late", "text/plain")
            return self.wrapped.inventory()

        def get(self, key, limit):
            return self.wrapped.get(key, limit)

    with pytest.raises(backup.ObjectArchiveError, match="changed"):
        backup.archive_store(ChangingStore(source), SRC, archive)
    assert not (archive / "manifest.json").exists()


def test_archive_rejects_oversized_object_without_reading_it(monkeypatch, tmp_path):
    source, _ = _source(tmp_path)
    monkeypatch.setattr(backup, "MAX_OBJECT_BYTES", 8)

    class ReadForbidden:
        def inventory(self):
            return source.inventory()

        def get(self, *_):
            pytest.fail("Oversized object was downloaded")

    archive = tmp_path / "private-backup"
    with pytest.raises(backup.ObjectArchiveError, match="maximum"):
        backup.archive_store(ReadForbidden(), SRC, archive)
    assert not (archive / "manifest.json").exists()


class SpyTarget:
    def __init__(self, path: Path):
        self.wrapped = LocalObjectStore(path)
        self.puts = []

    def inventory(self):
        return self.wrapped.inventory()

    def put(self, key, value, content_type):
        self.puts.append(key)
        self.wrapped.put(key, value, content_type)

    def get(self, key, limit):
        return self.wrapped.get(key, limit)


def test_restore_refuses_same_resource_before_any_write(tmp_path):
    archive, _, _ = _archive(tmp_path)
    target = SpyTarget(tmp_path / "target")
    output = tmp_path / "restore-receipt.json"
    with pytest.raises(backup.ObjectArchiveError, match="distinct"):
        backup.restore_store(target, SRC, archive, output)
    assert target.puts == [] and not output.exists()


def test_restore_refuses_nonempty_target_before_any_write(tmp_path):
    archive, _, _ = _archive(tmp_path)
    target = SpyTarget(tmp_path / "target")
    target.wrapped.put("existing/inputs/v1/existing.txt", b"untouched", "text/plain")
    output = tmp_path / "restore-receipt.json"
    with pytest.raises(backup.ObjectArchiveError, match="empty"):
        backup.restore_store(target, DST, archive, output)
    assert target.puts == [] and not output.exists()
    assert target.wrapped.get("existing/inputs/v1/existing.txt", 9) == b"untouched"


@pytest.mark.parametrize("corruption", ["bytes", "digest", "duplicate", "symlink", "missing"])
def test_restore_refuses_corrupt_or_ambiguous_archive_before_any_write(tmp_path, corruption):
    archive, manifest, _ = _archive(tmp_path)
    path = archive / "objects" / manifest["objects"][0]["file"]
    if corruption == "bytes":
        path.write_bytes(b"tampered")
    elif corruption == "digest":
        manifest["objects"][0]["sha256"] = "0" * 64
    elif corruption == "duplicate":
        manifest["objects"].append(dict(manifest["objects"][0]))
        manifest["object_count"] += 1
        manifest["total_bytes"] += manifest["objects"][0]["byte_size"]
    elif corruption == "symlink":
        contents = path.read_bytes()
        path.unlink()
        other = tmp_path / "untrusted-source"
        other.write_bytes(contents)
        path.symlink_to(other)
    elif corruption == "missing":
        path.unlink()
    if corruption in ("digest", "duplicate"):
        (archive / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    target = SpyTarget(tmp_path / "target")
    output = tmp_path / "restore-receipt.json"
    with pytest.raises(backup.ObjectArchiveError):
        backup.restore_store(target, DST, archive, output)
    assert target.puts == [] and not output.exists()


def test_restore_preflights_receipt_destination_before_uploads(tmp_path):
    archive, _, _ = _archive(tmp_path)
    target = SpyTarget(tmp_path / "target")
    receipt = tmp_path / "occupied.json"
    receipt.write_text("original")
    with pytest.raises(backup.ObjectArchiveError, match="receipt"):
        backup.restore_store(target, DST, archive, receipt)
    assert target.puts == []
    assert receipt.read_text() == "original"


def test_restore_readback_detects_corrupt_target_and_emits_no_pass(tmp_path):
    archive, _, _ = _archive(tmp_path)

    class CorruptingTarget(SpyTarget):
        def get(self, key, limit):
            data = super().get(key, limit)
            return b"tampered" if self.puts else data

    target = CorruptingTarget(tmp_path / "target")
    output = tmp_path / "restore-receipt.json"
    with pytest.raises(backup.ObjectArchiveError, match="readback"):
        backup.restore_store(target, DST, archive, output)
    assert target.puts
    assert not output.exists()


def test_archive_existing_output_directory_is_never_overwritten(tmp_path):
    source, _ = _source(tmp_path)
    archive = tmp_path / "already-there"
    archive.mkdir()
    (archive / "important.txt").write_text("retain me")
    with pytest.raises(backup.ObjectArchiveError, match="fresh"):
        backup.archive_store(source, SRC, archive)
    assert (archive / "important.txt").read_text() == "retain me"


def test_archive_rejects_total_bytes_before_reading_any_object(monkeypatch, tmp_path):
    source, _ = _source(tmp_path)
    monkeypatch.setattr(backup, "MAX_TOTAL_BYTES", 12)

    class ReadForbidden:
        def inventory(self):
            return source.inventory()

        def get(self, *_):
            pytest.fail("Aggregate over-limit source was downloaded")

    archive = tmp_path / "too-large"
    with pytest.raises(backup.ObjectArchiveError, match="total"):
        backup.archive_store(ReadForbidden(), SRC, archive)
    assert not (archive / "manifest.json").exists()


def test_restore_refuses_symlinked_object_directory(tmp_path):
    archive, _manifest, _payloads = _archive(tmp_path)
    root = archive / "objects"
    real = archive / "objects-real"
    root.rename(real)
    root.symlink_to(real, target_is_directory=True)
    target = SpyTarget(tmp_path / "target")
    output = tmp_path / "restore-receipt.json"
    with pytest.raises(backup.ObjectArchiveError, match="symlink"):
        backup.restore_store(target, DST, archive, output)
    assert target.puts == [] and not output.exists()


def test_cli_requires_explicit_guard_before_storage_is_initialized(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_OBJECT_ARCHIVE", raising=False)
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_OBJECT_RESTORE", raising=False)
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", raising=False)
    monkeypatch.setattr(backup, "make_storage", lambda _: pytest.fail("Storage was initialized"))
    assert backup.main(["archive", "--directory", str(tmp_path / "archive")]) == 1
    assert "guards" in capsys.readouterr().out
    assert backup.main([
        "restore", "--archive-directory", str(tmp_path / "archive"),
        "--output", str(tmp_path / "restored.json"),
    ]) == 1
    assert "guards" in capsys.readouterr().out


def test_fake_s3_archive_retains_mime_metadata_and_restores_exact_private_bytes(tmp_path):
    """Exercise the real S3 store adapter against memory-only client objects."""
    import io
    from services.coworker.storage import S3ObjectStore

    class MemoryS3:
        def __init__(self):
            self.entries = {}

        def put_object(self, *, Bucket, Key, Body, ContentType, Metadata):
            self.entries[Key] = {
                "bytes": bytes(Body),
                "content_type": ContentType,
                "metadata": dict(Metadata),
                "modified_at": datetime.now(timezone.utc),
            }

        def list_objects_v2(self, *, Bucket, Prefix, MaxKeys, **kwargs):
            return {
                "IsTruncated": False,
                "Contents": [
                    {"Key": key, "Size": len(row["bytes"]),
                     "LastModified": row["modified_at"]}
                    for key, row in sorted(self.entries.items())
                    if key.startswith(Prefix)
                ],
            }

        def head_object(self, *, Bucket, Key):
            row = self.entries[Key]
            return {
                "ContentLength": len(row["bytes"]),
                "ContentType": row["content_type"],
                "Metadata": dict(row["metadata"]),
            }

        def get_object(self, *, Bucket, Key):
            row = self.entries[Key]
            return {
                "ContentLength": len(row["bytes"]),
                "Body": io.BytesIO(row["bytes"]),
            }

    def store(bucket):
        client = MemoryS3()
        # Exercise the real S3 adapter methods without importing boto3 in
        # the base Python suite: this is a memory-only test client.
        wrapped = object.__new__(S3ObjectStore)
        wrapped.bucket = bucket
        wrapped.client = client
        return wrapped, client

    source, original = store("private-source")
    source.put("owner-a/inputs/v1/report.pdf", b"%PDF-1.4\nPRIVATE\n%%EOF", "application/pdf")
    archive_dir = tmp_path / "archive"
    manifest = backup.archive_store(source, SRC, archive_dir)
    assert manifest["objects"][0]["content_type"] == "application/pdf"
    assert manifest["objects"][0]["sha256"] == original.entries[
        "owner-a/inputs/v1/report.pdf"
    ]["metadata"]["sha256"]

    restored, target_client = store("private-target")
    receipt = backup.restore_store(restored, DST, archive_dir, tmp_path / "verified.json")
    assert receipt["object_count"] == 1
    item = target_client.entries["owner-a/inputs/v1/report.pdf"]
    assert item["bytes"] == b"%PDF-1.4\nPRIVATE\n%%EOF"
    assert item["content_type"] == "application/pdf"
    assert item["metadata"]["sha256"] == manifest["objects"][0]["sha256"]



# The archive is untrusted local evidence. Neither prechecking a path nor
# matching its final SHA protects provenance if it is later reopened.
@pytest.mark.parametrize("where", ["top", "nested"])
def test_private_manifest_rejects_duplicate_keys_before_restore(tmp_path, where):
    archive, _manifest, _ = _archive(tmp_path)
    path = archive / "manifest.json"
    raw = path.read_text(encoding="utf-8")
    if where == "top":
        raw = raw.replace('"status": "archived"', '"status": "unverified", "status": "archived"', 1)
    else:
        raw = raw.replace('"sha256": ', '"sha256": "' + ("0" * 64) + '", "sha256": ', 1)
    path.write_text(raw, encoding="utf-8")
    target = SpyTarget(tmp_path / "target")
    with pytest.raises(backup.ObjectArchiveError, match="duplicate"):
        backup.restore_store(target, DST, archive, tmp_path / "receipt.json")
    assert target.puts == [] and not (tmp_path / "receipt.json").exists()


def test_private_manifest_rejects_oversize_before_parsing(tmp_path, monkeypatch):
    archive, _, _ = _archive(tmp_path)
    monkeypatch.setattr(backup, "MAX_MANIFEST_BYTES", 128, raising=False)
    target = SpyTarget(tmp_path / "target")
    with pytest.raises(backup.ObjectArchiveError, match="size|limit|large"):
        backup.restore_store(target, DST, archive, tmp_path / "receipt.json")
    assert target.puts == []


def test_private_manifest_rejects_symlink_substitution_at_descriptor_open(tmp_path, monkeypatch):
    archive, _, _ = _archive(tmp_path)
    path = archive / "manifest.json"
    alternative = tmp_path / "outside.json"
    alternative.write_bytes(path.read_bytes())
    real_open = os.open
    swapped = False

    def switch_at_open(candidate, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and (str(candidate) == "manifest.json" or Path(candidate) == path):
            swapped = True
            path.unlink()
            path.symlink_to(alternative)
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", switch_at_open)
    with pytest.raises(backup.ObjectArchiveError):
        backup._manifest(archive)
    assert swapped


def test_private_manifest_rejects_growth_after_descriptor_stat(tmp_path, monkeypatch):
    archive, _, _ = _archive(tmp_path)
    path = archive / "manifest.json"
    inode = path.stat().st_ino
    real_read = os.read
    modified = False

    def change_after_stat(fd, size):
        nonlocal modified
        if not modified and os.fstat(fd).st_ino == inode:
            modified = True
            with path.open("ab") as handle:
                handle.write(b" " * 512)
        return real_read(fd, size)

    monkeypatch.setattr(os, "read", change_after_stat)
    with pytest.raises(backup.ObjectArchiveError, match="changed|size"):
        backup._manifest(archive)
    assert modified


def test_private_object_blob_rejects_symlink_swap_at_open(tmp_path, monkeypatch):
    archive, manifest, _ = _archive(tmp_path)
    path = archive / "objects" / manifest["objects"][0]["file"]
    substitute = tmp_path / "outside-object.bin"
    substitute.write_bytes(path.read_bytes())
    real_open = os.open
    swapped = False

    def switch_blob_at_open(candidate, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and (str(candidate) == path.name or Path(candidate) == path):
            swapped = True
            path.unlink()
            path.symlink_to(substitute)
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", switch_blob_at_open)
    target = SpyTarget(tmp_path / "target")
    with pytest.raises(backup.ObjectArchiveError):
        backup.restore_store(target, DST, archive, tmp_path / "receipt.json")
    assert swapped
    assert target.puts == []


def test_private_objects_directory_rejects_symlink_swap_at_open(tmp_path, monkeypatch):
    archive, _, _ = _archive(tmp_path)
    directory = archive / "objects"
    moved = archive / "objects-original"
    real_open = os.open
    swapped = False

    def switch_dir_at_open(candidate, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and (str(candidate) == "objects" or Path(candidate) == directory):
            swapped = True
            directory.rename(moved)
            directory.symlink_to(moved, target_is_directory=True)
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", switch_dir_at_open)
    target = SpyTarget(tmp_path / "target")
    with pytest.raises(backup.ObjectArchiveError):
        backup.restore_store(target, DST, archive, tmp_path / "receipt.json")
    assert swapped
    assert target.puts == []


@pytest.mark.parametrize("mutation", ["append", "same_length"])
def test_private_object_blob_rejects_mutation_during_read(tmp_path, monkeypatch, mutation):
    archive, manifest, _ = _archive(tmp_path)
    path = archive / "objects" / manifest["objects"][0]["file"]
    inode = path.stat().st_ino
    real_read = os.read
    modified = False

    def mutate_before_read(fd, size):
        nonlocal modified
        if not modified and os.fstat(fd).st_ino == inode:
            modified = True
            original = path.read_bytes()
            if mutation == "append":
                with path.open("ab") as handle:
                    handle.write(b"+")
            else:
                path.write_bytes(original[:-1] + (b"z" if original[-1:] != b"z" else b"x"))
        return real_read(fd, size)

    monkeypatch.setattr(os, "read", mutate_before_read)
    target = SpyTarget(tmp_path / "target")
    with pytest.raises(backup.ObjectArchiveError, match="changed|size"):
        backup.restore_store(target, DST, archive, tmp_path / "receipt.json")
    assert modified
    assert target.puts == []
