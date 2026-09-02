from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
    assert {"memory_items", "deletion_status"} <= tables

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
