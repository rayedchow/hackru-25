from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import pytest
from conftest import FakeOCR, MutableClock
from synapse_memory.config import MemoryConfig
from synapse_memory.errors import LeaseConflict, OwnerMismatch
from synapse_memory.models import DeletionState, ProcessingState, RetentionClass
from synapse_memory.providers import DeletionAdapter
from synapse_memory.service import MemoryService


class RecordingDeletionAdapter:
    def __init__(self, name: str, *, failures: int = 0) -> None:
        self.name = name
        self.failures = failures
        self.calls: list[tuple[str, str]] = []

    def delete(self, *, owner_id: str, content_id: str) -> None:
        self.calls.append((owner_id, content_id))
        if len(self.calls) <= self.failures:
            raise RuntimeError("synthetic adapter failure")


class BlockingDeletionAdapter:
    name = "vector"

    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.calls = 0

    def delete(self, *, owner_id: str, content_id: str) -> None:
        assert owner_id and content_id
        self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=3)


def _processed_service(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
    *,
    deletion_adapters: dict[str, DeletionAdapter] | None = None,
) -> tuple[MemoryService, str]:
    service = MemoryService(
        config,
        clock=clock,
        ocr_provider=FakeOCR("synthetic roadmap evidence"),
        deletion_adapters=deletion_adapters,
    )
    envelope, _ = service.ingest(synthetic_png, source="synthetic")
    processed = service.process_next()
    assert processed is not None and processed.envelope.state is ProcessingState.PROCESSED
    return service, envelope.content_id


