"""Fail-closed local configuration for Synapse memory."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .errors import ConfigurationError

DEFAULT_MAX_UPLOAD_BYTES = 8 * 1024 * 1024
DEFAULT_LEASE_SECONDS = 60
DEFAULT_MAX_RETRIES = 3


def _is_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(name: str, raw: str | None, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw) if raw is not None else default
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _csv_values(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    values = {part.strip().casefold() for part in raw.split(",") if part.strip()}
    return tuple(sorted(values))


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    data_root: Path
    owner_id: str = "local-owner"
    remote_enabled: bool = False
    remote_endpoint: str | None = None
    remote_timeout_seconds: int = 10
    default_retention_days: int = 30
    session_retention_days: int = 1
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    lease_seconds: int = DEFAULT_LEASE_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    auto_create_key: bool = True
    consent_version: str = "local-consent-v1"
    provider_version: str = "local-v1"
    policy_version: str = "privacy-v1"
    denied_sources: tuple[str, ...] = field(default_factory=tuple)
    exclusion_terms: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.owner_id or len(self.owner_id) > 96:
            raise ConfigurationError("SYNAPSE_OWNER_ID must contain 1-96 characters.")
        bounds = (
            ("remote_timeout_seconds", self.remote_timeout_seconds, 1, 60),
            ("default_retention_days", self.default_retention_days, 1, 3_650),
            ("session_retention_days", self.session_retention_days, 1, 30),
            ("max_upload_bytes", self.max_upload_bytes, 1_024, 32 * 1024 * 1024),
            ("lease_seconds", self.lease_seconds, 5, 3_600),
            ("max_retries", self.max_retries, 0, 10),
        )
        for name, value, minimum, maximum in bounds:
            if not minimum <= value <= maximum:
                raise ConfigurationError(f"{name} must be between {minimum} and {maximum}.")
        if self.remote_enabled and not self.remote_endpoint:
            raise ConfigurationError(
                "Remote processing requires both SYNAPSE_REMOTE_ENABLED=true "
                "and SYNAPSE_REMOTE_ENDPOINT."
            )
        if self.remote_endpoint:
            parsed = urlparse(self.remote_endpoint)
            is_loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            if parsed.scheme not in {"https", "http"} or not parsed.hostname:
                raise ConfigurationError("SYNAPSE_REMOTE_ENDPOINT must be an absolute HTTP(S) URL.")
            if parsed.scheme != "https" and not is_loopback:
                raise ConfigurationError("Non-loopback remote processing endpoints must use HTTPS.")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ConfigurationError(
                    "SYNAPSE_REMOTE_ENDPOINT must not embed credentials, query parameters, "
                    "or fragments."
                )

    @property
    def database_path(self) -> Path:
        return self.data_root / "memory.sqlite3"

    @property
    def blob_root(self) -> Path:
        return self.data_root / "blobs"

    @property
    def keyring_path(self) -> Path:
        return self.data_root / "keyring.json"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> MemoryConfig:
        env = os.environ if environ is None else environ
        default_root = Path(__file__).resolve().parent.parent / "private_data"
        data_root = Path(env.get("SYNAPSE_DATA_ROOT", str(default_root))).expanduser().resolve()
        remote_enabled = _is_enabled(env.get("SYNAPSE_REMOTE_ENABLED"))
        return cls(
            data_root=data_root,
            owner_id=env.get("SYNAPSE_OWNER_ID", "local-owner").strip(),
            remote_enabled=remote_enabled,
            remote_endpoint=env.get("SYNAPSE_REMOTE_ENDPOINT") or None,
            remote_timeout_seconds=_bounded_int(
                "SYNAPSE_REMOTE_TIMEOUT_SECONDS",
                env.get("SYNAPSE_REMOTE_TIMEOUT_SECONDS"),
                10,
                1,
                60,
            ),
            default_retention_days=_bounded_int(
                "SYNAPSE_DEFAULT_RETENTION_DAYS",
                env.get("SYNAPSE_DEFAULT_RETENTION_DAYS"),
                30,
                1,
                3_650,
            ),
            session_retention_days=_bounded_int(
                "SYNAPSE_SESSION_RETENTION_DAYS",
                env.get("SYNAPSE_SESSION_RETENTION_DAYS"),
                1,
                1,
                30,
            ),
            max_upload_bytes=_bounded_int(
                "SYNAPSE_MAX_UPLOAD_BYTES",
                env.get("SYNAPSE_MAX_UPLOAD_BYTES"),
                DEFAULT_MAX_UPLOAD_BYTES,
                1_024,
                32 * 1024 * 1024,
            ),
            lease_seconds=_bounded_int(
                "SYNAPSE_LEASE_SECONDS",
                env.get("SYNAPSE_LEASE_SECONDS"),
                DEFAULT_LEASE_SECONDS,
                5,
                3_600,
            ),
            max_retries=_bounded_int(
                "SYNAPSE_MAX_RETRIES",
                env.get("SYNAPSE_MAX_RETRIES"),
                DEFAULT_MAX_RETRIES,
                0,
                10,
            ),
            auto_create_key=not _is_enabled(env.get("SYNAPSE_DISABLE_KEY_AUTOCREATE")),
            denied_sources=_csv_values(env.get("SYNAPSE_DENIED_SOURCES")),
            exclusion_terms=_csv_values(env.get("SYNAPSE_EXCLUSION_TERMS")),
        )
