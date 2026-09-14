"""Orchestration for encrypted ingest, local processing, search, and deletion."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import MemoryConfig
from .crypto import (
    EncryptedBlobStore,
    Keyring,
    delete_encrypted_blob,
    load_keyring,
    load_or_create_keyring,
    rotate_keyring,
)
from .database import MemoryDatabase, MemoryRecord
from .errors import (
    ContentDenied,
    EncryptionKeyUnavailable,
    InvalidUpload,
    LeaseConflict,
    MemoryPipelineError,
)
from .models import (
    DeletionReceipt,
    DeletionState,
    FailureMetadata,
    IngestionEnvelope,
    PrivacyStatus,
    ProcessingState,
    RemoteProcessingRequest,
    RetentionClass,
    SearchHit,
    SearchResponse,
)
from .policy import enforce_source_policy, excerpt, redact_text, search_terms
from .providers import (
    DeletionAdapter,
    DeterministicHashEmbeddingProvider,
    DeterministicImageProvider,
    DisabledRemoteProvider,
    DisabledSourceObservationProvider,
    EmbeddingProvider,
    HTTPRemoteProvider,
    ImageUnderstandingProvider,
    OCRProvider,
    RemoteProcessingProvider,
    SourceObservationProvider,
    TesseractOCRProvider,
)

Clock = Callable[[], datetime]
DELETION_STORES = ("encrypted_blob", "local_index", "vector", "graph")
MIN_HEARTBEAT_INTERVAL_SECONDS = 0.1
MAX_HEARTBEAT_INTERVAL_SECONDS = 5.0


class _LeaseHeartbeat:
    """Renew a database lease while slow provider or deletion work runs."""

    def __init__(
        self,
        renew: Callable[[], None],
        *,
        interval_seconds: float,
    ) -> None:
        self._renew = renew
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._failure: Exception | None = None
        self._thread = threading.Thread(
            target=self._run, name="synapse-lease-heartbeat", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def ensure_owned(self) -> None:
        if self._failure is None:
            return
        if isinstance(self._failure, LeaseConflict):
            raise self._failure
        raise LeaseConflict("The lease could not be renewed safely.") from self._failure

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._renew()
            except Exception as exc:
                self._failure = exc
                self._stop.set()
                return


def utc_now() -> datetime:
    return datetime.now(UTC)


class MemoryService:
    def __init__(
        self,
        config: MemoryConfig,
        *,
        clock: Clock = utc_now,
        ocr_provider: OCRProvider | None = None,
        image_provider: ImageUnderstandingProvider | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        remote_provider: RemoteProcessingProvider | None = None,
        source_observation_provider: SourceObservationProvider | None = None,
        deletion_adapters: Mapping[str, DeletionAdapter] | None = None,
        keyring: Keyring | None = None,
        lease_heartbeat_interval_seconds: float | None = None,
    ) -> None:
        self.config = config
        self.clock = clock
        self.database = MemoryDatabase(config.database_path)
        self.database.migrate_up()
        self.ocr_provider = ocr_provider or TesseractOCRProvider()
        self.image_provider = image_provider or DeterministicImageProvider()
        self.embedding_provider = embedding_provider or DeterministicHashEmbeddingProvider()
        self.source_observation_provider = (
            source_observation_provider or DisabledSourceObservationProvider()
        )
        self.remote_provider: RemoteProcessingProvider
        if not config.remote_enabled:
            # Do not even retain an injected remote provider in local-only mode.
            self.remote_provider = DisabledRemoteProvider()
        elif remote_provider is not None:
            self.remote_provider = remote_provider
        else:
            assert config.remote_endpoint is not None
            self.remote_provider = HTTPRemoteProvider(
                endpoint=config.remote_endpoint,
                timeout_seconds=config.remote_timeout_seconds,
            )
        self.deletion_adapters = dict(deletion_adapters or {})
        default_heartbeat_interval = max(
            MIN_HEARTBEAT_INTERVAL_SECONDS,
            min(MAX_HEARTBEAT_INTERVAL_SECONDS, config.lease_seconds / 3),
        )
        self._heartbeat_interval_seconds = (
            default_heartbeat_interval
            if lease_heartbeat_interval_seconds is None
            else lease_heartbeat_interval_seconds
        )
        if not 0 < self._heartbeat_interval_seconds < config.lease_seconds:
            raise ValueError(
                "the lease heartbeat interval must be positive and shorter than the lease"
            )
        self._keyring_lock = threading.Lock()
        self._reload_keyring_from_disk = keyring is None
        self._key_error: EncryptionKeyUnavailable | None = None
        self.keyring: Keyring | None
        try:
            self.keyring = keyring or load_or_create_keyring(
                config.keyring_path, auto_create=config.auto_create_key
            )
        except EncryptionKeyUnavailable as exc:
            self.keyring = None
            self._key_error = exc
        self.blobs = EncryptedBlobStore(config.blob_root, self.keyring) if self.keyring else None

    def _refresh_keyring(self) -> None:
        """Observe rotations performed by another local process before blob access."""

        if not self._reload_keyring_from_disk:
            return
        with self._keyring_lock:
            if not self.config.keyring_path.exists():
                exc = self._key_error or EncryptionKeyUnavailable(
                    "No encryption key is available; restore the local keyring before ingesting."
                )
                self.keyring = None
                self.blobs = None
                self._key_error = exc
                raise exc
            try:
                on_disk = load_keyring(self.config.keyring_path)
            except EncryptionKeyUnavailable as exc:
                self.keyring = None
                self.blobs = None
                self._key_error = exc
                raise
            if on_disk != self.keyring:
                self.keyring = on_disk
                self.blobs = EncryptedBlobStore(self.config.blob_root, on_disk)
                self._key_error = None

    def _require_blobs(self) -> EncryptedBlobStore:
        if self.blobs is None or self.keyring is None:
            raise self._key_error or EncryptionKeyUnavailable(
                "The local encryption key is unavailable."
            )
        return self.blobs

    def _owner(self, owner_id: str | None) -> str:
        return owner_id or self.config.owner_id

    def _opaque_digest(self, label: bytes, value: bytes, prefix: str, length: int) -> str:
        keyring = self.keyring
        if keyring is None:
            self._require_blobs()
            raise AssertionError("unreachable")
        digest = hmac.digest(keyring.active_key, label + b"\x00" + value, "sha256").hex()
        return prefix + digest[:length]

    def _content_id(self, owner_id: str, content_hash: str) -> str:
        return self._opaque_digest(
            b"synapse-content-id-v1",
            owner_id.encode("utf-8") + b"\x00" + content_hash.encode("ascii"),
            "mem-",
            40,
        )

    def _device_pseudonym(self, owner_id: str, source: str) -> str:
        return self._opaque_digest(
            b"synapse-device-pseudonym-v1",
            owner_id.encode("utf-8") + b"\x00" + source.encode("utf-8"),
            "device-",
            24,
        )

    def _expiry(self, now: datetime, retention_class: RetentionClass) -> datetime | None:
        if retention_class is RetentionClass.KEEP:
            return None
        days = (
            self.config.session_retention_days
            if retention_class is RetentionClass.SESSION
            else self.config.default_retention_days
        )
        return now + timedelta(days=days)

    def ingest(
        self,
        image_bytes: bytes,
        *,
        owner_id: str | None = None,
        source: str | None = None,
        retention_class: RetentionClass = RetentionClass.STANDARD,
    ) -> tuple[IngestionEnvelope, bool]:
        self._refresh_keyring()
        blobs = self._require_blobs()
        if not image_bytes:
            raise InvalidUpload("The screenshot payload is empty.")
        if len(image_bytes) > self.config.max_upload_bytes:
            raise InvalidUpload("The screenshot exceeds the configured upload limit.")
        # Decode before any durable write. This also rejects non-image payloads.
        self.image_provider.describe(image_bytes)
        declared_source = enforce_source_policy(source, self.config.denied_sources)
        observed_source: str | None = None
        if self.config.denied_sources:
            if self.source_observation_provider.name == "disabled":
                raise ContentDenied(
                    "A local source detector is required while source deny rules are active."
                )
            try:
                observed_source = self.source_observation_provider.detect(image_bytes)
            except MemoryPipelineError:
                raise
            except Exception as exc:
                raise ContentDenied(
                    "Local source observation failed while source deny rules are active."
                ) from exc
            if observed_source is not None:
                observed_source = enforce_source_policy(
                    observed_source,
                    self.config.denied_sources,
                )
        normalized_source = (
            observed_source if observed_source and observed_source != "unknown" else declared_source
        )
        resolved_owner = self._owner(owner_id)
        now = self.clock().astimezone(UTC)
        content_hash = blobs.content_hash(image_bytes)
        content_id = self._content_id(resolved_owner, content_hash)
        key_id = blobs.keyring.active_key_id
        blob_name = blobs.blob_name(resolved_owner, content_hash, key_id)
        envelope = IngestionEnvelope(
            content_id=content_id,
            content_hash=content_hash,
            captured_at=now,
            device_pseudonym=self._device_pseudonym(resolved_owner, normalized_source),
            state=ProcessingState.RECEIVED,
            consent_version=self.config.consent_version,
            retention_class=retention_class,
            expires_at=self._expiry(now, retention_class),
            provider_version=self.config.provider_version,
            policy_version=self.config.policy_version,
        )
        record, created = self.database.create_received(
            envelope,
            owner_id=resolved_owner,
            blob_name=blob_name,
            key_id=key_id,
            now=now,
        )
        # A replay observes the canonical state. In particular, an upload must not
        # turn a terminal or delayed failure back into an immediately claimable item
        # and thereby bypass the bounded retry policy.
        if record.envelope.state is not ProcessingState.RECEIVED:
            return record.envelope, False
        if record.blob_name is None or record.key_id is None:
            raise EncryptionKeyUnavailable("The encrypted screenshot target is unavailable.")
        stored = blobs.store(
            owner_id=resolved_owner,
            content_id=record.envelope.content_id,
            content_hash=record.envelope.content_hash,
            key_id=record.key_id,
            plaintext=image_bytes,
        )
        record = self.database.mark_stored(
            content_id=record.envelope.content_id,
            owner_id=resolved_owner,
            blob_name=stored.blob_name,
            key_id=stored.key_id,
            now=now,
        )
        # The filesystem and SQLite cannot share a transaction. If a concurrent
        # deletion won after the received row was read, do not strand the late
        # ciphertext. Never remove a blob that the canonical row references.
        if record.blob_name != stored.blob_name:
            try:
                blobs.delete(stored.blob_name)
            except Exception as exc:
                code = exc.code if isinstance(exc, MemoryPipelineError) else "orphan_cleanup_failed"
                self.database.record_orphan_cleanup_failure(
                    content_id=record.envelope.content_id,
                    owner_id=resolved_owner,
                    blob_name=stored.blob_name,
                    key_id=stored.key_id,
                    error_code=code,
                    now=self.clock().astimezone(UTC),
                )
                record = self.database.get(record.envelope.content_id, resolved_owner)
        return record.envelope, created

    def process_next(self, *, owner_id: str | None = None) -> MemoryRecord | None:
        resolved_owner = self._owner(owner_id)
        now = self.clock().astimezone(UTC)
        record = self.database.claim_next(
            owner_id=resolved_owner,
            now=now,
            lease_seconds=self.config.lease_seconds,
            max_retries=self.config.max_retries,
        )
        if record is None:
            return None
        assert record.lease_token is not None
        lease_token = record.lease_token
        heartbeat = _LeaseHeartbeat(
            lambda: self.database.renew_processing_lease(
                content_id=record.envelope.content_id,
                owner_id=resolved_owner,
                lease_token=lease_token,
                clock=self.clock,
                lease_seconds=self.config.lease_seconds,
            ),
            interval_seconds=self._heartbeat_interval_seconds,
        )
        heartbeat.start()
        try:
            self._refresh_keyring()
            blobs = self._require_blobs()
            if record.blob_name is None:
                raise EncryptionKeyUnavailable("The encrypted screenshot reference is unavailable.")
            image_bytes = blobs.read(
                blob_name=record.blob_name,
                owner_id=resolved_owner,
                content_id=record.envelope.content_id,
                content_hash=record.envelope.content_hash,
            )
            metadata, local_caption = self.image_provider.describe(image_bytes)
            raw_text = self.ocr_provider.extract_text(image_bytes)
            redacted_text = redact_text(raw_text, self.config.exclusion_terms)
            # Exercise the selected local embedding boundary without persisting its vector in v1.
            self.embedding_provider.embed(redacted_text)
            caption = local_caption
            provider_version = self.config.provider_version
            if self.config.remote_enabled:
                request_payload = RemoteProcessingRequest(
                    content_id=record.envelope.content_id,
                    metadata=metadata,
                    policy_version=self.config.policy_version,
                    redacted_text=redacted_text,
                    idempotency_key="0" * 64,
                ).model_dump(mode="json", exclude={"idempotency_key"})
                idempotency_key = hashlib.sha256(
                    json.dumps(request_payload, sort_keys=True, separators=(",", ":")).encode(
                        "utf-8"
                    )
                ).hexdigest()
                remote_request = RemoteProcessingRequest.model_validate(
                    {**request_payload, "idempotency_key": idempotency_key}, strict=True
                )
                remote_response = self.remote_provider.process(remote_request)
                # A remote caption remains untrusted evidence and may itself contain
                # invented sensitive-looking text, so apply the local redactor again.
                caption = redact_text(remote_response.caption, self.config.exclusion_terms)
                provider_version = f"{self.config.provider_version}:{self.remote_provider.name}"
            heartbeat.ensure_owned()
            return self.database.mark_processed(
                content_id=record.envelope.content_id,
                owner_id=resolved_owner,
                lease_token=lease_token,
                redacted_text=redacted_text,
                caption=caption,
                image_metadata=metadata,
                provider_version=provider_version,
                now=self.clock().astimezone(UTC),
            )
        except LeaseConflict:
            # Another worker already recovered this lease; stale work must not mutate it.
            raise
        except Exception as exc:
            heartbeat.ensure_owned()
            return self._record_processing_failure(record, resolved_owner, exc)
        finally:
            heartbeat.stop()

    def _record_processing_failure(
        self, record: MemoryRecord, owner_id: str, error: Exception
    ) -> MemoryRecord:
        now = self.clock().astimezone(UTC)
        attempt = record.envelope.retry_count + 1
        if isinstance(error, MemoryPipelineError):
            code = error.code
            message = error.public_message
            retryable = error.retryable and attempt <= self.config.max_retries
        else:
            code = "processing_failure"
            message = "Local processing failed without exposing screenshot content."
            retryable = False
        next_attempt_at = None
        if retryable:
            base_seconds = min(300, 2**attempt)
            jitter_millis = (
                int(
                    hashlib.sha256(f"{record.envelope.content_id}:{attempt}".encode()).hexdigest()[
                        :8
                    ],
                    16,
                )
                % 1_000
            )
            next_attempt_at = now + timedelta(seconds=base_seconds, milliseconds=jitter_millis)
        assert record.lease_token is not None
        return self.database.mark_failed(
            content_id=record.envelope.content_id,
            owner_id=owner_id,
            lease_token=record.lease_token,
            failure=FailureMetadata(
                code=code,
                message=message,
                retryable=retryable,
                occurred_at=now,
                attempt=attempt,
            ),
            next_attempt_at=next_attempt_at,
            now=now,
        )

    def search(self, query: str, *, owner_id: str | None = None, limit: int = 10) -> SearchResponse:
        resolved_owner = self._owner(owner_id)
        terms = search_terms(query)
        if not terms:
            return SearchResponse(
                answer="There is not enough query evidence to search local memory.",
                evidence=[],
                insufficient_evidence=True,
            )
        candidates = self.database.searchable(
            owner_id=resolved_owner, now=self.clock().astimezone(UTC)
        )
        hits: list[SearchHit] = []
        for record in candidates:
            searchable_text = " ".join(
                part for part in (record.redacted_text, record.caption) if part
            )
            matched = terms & search_terms(searchable_text)
            if not matched:
                continue
            score = len(matched) * 10_000 // len(terms)
            hits.append(
                SearchHit(
                    source_id=record.envelope.content_id,
                    captured_at=record.envelope.captured_at,
                    excerpt=excerpt(searchable_text, matched),
                    score=score,
                )
            )
        hits.sort(key=lambda hit: (-hit.score, -hit.captured_at.timestamp(), hit.source_id))
        hits = hits[: max(1, min(limit, 50))]
        if not hits:
            return SearchResponse(
                answer="No active local memory contains enough matching evidence.",
                evidence=[],
                insufficient_evidence=True,
            )
        return SearchResponse(
            answer=(
                f"Found {len(hits)} local memory "
                f"source{'s' if len(hits) != 1 else ''}; review the cited evidence."
            ),
            evidence=hits,
            insufficient_evidence=False,
        )

    def _store_deletion_heartbeat(
        self,
        *,
        content_id: str,
        store: str,
        lease_token: str,
    ) -> _LeaseHeartbeat:
        def renew_store() -> None:
            self.database.renew_store_deletion_lease(
                content_id=content_id,
                store=store,
                lease_token=lease_token,
                clock=self.clock,
                lease_seconds=self.config.lease_seconds,
            )

        return _LeaseHeartbeat(
            renew_store,
            interval_seconds=self._heartbeat_interval_seconds,
        )

    def delete(self, content_id: str, *, owner_id: str | None = None) -> DeletionReceipt:
        resolved_owner = self._owner(owner_id)
        now = self.clock().astimezone(UTC)
        record = self.database.begin_deletion(
            content_id=content_id,
            owner_id=resolved_owner,
            stores=DELETION_STORES,
            now=now,
        )
        for store in DELETION_STORES:
            lease_token = self.database.claim_store_deletion(
                content_id=content_id,
                owner_id=resolved_owner,
                store=store,
                now=self.clock().astimezone(UTC),
                lease_seconds=self.config.lease_seconds,
            )
            if lease_token is None:
                continue

            heartbeat = self._store_deletion_heartbeat(
                content_id=content_id,
                store=store,
                lease_token=lease_token,
            )
            heartbeat.start()
            try:
                if store == "encrypted_blob":
                    if record.blob_name:
                        delete_encrypted_blob(self.config.blob_root, record.blob_name)
                    state = DeletionState.COMPLETE
                elif store == "local_index":
                    # begin_deletion tombstones and removes searchable text atomically.
                    state = DeletionState.COMPLETE
                else:
                    adapter = self.deletion_adapters.get(store)
                    if adapter is None:
                        state = DeletionState.NOT_CONFIGURED
                    else:
                        adapter.delete(owner_id=resolved_owner, content_id=content_id)
                        state = DeletionState.COMPLETE
                heartbeat.ensure_owned()
                self.database.record_store_deletion(
                    content_id=content_id,
                    store=store,
                    lease_token=lease_token,
                    state=state,
                    error_code=None,
                    now=self.clock().astimezone(UTC),
                )
            except LeaseConflict:
                # A recovered worker owns the canonical store outcome now.
                continue
            except Exception as exc:
                try:
                    heartbeat.ensure_owned()
                except LeaseConflict:
                    continue
                code = exc.code if isinstance(exc, MemoryPipelineError) else "adapter_delete_failed"
                self.database.record_store_deletion(
                    content_id=content_id,
                    store=store,
                    lease_token=lease_token,
                    state=DeletionState.FAILED,
                    error_code=code,
                    now=self.clock().astimezone(UTC),
                )
            finally:
                heartbeat.stop()
        return self.database.finalize_deletion(
            content_id=content_id,
            owner_id=resolved_owner,
            now=self.clock().astimezone(UTC),
        )

    def sweep_expired(
        self, *, owner_id: str | None = None, limit: int = 100
    ) -> list[DeletionReceipt]:
        resolved_owner = self._owner(owner_id)
        content_ids = self.database.expired_content_ids(
            owner_id=resolved_owner,
            now=self.clock().astimezone(UTC),
            limit=max(1, min(limit, 1_000)),
        )
        return [self.delete(content_id, owner_id=resolved_owner) for content_id in content_ids]

    def status(self, *, owner_id: str | None = None) -> PrivacyStatus:
        resolved_owner = self._owner(owner_id)
        warnings: list[str] = []
        with suppress(EncryptionKeyUnavailable):
            self._refresh_keyring()
        if self.keyring is None:
            warnings.append("Encryption key unavailable: ingestion and decryption fail closed.")
        if self.config.remote_enabled:
            warnings.append(
                "Remote processing is enabled by explicit configuration; only locally "
                "redacted text and metadata are sent."
            )
        else:
            warnings.append("Local-only mode: no remote processing or telemetry is configured.")
        return PrivacyStatus(
            mode="remote-enabled" if self.config.remote_enabled else "local-only",
            remote_enabled=self.config.remote_enabled,
            providers={
                "ocr": self.ocr_provider.name,
                "image_understanding": self.image_provider.name,
                "embeddings": self.embedding_provider.name,
                "source_observation": self.source_observation_provider.name,
                "remote": self.remote_provider.name,
            },
            default_retention_days=self.config.default_retention_days,
            queue_counts=self.database.state_counts(resolved_owner),
            deletion_counts=self.database.deletion_counts(resolved_owner),
            active_key_id=self.keyring.active_key_id if self.keyring else None,
            key_available=self.keyring is not None,
            warnings=warnings,
        )

    def rotate_key(self) -> str:
        self._require_blobs()
        with self._keyring_lock:
            self.keyring = rotate_keyring(self.config.keyring_path)
            self.blobs = EncryptedBlobStore(self.config.blob_root, self.keyring)
        self._key_error = None
        return self.keyring.active_key_id

    def local_data_paths(self) -> tuple[Path, Path, Path]:
        """Documented paths for backup tooling; never returned by the public status API."""
        return self.config.database_path, self.config.blob_root, self.config.keyring_path
