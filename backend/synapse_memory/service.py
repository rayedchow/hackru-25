"""Orchestration for encrypted ingest, local processing, search, and deletion."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import MemoryConfig
from .crypto import (
    EncryptedBlobStore,
    Keyring,
    delete_encrypted_blob,
    load_or_create_keyring,
    rotate_keyring,
)
from .database import MemoryDatabase, MemoryRecord
from .errors import EncryptionKeyUnavailable, InvalidUpload, LeaseConflict, MemoryPipelineError
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
    EmbeddingProvider,
    HTTPRemoteProvider,
    ImageUnderstandingProvider,
    OCRProvider,
    RemoteProcessingProvider,
    TesseractOCRProvider,
)

Clock = Callable[[], datetime]
DELETION_STORES = ("encrypted_blob", "local_index", "vector", "graph")


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
        deletion_adapters: Mapping[str, DeletionAdapter] | None = None,
        keyring: Keyring | None = None,
    ) -> None:
        self.config = config
        self.clock = clock
        self.database = MemoryDatabase(config.database_path)
        self.database.migrate_up()
        self.ocr_provider = ocr_provider or TesseractOCRProvider()
        self.image_provider = image_provider or DeterministicImageProvider()
        self.embedding_provider = embedding_provider or DeterministicHashEmbeddingProvider()
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
        blobs = self._require_blobs()
        if not image_bytes:
            raise InvalidUpload("The screenshot payload is empty.")
        if len(image_bytes) > self.config.max_upload_bytes:
            raise InvalidUpload("The screenshot exceeds the configured upload limit.")
        # Decode before any durable write. This also rejects non-image payloads.
        self.image_provider.describe(image_bytes)
        normalized_source = enforce_source_policy(source, self.config.denied_sources)
        resolved_owner = self._owner(owner_id)
        now = self.clock().astimezone(UTC)
        content_hash = blobs.content_hash(image_bytes)
        content_id = self._content_id(resolved_owner, content_hash)
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
        record, created = self.database.create_received(envelope, owner_id=resolved_owner, now=now)
        # A replay observes the canonical state. In particular, an upload must not
        # turn a terminal or delayed failure back into an immediately claimable item
        # and thereby bypass the bounded retry policy.
        if record.envelope.state is not ProcessingState.RECEIVED:
            return record.envelope, False
        stored = blobs.store(
            owner_id=resolved_owner,
            content_id=record.envelope.content_id,
            content_hash=record.envelope.content_hash,
            plaintext=image_bytes,
        )
        record = self.database.mark_stored(
            content_id=record.envelope.content_id,
            owner_id=resolved_owner,
            blob_name=stored.blob_name,
            key_id=stored.key_id,
            now=now,
        )
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
        try:
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
            return self.database.mark_processed(
                content_id=record.envelope.content_id,
                owner_id=resolved_owner,
                lease_token=record.lease_token,
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
            return self._record_processing_failure(record, resolved_owner, exc)

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

    def delete(self, content_id: str, *, owner_id: str | None = None) -> DeletionReceipt:
        resolved_owner = self._owner(owner_id)
        now = self.clock().astimezone(UTC)
        record = self.database.begin_deletion(
            content_id=content_id,
            owner_id=resolved_owner,
            stores=DELETION_STORES,
            now=now,
        )
        receipt = self.database.deletion_receipt(content_id=content_id, owner_id=resolved_owner)
        status_by_store = {status.store: status for status in receipt.stores}
        for store in DELETION_STORES:
            status = status_by_store[store]
            if status.state in {DeletionState.COMPLETE, DeletionState.NOT_CONFIGURED}:
                continue
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
                self.database.record_store_deletion(
                    content_id=content_id,
                    store=store,
                    state=state,
                    error_code=None,
                    now=self.clock().astimezone(UTC),
                )
            except Exception as exc:
                code = exc.code if isinstance(exc, MemoryPipelineError) else "adapter_delete_failed"
                self.database.record_store_deletion(
                    content_id=content_id,
                    store=store,
                    state=DeletionState.FAILED,
                    error_code=code,
                    now=self.clock().astimezone(UTC),
                )
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
        self.keyring = rotate_keyring(self.config.keyring_path)
        self.blobs = EncryptedBlobStore(self.config.blob_root, self.keyring)
        self._key_error = None
        return self.keyring.active_key_id

    def local_data_paths(self) -> tuple[Path, Path, Path]:
        """Documented paths for backup tooling; never returned by the public status API."""
        return self.config.database_path, self.config.blob_root, self.config.keyring_path