def test_delete_removes_each_configured_store_and_is_idempotent(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    vector = RecordingDeletionAdapter("vector")
    graph = RecordingDeletionAdapter("graph")
    service, content_id = _processed_service(
        config,
        clock,
        synthetic_png,
        deletion_adapters={"vector": vector, "graph": graph},
    )
    record = service.database.get(content_id, config.owner_id)
    assert record.blob_name is not None
    blob_path = config.blob_root / record.blob_name
    assert blob_path.exists()
    assert service.search("roadmap").evidence

    receipt = service.delete(content_id)
    repeated = service.delete(content_id)

    assert receipt.complete is True
    assert receipt.state is ProcessingState.DELETED
    assert {item.store: item.state for item in receipt.stores} == {
        "encrypted_blob": DeletionState.COMPLETE,
        "graph": DeletionState.COMPLETE,
        "local_index": DeletionState.COMPLETE,
        "vector": DeletionState.COMPLETE,
    }
    assert not blob_path.exists()
    assert service.search("roadmap").evidence == []
    assert repeated.complete is True
    assert vector.calls == [(config.owner_id, content_id)]
    assert graph.calls == [(config.owner_id, content_id)]


def test_partial_deletion_stays_visible_and_retryable(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    vector = RecordingDeletionAdapter("vector", failures=1)
    service, content_id = _processed_service(
        config,
        clock,
        synthetic_png,
        deletion_adapters={"vector": vector},
    )

    first = service.delete(content_id)

    assert first.complete is False
    assert first.state is ProcessingState.DELETING
    assert (
        next(item for item in first.stores if item.store == "vector").state is DeletionState.FAILED
    )
    assert service.search("roadmap").evidence == []

    second = service.delete(content_id)

    assert second.complete is True
    assert second.state is ProcessingState.DELETED
    vector_status = next(item for item in second.stores if item.store == "vector")
    assert vector_status.state is DeletionState.COMPLETE
    assert vector_status.attempts == 2


def test_concurrent_deletion_calls_claim_each_external_store_once(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    vector = BlockingDeletionAdapter()
    service, content_id = _processed_service(
        config,
        clock,
        synthetic_png,
        deletion_adapters={"vector": vector},
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        first_future = executor.submit(service.delete, content_id)
        assert vector.entered.wait(timeout=3)
        overlapping = service.delete(content_id)
        vector.release.set()
        first = first_future.result(timeout=3)

    assert overlapping.complete is False
    assert first.complete is True
    assert vector.calls == 1
    final = service.database.deletion_receipt(
        content_id=content_id,
        owner_id=config.owner_id,
    )
    vector_status = next(item for item in final.stores if item.store == "vector")
    assert vector_status.attempts == 1


def test_crashed_deletion_claim_recovers_after_lease_expiry(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    service, content_id = _processed_service(config, clock, synthetic_png)
    service.database.begin_deletion(
        content_id=content_id,
        owner_id=config.owner_id,
        stores=("vector",),
        now=clock(),
    )
    stale = service.database.claim_store_deletion(
        content_id=content_id,
        owner_id=config.owner_id,
        store="vector",
        now=clock(),
        lease_seconds=10,
    )
    assert stale is not None
    clock.advance(seconds=11)

    recovered = service.database.claim_store_deletion(
        content_id=content_id,
        owner_id=config.owner_id,
        store="vector",
        now=clock(),
        lease_seconds=10,
    )
    assert recovered is not None and recovered != stale
    with pytest.raises(LeaseConflict):
        service.database.record_store_deletion(
            content_id=content_id,
            store="vector",
            lease_token=stale,
            state=DeletionState.COMPLETE,
            error_code=None,
            now=clock(),
        )
    service.database.record_store_deletion(
        content_id=content_id,
        store="vector",
        lease_token=recovered,
        state=DeletionState.COMPLETE,
        error_code=None,
        now=clock(),
    )

    receipt = service.database.deletion_receipt(
        content_id=content_id,
        owner_id=config.owner_id,
    )
    vector = next(item for item in receipt.stores if item.store == "vector")
    assert vector.state is DeletionState.COMPLETE
    assert vector.attempts == 2


def test_ttl_sweep_removes_expired_item_from_every_configured_store(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    vector = RecordingDeletionAdapter("vector")
    graph = RecordingDeletionAdapter("graph")
    service = MemoryService(
        replace(config, session_retention_days=1),
        clock=clock,
        ocr_provider=FakeOCR("expiring synthetic evidence"),
        deletion_adapters={"vector": vector, "graph": graph},
    )
    envelope, _ = service.ingest(
        synthetic_png,
        retention_class=RetentionClass.SESSION,
    )
    assert service.process_next() is not None
    clock.advance(days=1, seconds=1)

    receipts = service.sweep_expired()

    assert len(receipts) == 1 and receipts[0].complete
    assert receipts[0].content_id == envelope.content_id
    assert service.search("expiring").evidence == []
    assert vector.calls == [(config.owner_id, envelope.content_id)]
    assert graph.calls == [(config.owner_id, envelope.content_id)]


def test_expired_or_deleted_content_never_appears_in_answers(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR("private synthetic fact"))
    envelope, _ = service.ingest(
        synthetic_png,
        retention_class=RetentionClass.SESSION,
    )
    assert service.process_next() is not None
    clock.advance(days=2)

    expired = service.search("private fact")
    assert expired.insufficient_evidence is True
    assert expired.evidence == []

    service.delete(envelope.content_id)
    deleted = service.search("private fact")
    assert deleted.insufficient_evidence is True
    assert deleted.evidence == []


def test_cross_owner_read_delete_and_search_are_isolated(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    service, content_id = _processed_service(config, clock, synthetic_png)

    with pytest.raises(OwnerMismatch):
        service.database.get(content_id, "different-owner")
    with pytest.raises(OwnerMismatch):
        service.delete(content_id, owner_id="different-owner")
    assert service.search("roadmap", owner_id="different-owner").evidence == []


def test_later_ttl_sweep_retries_a_visible_partial_deletion(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    vector = RecordingDeletionAdapter("vector", failures=1)
    service = MemoryService(
        config,
        clock=clock,
        ocr_provider=FakeOCR("expiring evidence"),
        deletion_adapters={"vector": vector},
    )
    service.ingest(synthetic_png, retention_class=RetentionClass.SESSION)
    assert service.process_next() is not None
    clock.advance(days=2)

    first = service.sweep_expired()
    second = service.sweep_expired()

    assert len(first) == 1 and first[0].complete is False
    assert len(second) == 1 and second[0].complete is True
    assert len(vector.calls) == 2
