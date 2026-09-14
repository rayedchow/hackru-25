from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import httpx
import pytest
import synapse_memory.database as database_module
from conftest import FakeOCR, MutableClock
from synapse_memory.config import MemoryConfig
from synapse_memory.database import MemoryDatabase
from synapse_memory.errors import (
    AmbiguousRemoteFailure,
    ContentDenied,
    LeaseConflict,
    RemoteResponseInvalid,
)
from synapse_memory.models import ImageMetadata, ProcessingState, RemoteProcessingRequest
from synapse_memory.providers import MAX_REMOTE_RESPONSE_BYTES, HTTPRemoteProvider
from synapse_memory.service import MemoryService


def _remote_request() -> RemoteProcessingRequest:
    return RemoteProcessingRequest(
        content_id="mem-" + "a" * 40,
        redacted_text="synthetic evidence",
        metadata=ImageMetadata(width=32, height=24, format="png", mode="rgb"),
        policy_version="privacy-v1",
        idempotency_key="b" * 64,
    )


def test_migration_up_and_down_are_reversible(tmp_path: Path) -> None:
    database = MemoryDatabase(tmp_path / "memory.sqlite3")

    database.migrate_up()

    assert database.schema_version() == 1
    with sqlite3.connect(database.path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        deletion_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(deletion_status)").fetchall()
        }
    assert {"memory_items", "deletion_status"} <= tables
    assert {"lease_token", "lease_expires_at"} <= deletion_columns

    database.migrate_down()

    assert database.schema_version() == 0
    with sqlite3.connect(database.path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "memory_items" not in tables
    assert "deletion_status" not in tables


def test_failed_migration_rolls_back_schema_and_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = MemoryDatabase(tmp_path / "memory.sqlite3")
    monkeypatch.setattr(
        database_module,
        "SCHEMA_V1",
        "CREATE TABLE should_rollback (value TEXT); INVALID SQL",
    )

    with pytest.raises(sqlite3.Error):
        database.migrate_up()

    with sqlite3.connect(database.path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'should_rollback'"
        ).fetchone()
    assert version == 0
    assert table is None


def test_duplicate_concurrent_ingest_creates_one_canonical_item_and_blob(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())

    def ingest_once(_index: int) -> tuple[str, bool]:
        envelope, created = service.ingest(synthetic_png, source="synthetic")
        return envelope.content_id, created

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(ingest_once, range(16)))

    assert len({content_id for content_id, _created in outcomes}) == 1
    assert sum(created for _content_id, created in outcomes) == 1
    assert len(list(config.blob_root.glob("*.blob"))) == 1


def test_delete_winning_between_blob_write_and_database_mark_leaves_no_orphan(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())
    original_mark = service.database.mark_stored

    def delete_then_mark(**kwargs: object):  # type: ignore[no-untyped-def]
        service.delete(str(kwargs["content_id"]))
        return original_mark(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service.database, "mark_stored", delete_then_mark)

    envelope, _ = service.ingest(synthetic_png)

    assert envelope.state is ProcessingState.DELETED
    assert list(config.blob_root.glob("*.blob")) == []


def test_failed_racing_blob_deletion_is_visible_and_retryable(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())
    assert service.blobs is not None
    original_store = service.blobs.store

    def delete_then_store(**kwargs: object):  # type: ignore[no-untyped-def]
        service.delete(str(kwargs["content_id"]))
        return original_store(**kwargs)  # type: ignore[arg-type]

    def fail_cleanup(_blob_name: str) -> None:
        raise OSError("synthetic cleanup failure")

    with monkeypatch.context() as context:
        context.setattr(service.blobs, "store", delete_then_store)
        context.setattr(service.blobs, "delete", fail_cleanup)
        envelope, _ = service.ingest(synthetic_png)

    failed = service.database.deletion_receipt(
        content_id=envelope.content_id,
        owner_id=config.owner_id,
    )
    encrypted = next(item for item in failed.stores if item.store == "encrypted_blob")
    assert failed.complete is False
    assert failed.state is ProcessingState.DELETING
    assert encrypted.state.value == "failed"
    assert list(config.blob_root.glob("*.blob"))

    retried = service.delete(envelope.content_id)
    assert retried.complete is True
    assert list(config.blob_root.glob("*.blob")) == []


def test_concurrent_workers_execute_one_claim_once(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    ocr = FakeOCR()
    service = MemoryService(config, clock=clock, ocr_provider=ocr)
    service.ingest(synthetic_png)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _index: service.process_next(), range(2)))

    assert sum(outcome is not None for outcome in outcomes) == 1
    assert ocr.calls == 1
    processed = next(outcome for outcome in outcomes if outcome is not None)
    assert processed.envelope.state is ProcessingState.PROCESSED


def test_invalid_heartbeat_interval_is_rejected(config: MemoryConfig) -> None:
    with pytest.raises(ValueError, match="heartbeat interval"):
        MemoryService(
            config,
            ocr_provider=FakeOCR(),
            lease_heartbeat_interval_seconds=0,
        )


