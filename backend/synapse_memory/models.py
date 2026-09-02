"""Versioned schemas for local memory ingestion and deletion."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

SCHEMA_VERSION: Literal["1"] = "1"
HexDigest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
OpaqueIdentifier = Annotated[
    str, StringConstraints(min_length=8, max_length=96, pattern=r"^[A-Za-z0-9_.:-]+$")
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProcessingState(StrEnum):
    RECEIVED = "received"
    STORED = "stored"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class RetentionClass(StrEnum):
    SESSION = "session"
    STANDARD = "standard"
    KEEP = "keep"


class DeletionState(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


class FailureMetadata(StrictModel):
    code: Annotated[str, StringConstraints(min_length=3, max_length=64)]
    message: Annotated[str, StringConstraints(min_length=1, max_length=240)]
    retryable: bool
    occurred_at: datetime
    attempt: Annotated[int, Field(ge=0, le=100)]

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(UTC)


class IngestionEnvelope(StrictModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    content_id: OpaqueIdentifier
    content_hash: HexDigest
    captured_at: datetime
    device_pseudonym: OpaqueIdentifier
    state: ProcessingState
    consent_version: OpaqueIdentifier
    retention_class: RetentionClass
    expires_at: datetime | None
    provider_version: OpaqueIdentifier
    policy_version: OpaqueIdentifier
    retry_count: Annotated[int, Field(ge=0, le=100)] = 0
    version: Annotated[int, Field(ge=0)] = 0
    failure: FailureMetadata | None = None

    @field_validator("captured_at", "expires_at")
    @classmethod
    def normalize_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(UTC)


class ImageMetadata(StrictModel):
    width: Annotated[int, Field(gt=0, le=20_000)]
    height: Annotated[int, Field(gt=0, le=20_000)]
    format: Annotated[str, StringConstraints(min_length=1, max_length=16)]
    mode: Annotated[str, StringConstraints(min_length=1, max_length=16)]


class ProcessedEvidence(StrictModel):
    source_id: OpaqueIdentifier
    redacted_text: Annotated[str, StringConstraints(max_length=20_000)]
    caption: Annotated[str, StringConstraints(max_length=2_000)]
    metadata: ImageMetadata
    applied_policy_version: OpaqueIdentifier
    provider_version: OpaqueIdentifier


class RemoteProcessingRequest(StrictModel):
    schema_version: Literal["1"] = SCHEMA_VERSION
    content_id: OpaqueIdentifier
    redacted_text: Annotated[str, StringConstraints(max_length=20_000)]
    metadata: ImageMetadata
    policy_version: OpaqueIdentifier
    idempotency_key: HexDigest


class RemoteProcessingResponse(StrictModel):
    schema_version: Literal["1"]
    caption: Annotated[str, StringConstraints(min_length=1, max_length=2_000)]
    tags: Annotated[
        list[Annotated[str, StringConstraints(min_length=1, max_length=64)]],
        Field(max_length=32),
    ] = Field(default_factory=list)


class MemorySummary(StrictModel):
    """Public lifecycle view that deliberately omits the raw screenshot digest."""

    schema_version: Literal["1"] = SCHEMA_VERSION
    content_id: OpaqueIdentifier
    captured_at: datetime
    device_pseudonym: OpaqueIdentifier
    state: ProcessingState
    consent_version: OpaqueIdentifier
    retention_class: RetentionClass
    expires_at: datetime | None
    provider_version: OpaqueIdentifier
    policy_version: OpaqueIdentifier
    retry_count: Annotated[int, Field(ge=0, le=100)]
    version: Annotated[int, Field(ge=0)]
    failure: FailureMetadata | None

    @classmethod
    def from_envelope(cls, envelope: IngestionEnvelope) -> MemorySummary:
        return cls.model_validate(
            envelope.model_dump(exclude={"content_hash"}),
            strict=True,
        )


class SearchHit(StrictModel):
    source_id: OpaqueIdentifier
    captured_at: datetime
    excerpt: Annotated[str, StringConstraints(max_length=500)]
    score: Annotated[int, Field(ge=0, le=10_000)]


class SearchResponse(StrictModel):
    answer: Annotated[str, StringConstraints(min_length=1, max_length=1_000)]
    evidence: list[SearchHit]
    insufficient_evidence: bool


class DeletionStoreStatus(StrictModel):
    store: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    state: DeletionState
    attempts: Annotated[int, Field(ge=0, le=100)]
    last_error_code: Annotated[str, StringConstraints(max_length=64)] | None = None


class DeletionReceipt(StrictModel):
    content_id: OpaqueIdentifier
    state: ProcessingState
    complete: bool
    stores: list[DeletionStoreStatus]


class PrivacyStatus(StrictModel):
    mode: Literal["local-only", "remote-enabled"]
    remote_enabled: bool
    providers: dict[str, str]
    default_retention_days: Annotated[int, Field(ge=1, le=3_650)]
    queue_counts: dict[str, Annotated[int, Field(ge=0)]]
    deletion_counts: dict[str, Annotated[int, Field(ge=0)]]
    active_key_id: OpaqueIdentifier | None
    key_available: bool
    warnings: list[str]


class ErrorResponse(StrictModel):
    ok: Literal[False] = False
    error: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    message: Annotated[str, StringConstraints(min_length=1, max_length=240)]
