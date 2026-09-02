# Privacy threat model and operational limits

## Protected assets

- Raw screenshot pixels.
- Locally extracted OCR and derived captions.
- Linkage between captures, times, device/source pseudonyms, and one local owner.
- Encryption keys and deletion state.

## Trust boundaries

The default trust boundary is one user-controlled host and its local filesystem. The FastAPI server binds to loopback and remote processing is disabled. Capture clients, the operating system, Tesseract binary/language data, Python dependencies, and anyone with host access remain trusted components.

AES-GCM protects blobs when ciphertext is copied without the keyring and detects ciphertext/AAD modification. It does not protect content from a fully compromised running process, screen recorder, malicious OCR binary, swap/hibernation capture, or an attacker who obtains both blobs and keys.

SQLite metadata is not encrypted in v1. It includes content hashes, capture/expiry times, opaque keyed IDs, state/failure information, provider/policy versions, and redacted OCR/captions for processed items. Raw content hashes stay inside this local store and are omitted from public API summaries. The owner ID should therefore remain pseudonymous.

## Default network behavior

- Default backend and frontend paths initialize no analytics or telemetry client.
- Local processing constructs no remote provider unless explicit enablement and endpoint configuration are both present.
- The iOS extension has no default upload URL.
- The desktop adapter targets loopback. A non-loopback target requires explicit opt-in and HTTPS.
- Legacy Gemini, Neo4j, and PostgreSQL modules are not imported by the default server.
- The metadata-only capture monitor and WebSocket are disabled by default. Explicit enablement still requires an exact allowlisted browser origin; this is origin isolation for a single local owner, not user authentication.

Tests block non-loopback socket access (while permitting the in-process loopback test harness) and prove a supplied remote spy receives zero calls in local-only mode. This does not verify behavior of arbitrary third-party binaries such as Tesseract.

## Ingestion and crash windows

The server validates image bytes in memory, enforces configured source rules, creates a metadata-only `received` row, writes an authenticated ciphertext atomically, then marks the row `stored`. A crash before blob completion leaves a metadata-only row; replaying the same image resumes idempotently. A crash after blob replacement but before `stored` leaves a deterministic encrypted blob that replay reconciles. If a concurrent deletion wins before the reference update, ingest removes the late ciphertext; a failed compensating removal records the blob reference and reopens deletion as failed instead of silently reporting completion. Abrupt process termination before compensation can still leave an encrypted orphan, so future maintenance may add conservative orphan sweeping.

The database and blob filesystem cannot share one atomic transaction. Atomic same-directory blob replacement and deterministic names minimize ambiguity, but backups must capture both coherently.

## Processing and retries

Claims use conditional SQLite updates with random lease tokens. No database transaction is held during OCR or remote work. A background heartbeat conditionally renews the token during live work; if renewal loses ownership, the stale worker cannot persist success or failure. An actually expired claim can be recovered, consumes the retry budget, and becomes an explicit terminal failure after that budget is exhausted. Only named retryable failures receive capped exponential backoff with deterministic per-item jitter and a hard attempt limit. A process crash during an optional remote request remains ambiguous, so that provider must honor the deterministic idempotency key.

The optional remote request has a deterministic idempotency key. Connection/pool failures are considered retryable; read/write timeouts are treated as ambiguous and stop automatic retry. The remote adapter must honor idempotency for any side effect, though v1 expects suggestion-only processing and grants no publication/destruction capability.

## Redaction and prompt injection

Email, North American phone, common secret assignment, and configured literal exclusion patterns are removed locally. The original OCR is not stored after processing and is never sent by the v1 remote adapter. Redaction is best-effort and cannot guarantee removal of every sensitive form or information visible only in pixels.

Configured source/app deny rules run before durable ingest against both the untrusted client label and a local coarse detector in the default server. Detection recognizes only repository-defined indicators, may return `unknown`, and is not a DLP control. A library deployment that enables deny rules without a local observer fails closed instead of trusting the client label alone.

OCR text is a data field in a strict request schema. It is never evaluated as a command. An optional model provider remains capable of misinterpreting content, so its response is untrusted, schema-validated evidence and cannot authorize deletion, posting, or other actions.

## Retention and deletion semantics

Deletion first changes state to `deleting` and clears search text within SQLite. Each configured store has an independent status, attempt count, and renewable claim. Overlapping requests cannot concurrently execute one adapter, and a crashed store claim becomes retryable after its lease expires. `deleted` is reached only when all configured stores report complete; unavailable adapters remain visible as failure. Repetition is idempotent.

This mechanism cannot delete external copies, unregistered stores, crash dumps, backups, filesystem snapshots, or screenshots retained by the capture OS/application. `not_configured` means a store was not used by this local deployment; it is not evidence that no external copy exists.

## Key lifecycle

First start generates a random 256-bit key in an ignored versioned keyring. It fsyncs a private temporary file and atomically publishes it with exclusive same-filesystem linking, so a crash cannot expose a partially written final keyring path. POSIX permissions are restricted where supported; Windows users should additionally protect the directory with account ACLs or an OS secret store. Keys are not committed or printed in status.

Rotation adds a new active key and keeps prior decrypt-only keys. An exclusive lock makes concurrent rotation fail closed; a crash can leave a stale lock that requires operator review rather than silently risking key loss. Running services reload committed keyring changes before later blob access, although an already in-flight upload may finish under the prior retained key. Removing historical keys before their blobs expire causes intentional data loss. The code does not escrow, derive from a password, or upload keys.

If the keyring is missing, malformed, unreadable, or fails its key-ID integrity check, ingestion/decryption fails closed while status and database-referenced ciphertext deletion remain available. There is no content recovery without a backup.

## Residual risks and follow-ups

- OS keychain integration and envelope encryption are not implemented.
- SQLite metadata/search text is plaintext on the local host.
- Local owner identity is a single-host namespace, not hardened authentication.
- Redaction is deterministic but incomplete by nature.
- Tesseract and capture applications are trusted local dependencies.
- Existing prototype screenshot JSON is deliberately not auto-migrated.
- A future legacy-store adapter must add owner/source IDs and deletion contracts before graph/vector writes can be enabled safely.
