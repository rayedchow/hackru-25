# Synapse local-first setup

This guide covers the default encrypted local pipeline. The older Gemini/Neo4j/pgvector hackathon prototype remains under `backend/cron_server`, but it is not imported or called by `backend/server.py`.

## Requirements

- Python 3.11+
- Tesseract 5 plus the desired local language data
- Optional: Node 18+ for the existing Electron/Next interface
- Optional: Xcode and an iOS device for ReplayKit capture

No model API key, PostgreSQL server, or Neo4j server is required for encrypted capture, queue processing, privacy status, local evidence search, retention, or deletion.

## Install and run

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# POSIX: source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python backend/server.py
```

The server binds to `127.0.0.1:8000` by default. Open <http://127.0.0.1:8000/privacy> to confirm mode, providers, retention, queue state, and deletion failures.

The first start creates this ignored local data set:

```text
backend/private_data/
├── keyring.json
├── memory.sqlite3
└── blobs/
```

The keyring uses restrictive file permissions where the operating system supports them. It is not protected by an OS keychain in v1. Store backups separately and protect them according to the sensitivity of the screenshots.

## Configuration

| Variable | Default | Effect |
| --- | --- | --- |
| `SYNAPSE_DATA_ROOT` | `backend/private_data` | Local keyring, SQLite, and encrypted blob root. |
| `SYNAPSE_OWNER_ID` | `local-owner` | Single local ownership namespace; do not put a real name/email here. |
| `SYNAPSE_DEFAULT_RETENTION_DAYS` | `30` | TTL for `standard` captures (1–3650). |
| `SYNAPSE_SESSION_RETENTION_DAYS` | `1` | TTL for `session` captures (1–30). |
| `SYNAPSE_MAX_UPLOAD_BYTES` | `8388608` | Strict decoded image limit (1 KiB–32 MiB). |
| `SYNAPSE_LEASE_SECONDS` | `60` | Processing claim lease (5–3600 seconds). |
| `SYNAPSE_MAX_RETRIES` | `3` | Automatic retries after the initial attempt (0–10); expired worker leases consume this budget. |
| `SYNAPSE_DENIED_SOURCES` | empty | Comma-separated, case-insensitive source/app deny list. |
| `SYNAPSE_EXCLUSION_TERMS` | empty | Comma-separated literal terms redacted before storage/remote use. |
| `SYNAPSE_DISABLE_KEY_AUTOCREATE` | false | When true, a missing keyring causes fail-closed ingestion. |
| `SYNAPSE_ALLOWED_ORIGINS` | local Next origins | Exact browser origins allowed by CORS. |
| `SYNAPSE_CAPTURE_MONITOR_ENABLED` | false | Explicitly enables the metadata-only `/ws` capture monitor for allowed origins. |
| `SYNAPSE_BIND_HOST` | `127.0.0.1` | API bind host. Changing this expands the trust boundary. |
| `SYNAPSE_BIND_PORT` | `8000` | API port. |
| `SYNAPSE_REMOTE_ENABLED` | false | Explicit opt-in for remote text processing. |
| `SYNAPSE_REMOTE_ENDPOINT` | empty | Strict v1 remote processing endpoint; required when enabled. |
| `SYNAPSE_REMOTE_TIMEOUT_SECONDS` | `10` | Connect/read/write/pool deadline (1–60 seconds). |

Do not put these values in a committed `.env`. Remote credentials are intentionally outside the v1 provider contract; place authentication in a user-controlled adapter or reverse proxy.

## Capture

### macOS hotkey

```bash
cd frontend/brainApp
python -m pip install -r requirements.txt
python screenshot_app.py
```

Command + J invokes the macOS region selector and pipes the PNG in memory to the local Next adapter. No temporary screenshot path is used. The adapter sends it to `http://127.0.0.1:8000/upload` unless configured otherwise and never serves a raw screenshot preview.

### iOS ReplayKit

Set the broadcast extension's `SYNAPSE_UPLOAD_URL` build setting to a user-controlled HTTPS URL ending in `/upload`. With no setting, the extension logs a local locked state and sends nothing. There is no committed default tunnel and no HTTP transport exception.

Exposing the Python development server directly to the public internet is unsupported. Use authenticated, encrypted infrastructure under the user's control and assess the network threat boundary first.

## Process and search

Capture only stores an encrypted item. Processing is explicit so provider work never happens inside the upload transaction:

