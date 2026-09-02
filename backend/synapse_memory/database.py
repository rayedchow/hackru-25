"""SQLite state machine for crash-safe local memory processing."""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .errors import ItemNotFound, LeaseConflict, OwnerMismatch
from .models import (
    DeletionReceipt,
    DeletionState,
    DeletionStoreStatus,
    FailureMetadata,
    ImageMetadata,
    IngestionEnvelope,
    ProcessingState,
    RetentionClass,
)

DATABASE_SCHEMA_VERSION = 1
MAX_DELETION_ATTEMPTS = 100
STATE_VALUES = tuple(state.value for state in ProcessingState)
RETENTION_VALUES = tuple(value.value for value in RetentionClass)
DELETION_VALUES = tuple(value.value for value in DeletionState)


def _sql_values(values: Sequence[str]) -> str:
    return ",".join(f"'{value}'" for value in values)


SCHEMA_V1 = f"""
CREATE TABLE IF NOT EXISTS memory_items (
    content_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    content_hash TEXT NOT NULL CHECK(length(content_hash) = 64),
    captured_at TEXT NOT NULL,
    device_pseudonym TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ({_sql_values(STATE_VALUES)})),
    consent_version TEXT NOT NULL,
    retention_class TEXT NOT NULL CHECK(retention_class IN ({_sql_values(RETENTION_VALUES)})),
    expires_at TEXT,
    provider_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK(retry_count >= 0),
    version INTEGER NOT NULL DEFAULT 0 CHECK(version >= 0),
    failure_code TEXT,
    failure_message TEXT,
    failure_retryable INTEGER,
    failure_at TEXT,
    failure_attempt INTEGER,
    blob_name TEXT,
    key_id TEXT,
    lease_token TEXT,
    lease_expires_at TEXT,
    next_attempt_at TEXT,
    redacted_text TEXT,
    caption TEXT,
    image_metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_id, content_hash)
);

CREATE INDEX IF NOT EXISTS memory_items_claim_idx
ON memory_items(owner_id, state, next_attempt_at, lease_expires_at, captured_at);

CREATE INDEX IF NOT EXISTS memory_items_expiry_idx
ON memory_items(state, expires_at);

CREATE TABLE IF NOT EXISTS deletion_status (
    content_id TEXT NOT NULL REFERENCES memory_items(content_id) ON DELETE CASCADE,
    store TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ({_sql_values(DELETION_VALUES)})),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    last_error_code TEXT,
    lease_token TEXT,
    lease_expires_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(content_id, store)
);
"""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("database timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return _utc(value).isoformat() if value is not None else None


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(UTC) if value else None


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    envelope: IngestionEnvelope
    owner_id: str
    blob_name: str | None
    key_id: str | None
    lease_token: str | None
    lease_expires_at: datetime | None
    next_attempt_at: datetime | None
    redacted_text: str | None
    caption: str | None
    image_metadata: ImageMetadata | None


class MemoryDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with suppress(OSError):
            self.path.parent.chmod(0o700)
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        for path in (
            self.path,
            self.path.with_name(self.path.name + "-wal"),
            self.path.with_name(self.path.name + "-shm"),
        ):
            with suppress(OSError):
                path.chmod(0o600)
        return connection

    @contextmanager
    def _transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def migrate_up(self) -> None:
        with self._transaction(immediate=True) as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > DATABASE_SCHEMA_VERSION:
                raise RuntimeError(f"unsupported database schema version {version}")
            if version == 0:
                # ``executescript`` commits an active transaction implicitly. Execute this
                # repository-owned schema statement-by-statement so DDL and the version
                # marker remain one rollback-safe migration.
                for statement in SCHEMA_V1.split(";"):
                    if statement.strip():
                        connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION}")

    def migrate_down(self) -> None:
        with self._transaction(immediate=True) as connection:
            connection.execute("DROP TABLE IF EXISTS deletion_status")
            connection.execute("DROP TABLE IF EXISTS memory_items")
            connection.execute("PRAGMA user_version = 0")

    def schema_version(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])

    def create_received(
        self,
        envelope: IngestionEnvelope,
        *,
        owner_id: str,
        blob_name: str,
        key_id: str,
        now: datetime,
    ) -> tuple[MemoryRecord, bool]:
        timestamp = _iso(now)
        with self._transaction(immediate=True) as connection:
            cursor = connection.execute(
                """
                INSERT INTO memory_items (
                    content_id, owner_id, content_hash, captured_at, device_pseudonym,
                    state, consent_version, retention_class, expires_at,
                    provider_version, policy_version, retry_count, version, blob_name, key_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_id, content_hash) DO NOTHING
                """,
                (
                    envelope.content_id,
                    owner_id,
                    envelope.content_hash,
                    _iso(envelope.captured_at),
                    envelope.device_pseudonym,
                    envelope.state.value,
                    envelope.consent_version,
                    envelope.retention_class.value,
                    _iso(envelope.expires_at),
                    envelope.provider_version,
                    envelope.policy_version,
                    envelope.retry_count,
                    envelope.version,
                    blob_name,
                    key_id,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                "SELECT * FROM memory_items WHERE owner_id = ? AND content_hash = ?",
                (owner_id, envelope.content_hash),
            ).fetchone()
            assert row is not None
            return self._record(row), cursor.rowcount == 1

    def mark_stored(
        self,
        *,
        content_id: str,
        owner_id: str,
        blob_name: str,
        key_id: str,
        now: datetime,
    ) -> MemoryRecord:
        with self._transaction(immediate=True) as connection:
            cursor = connection.execute(
                """
                UPDATE memory_items
                SET state = ?, blob_name = ?, key_id = ?, failure_code = NULL,
                    failure_message = NULL, failure_retryable = NULL, failure_at = NULL,
                    failure_attempt = NULL, updated_at = ?, version = version + 1
                WHERE content_id = ? AND owner_id = ?
                  AND state = ?
                """,
                (
                    ProcessingState.STORED.value,
                    blob_name,
                    key_id,
                    _iso(now),
                    content_id,
                    owner_id,
                    ProcessingState.RECEIVED.value,
                ),
            )
            if cursor.rowcount != 1:
                return self._owned_record(connection, content_id, owner_id)
            return self._owned_record(connection, content_id, owner_id)

    def get(self, content_id: str, owner_id: str) -> MemoryRecord:
        with self._connect() as connection:
            return self._owned_record(connection, content_id, owner_id)

    def claim_next(
        self, *, owner_id: str, now: datetime, lease_seconds: int, max_retries: int
    ) -> MemoryRecord | None:
        now_text = _iso(now)
        with self._transaction(immediate=True) as connection:
            # A repeatedly crashing worker must not leave an item in ``processing``
            # forever. Once all configured recovery claims are consumed, make the
            # terminal failure explicit before looking for the next item.
            connection.execute(
                """
                UPDATE memory_items
                SET state = ?, failure_code = ?, failure_message = ?,
                    failure_retryable = 0, failure_at = ?,
                    failure_attempt = retry_count + 1,
                    lease_token = NULL, lease_expires_at = NULL,
                    next_attempt_at = NULL, updated_at = ?, version = version + 1
                WHERE owner_id = ? AND state = ? AND lease_expires_at < ?
                  AND retry_count >= ?
                """,
                (
                    ProcessingState.FAILED.value,
                    "lease_retries_exhausted",
                    "Processing stopped after the configured crash-recovery limit.",
                    now_text,
                    now_text,
                    owner_id,
                    ProcessingState.PROCESSING.value,
                    now_text,
                    max_retries,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM memory_items
                WHERE owner_id = ?
                  AND (
                    state = ?
                    OR (
                      state = ? AND failure_retryable = 1 AND retry_count <= ?
                      AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                    )
                    OR (state = ? AND lease_expires_at < ? AND retry_count < ?)
                  )
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY captured_at, content_id
                LIMIT 1
                """,
                (
                    owner_id,
                    ProcessingState.STORED.value,
                    ProcessingState.FAILED.value,
                    max_retries,
                    now_text,
                    ProcessingState.PROCESSING.value,
                    now_text,
                    max_retries,
                    now_text,
                ),
            ).fetchone()
            if row is None:
                return None
            lease_token = secrets.token_urlsafe(24)
            lease_expires_at = now + timedelta(seconds=lease_seconds)
            cursor = connection.execute(
                """
                UPDATE memory_items
                SET state = ?, lease_token = ?, lease_expires_at = ?,
                    retry_count = retry_count + CASE WHEN state = ? THEN 1 ELSE 0 END,
                    updated_at = ?, version = version + 1
                WHERE content_id = ? AND version = ?
                """,
                (
                    ProcessingState.PROCESSING.value,
                    lease_token,
                    _iso(lease_expires_at),
                    ProcessingState.PROCESSING.value,
                    now_text,
                    row["content_id"],
                    row["version"],
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseConflict("Another worker claimed this memory.")
            claimed = connection.execute(
                "SELECT * FROM memory_items WHERE content_id = ?", (row["content_id"],)
            ).fetchone()
            assert claimed is not None
            return self._record(claimed)

    def mark_processed(
        self,
        *,
        content_id: str,
        owner_id: str,
        lease_token: str,
        redacted_text: str,
        caption: str,
        image_metadata: ImageMetadata,
        provider_version: str,
        now: datetime,
    ) -> MemoryRecord:
        with self._transaction(immediate=True) as connection:
            cursor = connection.execute(
                """
                UPDATE memory_items
                SET state = ?, redacted_text = ?, caption = ?, image_metadata_json = ?,
                    provider_version = ?, lease_token = NULL, lease_expires_at = NULL,
                    next_attempt_at = NULL, failure_code = NULL, failure_message = NULL,
                    failure_retryable = NULL, failure_at = NULL, failure_attempt = NULL,
                    updated_at = ?, version = version + 1
                WHERE content_id = ? AND owner_id = ? AND state = ? AND lease_token = ?
                """,
                (
                    ProcessingState.PROCESSED.value,
                    redacted_text,
                    caption,
                    image_metadata.model_dump_json(),
                    provider_version,
                    _iso(now),
                    content_id,
                    owner_id,
                    ProcessingState.PROCESSING.value,
                    lease_token,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseConflict("The processing lease is stale or no longer owned.")
            return self._owned_record(connection, content_id, owner_id)

    def renew_processing_lease(
        self,
        *,
        content_id: str,
        owner_id: str,
        lease_token: str,
        clock: Callable[[], datetime],
        lease_seconds: int,
    ) -> None:
        """Extend a live processing claim without allowing stale-owner revival."""

        with self._transaction(immediate=True) as connection:
            now = _utc(clock())
            cursor = connection.execute(
                """
                UPDATE memory_items
                SET lease_expires_at = ?, updated_at = ?, version = version + 1
                WHERE content_id = ? AND owner_id = ? AND state = ? AND lease_token = ?
                """,
                (
                    _iso(now + timedelta(seconds=lease_seconds)),
                    _iso(now),
                    content_id,
                    owner_id,
                    ProcessingState.PROCESSING.value,
                    lease_token,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseConflict("The processing lease is stale or no longer owned.")

    def mark_failed(
        self,
        *,
        content_id: str,
        owner_id: str,
        lease_token: str,
        failure: FailureMetadata,
        next_attempt_at: datetime | None,
        now: datetime,
    ) -> MemoryRecord:
        with self._transaction(immediate=True) as connection:
            cursor = connection.execute(
                """
                UPDATE memory_items
                SET state = ?, retry_count = retry_count + 1, failure_code = ?,
                    failure_message = ?, failure_retryable = ?, failure_at = ?,
                    failure_attempt = ?, next_attempt_at = ?, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = ?, version = version + 1
                WHERE content_id = ? AND owner_id = ? AND state = ? AND lease_token = ?
                """,
                (
                    ProcessingState.FAILED.value,
                    failure.code,
                    failure.message,
                    int(failure.retryable),
                    _iso(failure.occurred_at),
                    failure.attempt,
                    _iso(next_attempt_at),
                    _iso(now),
                    content_id,
                    owner_id,
                    ProcessingState.PROCESSING.value,
                    lease_token,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseConflict("The processing lease is stale or no longer owned.")
            return self._owned_record(connection, content_id, owner_id)

    def searchable(self, *, owner_id: str, now: datetime, limit: int = 500) -> list[MemoryRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memory_items
                WHERE owner_id = ? AND state = ?
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY captured_at DESC, content_id
                LIMIT ?
                """,
                (owner_id, ProcessingState.PROCESSED.value, _iso(now), limit),
            ).fetchall()
            return [self._record(row) for row in rows]

    def begin_deletion(
        self,
        *,
        content_id: str,
        owner_id: str,
        stores: Sequence[str],
        now: datetime,
    ) -> MemoryRecord:
        with self._transaction(immediate=True) as connection:
            record = self._owned_record(connection, content_id, owner_id)
            if record.envelope.state is not ProcessingState.DELETED:
                connection.execute(
                    """
                    UPDATE memory_items
                    SET state = ?, redacted_text = NULL, caption = NULL,
                        image_metadata_json = NULL, lease_token = NULL,
                        lease_expires_at = NULL, next_attempt_at = NULL,
                        updated_at = ?, version = version + 1
                    WHERE content_id = ? AND owner_id = ?
                    """,
                    (ProcessingState.DELETING.value, _iso(now), content_id, owner_id),
                )
            for store in sorted(set(stores)):
                connection.execute(
                    """
                    INSERT INTO deletion_status (content_id, store, state, attempts, updated_at)
                    VALUES (?, ?, ?, 0, ?)
                    ON CONFLICT(content_id, store) DO NOTHING
                    """,
                    (content_id, store, DeletionState.PENDING.value, _iso(now)),
                )
            return self._owned_record(connection, content_id, owner_id)

    def record_store_deletion(
        self,
        *,
        content_id: str,
        store: str,
        lease_token: str,
        state: DeletionState,
        error_code: str | None,
        now: datetime,
    ) -> None:
        with self._transaction(immediate=True) as connection:
            if state not in {
                DeletionState.COMPLETE,
                DeletionState.FAILED,
                DeletionState.NOT_CONFIGURED,
            }:
                raise ValueError("a deletion claim may only finish in a terminal store state")
            cursor = connection.execute(
                """
                UPDATE deletion_status
                SET state = ?, last_error_code = ?, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE content_id = ? AND store = ? AND state = ? AND lease_token = ?
                """,
                (
                    state.value,
                    error_code,
                    _iso(now),
                    content_id,
                    store,
                    DeletionState.PROCESSING.value,
                    lease_token,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseConflict("The deletion-store lease is stale or no longer owned.")

    def claim_store_deletion(
        self,
        *,
        content_id: str,
        owner_id: str,
        store: str,
        now: datetime,
        lease_seconds: int,
        max_attempts: int = MAX_DELETION_ATTEMPTS,
    ) -> str | None:
        """Atomically claim one pending/failed or lease-expired store deletion."""

        with self._transaction(immediate=True) as connection:
            self._owned_record(connection, content_id, owner_id)
            row = connection.execute(
                "SELECT * FROM deletion_status WHERE content_id = ? AND store = ?",
                (content_id, store),
            ).fetchone()
            if row is None:
                raise ItemNotFound("The deletion store record does not exist.")
            eligible = row["state"] in {
                DeletionState.PENDING.value,
                DeletionState.FAILED.value,
            } or (
                row["state"] == DeletionState.PROCESSING.value
                and row["lease_expires_at"] is not None
                and row["lease_expires_at"] < _iso(now)
            )
            if eligible and row["attempts"] >= max_attempts:
                connection.execute(
                    """
                    UPDATE deletion_status
                    SET state = ?, last_error_code = ?, lease_token = NULL,
                        lease_expires_at = NULL, updated_at = ?
                    WHERE content_id = ? AND store = ? AND state = ? AND attempts = ?
                    """,
                    (
                        DeletionState.FAILED.value,
                        "deletion_attempts_exhausted",
                        _iso(now),
                        content_id,
                        store,
                        row["state"],
                        row["attempts"],
                    ),
                )
                return None
            if not eligible:
                return None
            lease_token = secrets.token_urlsafe(24)
            cursor = connection.execute(
                """
                UPDATE deletion_status
                SET state = ?, attempts = attempts + 1, last_error_code = NULL,
                    lease_token = ?, lease_expires_at = ?, updated_at = ?
                WHERE content_id = ? AND store = ? AND state = ?
                  AND attempts = ?
                  AND (lease_token IS ? OR lease_token = ?)
                """,
                (
                    DeletionState.PROCESSING.value,
                    lease_token,
                    _iso(now + timedelta(seconds=lease_seconds)),
                    _iso(now),
                    content_id,
                    store,
                    row["state"],
                    row["attempts"],
                    row["lease_token"],
                    row["lease_token"],
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseConflict("Another worker claimed this deletion store.")
            return lease_token

    def renew_store_deletion_lease(
        self,
        *,
        content_id: str,
        store: str,
        lease_token: str,
        clock: Callable[[], datetime],
        lease_seconds: int,
    ) -> None:
        with self._transaction(immediate=True) as connection:
            now = _utc(clock())
            cursor = connection.execute(
                """
                UPDATE deletion_status
                SET lease_expires_at = ?, updated_at = ?
                WHERE content_id = ? AND store = ? AND state = ? AND lease_token = ?
                """,
                (
                    _iso(now + timedelta(seconds=lease_seconds)),
                    _iso(now),
                    content_id,
                    store,
                    DeletionState.PROCESSING.value,
                    lease_token,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseConflict("The deletion-store lease is stale or no longer owned.")

    def record_orphan_cleanup_failure(
        self,
        *,
        content_id: str,
        owner_id: str,
        blob_name: str,
        key_id: str,
        error_code: str,
        now: datetime,
    ) -> None:
        """Keep a late ciphertext reference visible when compensating deletion fails."""

        with self._transaction(immediate=True) as connection:
            self._owned_record(connection, content_id, owner_id)
            cursor = connection.execute(
                """
                UPDATE memory_items
                SET state = ?, blob_name = ?, key_id = ?, updated_at = ?, version = version + 1
                WHERE content_id = ? AND owner_id = ? AND state IN (?, ?)
                """,
                (
                    ProcessingState.DELETING.value,
                    blob_name,
                    key_id,
                    _iso(now),
                    content_id,
                    owner_id,
                    ProcessingState.DELETING.value,
                    ProcessingState.DELETED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseConflict("The memory is no longer in a deletable cleanup state.")
            connection.execute(
                """
                INSERT INTO deletion_status (
                    content_id, store, state, attempts, last_error_code,
                    lease_token, lease_expires_at, updated_at
                ) VALUES (?, 'encrypted_blob', ?, 1, ?, NULL, NULL, ?)
                ON CONFLICT(content_id, store) DO UPDATE SET
                    state = excluded.state,
                    attempts = min(100, deletion_status.attempts + 1),
                    last_error_code = excluded.last_error_code,
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    updated_at = excluded.updated_at
                """,
                (content_id, DeletionState.FAILED.value, error_code, _iso(now)),
            )

    def finalize_deletion(
        self, *, content_id: str, owner_id: str, now: datetime
    ) -> DeletionReceipt:
        with self._transaction(immediate=True) as connection:
            record = self._owned_record(connection, content_id, owner_id)
            rows = connection.execute(
                "SELECT * FROM deletion_status WHERE content_id = ? ORDER BY store",
                (content_id,),
            ).fetchall()
            complete = bool(rows) and all(
                row["state"] in {DeletionState.COMPLETE.value, DeletionState.NOT_CONFIGURED.value}
                for row in rows
            )
            if complete and record.envelope.state is not ProcessingState.DELETED:
                connection.execute(
                    """
                    UPDATE memory_items
                    SET state = ?, blob_name = NULL, key_id = NULL, updated_at = ?,
                        version = version + 1
                    WHERE content_id = ? AND owner_id = ? AND state = ?
                    """,
                    (
                        ProcessingState.DELETED.value,
                        _iso(now),
                        content_id,
                        owner_id,
                        ProcessingState.DELETING.value,
                    ),
                )
            current = self._owned_record(connection, content_id, owner_id)
            return DeletionReceipt(
                content_id=content_id,
                state=current.envelope.state,
                complete=complete,
                stores=[
                    DeletionStoreStatus(
                        store=row["store"],
                        state=DeletionState(row["state"]),
                        attempts=row["attempts"],
                        last_error_code=row["last_error_code"],
                    )
                    for row in rows
                ],
            )

    def deletion_receipt(self, *, content_id: str, owner_id: str) -> DeletionReceipt:
        with self._connect() as connection:
            record = self._owned_record(connection, content_id, owner_id)
            rows = connection.execute(
                "SELECT * FROM deletion_status WHERE content_id = ? ORDER BY store",
                (content_id,),
            ).fetchall()
            complete = record.envelope.state is ProcessingState.DELETED
            return DeletionReceipt(
                content_id=content_id,
                state=record.envelope.state,
                complete=complete,
                stores=[
                    DeletionStoreStatus(
                        store=row["store"],
                        state=DeletionState(row["state"]),
                        attempts=row["attempts"],
                        last_error_code=row["last_error_code"],
                    )
                    for row in rows
                ],
            )

    def expired_content_ids(self, *, owner_id: str, now: datetime, limit: int = 100) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT content_id FROM memory_items
                WHERE owner_id = ? AND expires_at IS NOT NULL AND expires_at <= ?
                  AND state != ?
                ORDER BY expires_at, content_id
                LIMIT ?
                """,
                (
                    owner_id,
                    _iso(now),
                    ProcessingState.DELETED.value,
                    limit,
                ),
            ).fetchall()
            return [row["content_id"] for row in rows]

    def state_counts(self, owner_id: str) -> dict[str, int]:
        counts = {state.value: 0 for state in ProcessingState}
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT state, count(*) AS count
                FROM memory_items
                WHERE owner_id = ?
                GROUP BY state
                """,
                (owner_id,),
            ).fetchall()
            counts.update({row["state"]: row["count"] for row in rows})
        return counts

    def deletion_counts(self, owner_id: str) -> dict[str, int]:
        counts = {state.value: 0 for state in DeletionState}
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT d.state, count(*) AS count
                FROM deletion_status d
                JOIN memory_items m ON m.content_id = d.content_id
                WHERE m.owner_id = ?
                GROUP BY d.state
                """,
                (owner_id,),
            ).fetchall()
            counts.update({row["state"]: row["count"] for row in rows})
        return counts

    @staticmethod
    def _owned_record(
        connection: sqlite3.Connection, content_id: str, owner_id: str
    ) -> MemoryRecord:
        row = connection.execute(
            "SELECT * FROM memory_items WHERE content_id = ?", (content_id,)
        ).fetchone()
        if row is None:
            raise ItemNotFound("The requested memory does not exist.")
        if row["owner_id"] != owner_id:
            raise OwnerMismatch("The requested memory belongs to a different owner.")
        return MemoryDatabase._record(row)

    @staticmethod
    def _record(row: sqlite3.Row) -> MemoryRecord:
        failure = None
        if row["failure_code"]:
            failure_at = _datetime(row["failure_at"])
            assert failure_at is not None
            failure = FailureMetadata(
                code=row["failure_code"],
                message=row["failure_message"],
                retryable=bool(row["failure_retryable"]),
                occurred_at=failure_at,
                attempt=row["failure_attempt"],
            )
        metadata = None
        if row["image_metadata_json"]:
            metadata = ImageMetadata.model_validate_json(row["image_metadata_json"])
        captured_at = _datetime(row["captured_at"])
        assert captured_at is not None
        envelope = IngestionEnvelope(
            content_id=row["content_id"],
            content_hash=row["content_hash"],
            captured_at=captured_at,
            device_pseudonym=row["device_pseudonym"],
            state=ProcessingState(row["state"]),
            consent_version=row["consent_version"],
            retention_class=RetentionClass(row["retention_class"]),
            expires_at=_datetime(row["expires_at"]),
            provider_version=row["provider_version"],
            policy_version=row["policy_version"],
            retry_count=row["retry_count"],
            version=row["version"],
            failure=failure,
        )
        return MemoryRecord(
            envelope=envelope,
            owner_id=row["owner_id"],
            blob_name=row["blob_name"],
            key_id=row["key_id"],
            lease_token=row["lease_token"],
            lease_expires_at=_datetime(row["lease_expires_at"]),
            next_attempt_at=_datetime(row["next_attempt_at"]),
            redacted_text=row["redacted_text"],
            caption=row["caption"],
            image_metadata=metadata,
        )
