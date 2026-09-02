"""Structured failures at Synapse trust boundaries."""

from __future__ import annotations


class MemoryPipelineError(Exception):
    """Base error with a stable public code and safe message."""

    code = "memory_pipeline_error"
    status_code = 500
    retryable = False

    def __init__(self, message: str | None = None) -> None:
        self.public_message = message or "The memory operation failed."
        super().__init__(self.public_message)


class ConfigurationError(MemoryPipelineError):
    code = "configuration_error"
    status_code = 503


class EncryptionKeyUnavailable(ConfigurationError):
    code = "encryption_key_unavailable"


class StorageIntegrityError(MemoryPipelineError):
    code = "storage_integrity_error"
    status_code = 422


class InvalidUpload(MemoryPipelineError):
    code = "invalid_upload"
    status_code = 400


class ContentDenied(MemoryPipelineError):
    code = "content_denied"
    status_code = 403


class ItemNotFound(MemoryPipelineError):
    code = "item_not_found"
    status_code = 404


class OwnerMismatch(MemoryPipelineError):
    code = "owner_mismatch"
    status_code = 403


class LeaseConflict(MemoryPipelineError):
    code = "lease_conflict"
    status_code = 409


class RemoteProcessingDisabled(MemoryPipelineError):
    code = "remote_processing_disabled"
    status_code = 409


class RemoteResponseInvalid(MemoryPipelineError):
    code = "remote_response_invalid"
    status_code = 502


class ProviderTimeout(MemoryPipelineError):
    code = "provider_timeout"
    status_code = 504
    retryable = True


class ProviderUnavailable(MemoryPipelineError):
    code = "provider_unavailable"
    status_code = 503
    retryable = True


class AmbiguousRemoteFailure(MemoryPipelineError):
    """The remote side may have received a request; never blindly retry."""

    code = "ambiguous_remote_failure"
    status_code = 502