```bash
synapse-memory process-one
curl -sS 'http://127.0.0.1:8000/memory/search?q=example'
```

Local processing decrypts in memory, performs Tesseract OCR, applies deterministic redaction, records safe image metadata, and stores redacted evidence. It does not call a remote provider. Renewable claims keep valid long-running work from being reclaimed, and a stale worker still cannot acknowledge after another worker takes ownership. If Tesseract is absent or rejects its configured language data, status remains available and the item records a visible non-looping configuration failure; explicit timeouts retain the bounded retry policy.

When `SYNAPSE_DENIED_SOURCES` is non-empty, the default server enforces the list against the client label and a coarse local app observation before any row or ciphertext is created. Client labels remain untrusted. The bundled detector recognizes only a limited set of indicators and is best-effort rather than DLP; a custom library integration must provide its own local source observer or ingestion fails closed while deny rules are active.

The compatibility `/ask_question` endpoint now returns the same local evidence references. It does not fabricate an answer when evidence is absent.

## Retention and deletion

Run automatic expiry deliberately (for example from a user-owned scheduler):

```bash
synapse-memory sweep --limit 100
```

Delete by source ID in the privacy page or API:

```bash
curl -sS -X DELETE \
  -H 'X-Synapse-Intent: delete' \
  http://127.0.0.1:8000/memory/mem-REPLACE_WITH_SOURCE_ID
```

HTTP 200 means every configured store completed; HTTP 202 means at least one deletion is incomplete or actively claimed. Retry the same operation safely. Store-level leases prevent overlapping requests from invoking one deletion adapter twice and allow recovery after a crashed lease expires. Search exclusion happens before downstream deletion, so partially deleted content cannot be returned.

## Optional remote processing

Remote mode is deliberately text-only:

```text
SYNAPSE_REMOTE_ENABLED=true
SYNAPSE_REMOTE_ENDPOINT=https://your-adapter.example/v1/process
```

The request contains strict JSON with source ID, locally redacted OCR, bounded image dimensions/format, policy version, and a content-derived idempotency key. The raw screenshot, raw content hash, and original OCR text are not sent. Responses are capped at 64 KiB and must be:

```json
{"schema_version":"1","caption":"Bounded text","tags":["bounded-tag"]}
```

Connection/pool failures may be retried by the bounded queue. Authentication, schema/validation failures, and ambiguous read/write timeouts are not retried automatically. There is never a silent fallback from local to remote.

## Key rotation, backup, and loss

```bash
synapse-memory rotate-key
```

Rotation uses a new active key for future blobs and retains historical keys for old blobs. It does not re-encrypt old data. Running services reload the keyring before later blob access; an upload already in flight when rotation commits may still use the prior retained key. An exclusive sibling lock prevents concurrent rotations from losing a newly active key. If a process dies during rotation, verify that no rotation is active before manually removing the stale `keyring.json.rotation.lock`. Remove an old key only after proving that no retained blob references it.

The optional transient capture monitor is separate from encrypted memory processing. Enable it only for the single-owner local deployment with `SYNAPSE_CAPTURE_MONITOR_ENABLED=true`. `/ws` rejects missing or non-allowlisted browser origins and broadcasts only coarse session/frame/app/scroll metadata, never screenshot bytes. It has no separate login, so do not expose it as a multi-user service.

For a coherent backup, stop writers and copy the keyring, blob directory, SQLite database, and its WAL/SHM files together (or use SQLite's backup API). Key loss is intentionally unrecoverable. Restoring ciphertext without the matching keyring—or a keyring without its database/blob set—is insufficient.

Deletion does not need the decryption key when the database still contains the validated ciphertext identifier. It cannot reach old backups, snapshots, logs, or unregistered copies. Define and test a backup-retention policy separately.

## Validation

```bash
ruff format --check backend/synapse_memory backend/server.py backend/dashboard.py tests scripts frontend/brainApp/screenshot_app.py
ruff check backend/synapse_memory backend/server.py backend/dashboard.py tests scripts frontend/brainApp/screenshot_app.py
mypy backend/synapse_memory backend/server.py backend/dashboard.py
pytest --cov=synapse_memory --cov-report=term-missing --cov-fail-under=90
python -m build
python scripts/scan_secrets.py --base cdd926df300677e9f73f2422c9c1f0e11c0f1bc3
git diff --check
```

Tests create only synthetic images in isolated temporary directories and block non-loopback network calls. Loopback remains available for the in-process HTTP harness.