def test_stale_worker_cannot_ack_after_lease_recovery(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())
    envelope, _ = service.ingest(synthetic_png)
    first = service.database.claim_next(
        owner_id=config.owner_id,
        now=clock(),
        lease_seconds=10,
        max_retries=2,
    )
    assert first is not None and first.lease_token is not None
    clock.advance(seconds=11)
    recovered = service.database.claim_next(
        owner_id=config.owner_id,
        now=clock(),
        lease_seconds=10,
        max_retries=2,
    )
    assert recovered is not None and recovered.lease_token is not None

    with pytest.raises(LeaseConflict):
        service.database.mark_processed(
            content_id=envelope.content_id,
            owner_id=config.owner_id,
            lease_token=first.lease_token,
            redacted_text="stale",
            caption="stale",
            image_metadata=ImageMetadata(width=1, height=1, format="png", mode="rgb"),
            provider_version="local-v1",
            now=clock(),
        )

    current = service.database.get(envelope.content_id, config.owner_id)
    assert current.envelope.state is ProcessingState.PROCESSING
    assert current.lease_token == recovered.lease_token


def test_heartbeat_prevents_reclaim_during_slow_provider_work(
    tmp_path: Path,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    entered = Event()
    release = Event()
    renewed = Event()

    class BlockingOCR:
        name = "blocking-local-ocr"

        def extract_text(self, _image_bytes: bytes) -> str:
            entered.set()
            assert release.wait(timeout=30)
            return "synthetic evidence"

    config = MemoryConfig(data_root=tmp_path / "private", lease_seconds=5)
    service = MemoryService(
        config,
        clock=clock,
        ocr_provider=BlockingOCR(),
        lease_heartbeat_interval_seconds=0.01,
    )
    service.ingest(synthetic_png)
    original_renew = service.database.renew_processing_lease

    def observe_renewal(**kwargs: object) -> None:
        original_renew(**kwargs)  # type: ignore[arg-type]
        renewed.set()

    service.database.renew_processing_lease = observe_renewal  # type: ignore[method-assign]
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(service.process_next)
        assert entered.wait(timeout=10)
        clock.advance(seconds=6)
        renewed.clear()
        assert renewed.wait(timeout=10)
        competing = service.database.claim_next(
            owner_id=config.owner_id,
            now=clock(),
            lease_seconds=config.lease_seconds,
            max_retries=config.max_retries,
        )
        release.set()
        processed = future.result(timeout=30)

    assert competing is None
    assert processed is not None
    assert processed.envelope.state is ProcessingState.PROCESSED


def test_denied_source_fails_before_any_durable_item_or_blob(
    tmp_path: Path,
    synthetic_png: bytes,
) -> None:
    config = MemoryConfig(
        data_root=tmp_path / "private",
        denied_sources=("password-manager",),
    )
    service = MemoryService(config, ocr_provider=FakeOCR())

    with pytest.raises(ContentDenied):
        service.ingest(synthetic_png, source=" Password-Manager ")

    assert service.database.state_counts(config.owner_id)["received"] == 0
    assert list(config.blob_root.glob("*.blob")) == []


def test_locally_observed_denied_app_cannot_be_bypassed_by_client_label(
    tmp_path: Path,
    synthetic_png: bytes,
) -> None:
    class DetectedBank:
        name = "synthetic-source-observer"

        def detect(self, _image_bytes: bytes) -> str:
            return "BANK"

    config = MemoryConfig(data_root=tmp_path / "private", denied_sources=("bank",))
    service = MemoryService(
        config,
        ocr_provider=FakeOCR(),
        source_observation_provider=DetectedBank(),
    )

    with pytest.raises(ContentDenied):
        service.ingest(synthetic_png, source="desktop-hotkey")

    assert service.database.state_counts(config.owner_id)["received"] == 0
    assert list(config.blob_root.glob("*.blob")) == []


def test_source_rules_fail_closed_without_local_observation_provider(
    tmp_path: Path,
    synthetic_png: bytes,
) -> None:
    config = MemoryConfig(data_root=tmp_path / "private", denied_sources=("bank",))
    service = MemoryService(config, ocr_provider=FakeOCR())

    with pytest.raises(ContentDenied, match="source detector is required"):
        service.ingest(synthetic_png, source="desktop-hotkey")


def test_remote_provider_rejects_invalid_or_oversized_output() -> None:
    invalid_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"schema_version": "1", "extra": True})
        )
    )
    oversized_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, content=b"x" * (MAX_REMOTE_RESPONSE_BYTES + 1))
        )
    )

    with pytest.raises(RemoteResponseInvalid, match="invalid response"):
        HTTPRemoteProvider(
            endpoint="https://provider.invalid/v1", timeout_seconds=1, client=invalid_client
        ).process(_remote_request())
    with pytest.raises(RemoteResponseInvalid, match="size limit"):
        HTTPRemoteProvider(
            endpoint="https://provider.invalid/v1", timeout_seconds=1, client=oversized_client
        ).process(_remote_request())


def test_remote_timeout_is_ambiguous_and_not_retried() -> None:
    calls = 0

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    provider = HTTPRemoteProvider(
        endpoint="https://provider.invalid/v1",
        timeout_seconds=1,
        client=httpx.Client(transport=httpx.MockTransport(timeout)),
    )

    with pytest.raises(AmbiguousRemoteFailure, match="will not be retried"):
        provider.process(_remote_request())
    assert calls == 1


def test_remote_redirect_is_rejected_instead_of_followed() -> None:
    calls = 0

    def redirect(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(307, headers={"Location": "https://elsewhere.invalid"})

    provider = HTTPRemoteProvider(
        endpoint="https://provider.invalid/v1",
        timeout_seconds=1,
        client=httpx.Client(transport=httpx.MockTransport(redirect), follow_redirects=False),
    )

    with pytest.raises(RemoteResponseInvalid, match="rejected the request"):
        provider.process(_remote_request())
    assert calls == 1
