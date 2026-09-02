from __future__ import annotations

import sqlite3
import struct
import zlib
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import FakeOCR, MutableClock, make_png
from synapse_memory.config import MemoryConfig
from synapse_memory.crypto import EncryptedBlobStore, Keyring, load_keyring
from synapse_memory.errors import EncryptionKeyUnavailable, InvalidUpload, StorageIntegrityError
from synapse_memory.models import ProcessingState
from synapse_memory.service import MemoryService


def test_ingest_encrypts_before_durable_blob_and_does_not_store_raw_bytes(
    config: MemoryConfig, clock: MutableClock, synthetic_png: bytes
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())

    envelope, created = service.ingest(synthetic_png, source="synthetic")

    assert created is True
    assert envelope.state is ProcessingState.STORED
    files = list(config.blob_root.glob("*.blob"))
    assert len(files) == 1
    ciphertext = files[0].read_bytes()
    assert synthetic_png not in ciphertext
    assert envelope.content_hash.encode() not in files[0].name.encode()
    with sqlite3.connect(config.database_path) as connection:
        connection.row_factory = sqlite3.Row
        stored = connection.execute(
            "SELECT * FROM memory_items WHERE content_id = ?", (envelope.content_id,)
        ).fetchone()
    assert stored is not None
    row = dict(stored)
    serialized_row = repr(row).encode()
    assert synthetic_png not in serialized_row
    assert "image" not in row
    assert "payload" not in row


def test_duplicate_upload_is_idempotent_and_uses_one_blob(
    config: MemoryConfig, clock: MutableClock, synthetic_png: bytes
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())

    first, first_created = service.ingest(synthetic_png)
    second, second_created = service.ingest(synthetic_png)

    assert first_created is True
    assert second_created is False
    assert second.content_id == first.content_id
    assert second.content_hash == first.content_hash
    assert len(list(config.blob_root.glob("*.blob"))) == 1


def test_modified_ciphertext_fails_integrity_verification(
    config: MemoryConfig, clock: MutableClock, synthetic_png: bytes
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())
    envelope, _ = service.ingest(synthetic_png)
    record = service.database.get(envelope.content_id, config.owner_id)
    assert record.blob_name is not None
    path = config.blob_root / record.blob_name
    mutated = bytearray(path.read_bytes())
    mutated[-1] ^= 0x01
    path.write_bytes(mutated)

    with pytest.raises(StorageIntegrityError, match="integrity verification"):
        service.blobs.read(  # type: ignore[union-attr]
            blob_name=record.blob_name,
            owner_id=config.owner_id,
            content_id=envelope.content_id,
            content_hash=envelope.content_hash,
        )


def test_wrong_key_fails_safely(
    config: MemoryConfig, clock: MutableClock, synthetic_png: bytes
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())
    envelope, _ = service.ingest(synthetic_png)
    record = service.database.get(envelope.content_id, config.owner_id)
    assert record.blob_name is not None
    original = load_keyring(config.keyring_path)
    wrong = Keyring(active_key_id=original.active_key_id, keys={original.active_key_id: b"x" * 32})
    wrong_store = EncryptedBlobStore(config.blob_root, wrong)

    with pytest.raises(StorageIntegrityError, match="integrity verification"):
        wrong_store.read(
            blob_name=record.blob_name,
            owner_id=config.owner_id,
            content_id=envelope.content_id,
            content_hash=envelope.content_hash,
        )


def test_missing_keyring_fails_closed_but_status_remains_available(tmp_path: Path) -> None:
    config = MemoryConfig(data_root=tmp_path / "private", auto_create_key=False)
    service = MemoryService(config, ocr_provider=FakeOCR())

    assert service.status().key_available is False
    with pytest.raises(EncryptionKeyUnavailable, match="No encryption key"):
        service.ingest(make_png())
    assert not config.blob_root.exists()


def test_rotation_keeps_old_blob_decryptable(
    config: MemoryConfig, clock: MutableClock, synthetic_png: bytes
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())
    envelope, _ = service.ingest(synthetic_png)
    record = service.database.get(envelope.content_id, config.owner_id)
    old_key_id = record.key_id

    new_key_id = service.rotate_key()

    assert new_key_id != old_key_id
    assert record.blob_name is not None
    assert service.blobs is not None
    assert (
        service.blobs.read(
            blob_name=record.blob_name,
            owner_id=config.owner_id,
            content_id=envelope.content_id,
            content_hash=envelope.content_hash,
        )
        == synthetic_png
    )


def test_rotation_lock_fails_closed_without_changing_active_key(
    config: MemoryConfig,
    clock: MutableClock,
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())
    assert service.keyring is not None
    original_key_id = service.keyring.active_key_id
    lock_path = config.keyring_path.with_name(config.keyring_path.name + ".rotation.lock")
    lock_path.write_text("synthetic competing rotation\n", encoding="utf-8")

    with pytest.raises(EncryptionKeyUnavailable, match="already in progress"):
        service.rotate_key()

    assert load_keyring(config.keyring_path).active_key_id == original_key_id


def test_distinct_images_use_distinct_nondisclosing_paths(
    config: MemoryConfig, clock: MutableClock
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())
    first, _ = service.ingest(make_png(color=(1, 2, 3)))
    second, _ = service.ingest(make_png(color=(4, 5, 6)))

    assert first.content_id != second.content_id
    names = sorted(path.name for path in config.blob_root.glob("*.blob"))
    assert len(names) == 2
    assert all(first.content_hash not in name and second.content_hash not in name for name in names)


def test_oversized_image_dimensions_are_rejected_before_pixel_decode(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    oversized = bytearray(synthetic_png)
    struct.pack_into(">II", oversized, 16, 10_000, 5_000)
    struct.pack_into(">I", oversized, 29, zlib.crc32(oversized[12:29]) & 0xFFFFFFFF)
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())

    with pytest.raises(InvalidUpload, match="dimensions"):
        service.ingest(bytes(oversized))

    assert service.database.state_counts(config.owner_id)["received"] == 0
    assert list(config.blob_root.glob("*.blob")) == []


def test_key_loss_does_not_prevent_ciphertext_deletion(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    original = MemoryService(config, clock=clock, ocr_provider=FakeOCR())
    envelope, _ = original.ingest(synthetic_png)
    record = original.database.get(envelope.content_id, config.owner_id)
    assert record.blob_name is not None
    blob_path = config.blob_root / record.blob_name
    config.keyring_path.unlink()
    without_key = MemoryService(
        replace(config, auto_create_key=False),
        clock=clock,
        ocr_provider=FakeOCR(),
    )

    receipt = without_key.delete(envelope.content_id)

    assert receipt.complete is True
    assert receipt.state is ProcessingState.DELETED
    assert not blob_path.exists()
