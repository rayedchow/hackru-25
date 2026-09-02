# Synapse local memory

Synapse captures screenshots into a user-controlled, local-first memory pipeline. The default backend encrypts every accepted image before durable blob storage, processes it with local providers, keeps a leased SQLite queue, returns source-grounded search results, and reports retention/deletion status.

Remote processing and the transient capture monitor are off by default. There is no automatic local-to-remote fallback, and the repository's default application paths do not initialize an analytics client. The previous Gemini/Neo4j/pgvector prototype remains in `backend/cron_server` for reference, but the default server does not import or invoke it.

## Privacy boundary

- AES-256-GCM authenticates encrypted screenshot blobs with a fresh nonce.
- A local versioned keyring is created outside version control on first use.
- Blob filenames are keyed, non-reversible identifiers rather than screenshot names or raw hashes.
- SQLite stores lifecycle metadata and locally redacted OCR—not raw image bytes.
- Public API summaries omit the raw content hash; the internal digest is used only for integrity and owner-scoped deduplication.
- Processing and per-store deletion claims use renewable leases and conditional acknowledgements; crashes do not require clearing the queue, while live work is not reclaimed merely because OCR or a configured adapter takes longer than the initial lease.
- Search is owner-scoped and excludes expired, deleting, deleted, or unprocessed content.
- Deletion tombstones search first and tracks blob, local index, vector, and graph completion separately.
- Email addresses, phone numbers, common secret assignments, and configured exclusion terms are redacted locally before optional remote processing.
- Configured source/app deny rules are checked against both the untrusted client label and a pre-persistence local observation in the default server. Observation is deliberately coarse and best-effort, not a DLP guarantee; a library deployment with deny rules but no local observer fails closed.

This is not a claim of end-to-end privacy or protection after full host compromise. The keyring and encrypted data live on infrastructure controlled by the user; an attacker who can read both while the application is running may be able to decrypt content. SQLite retains content hashes, timestamps, keyed pseudonyms, lifecycle state, and redacted text. Backups may retain deleted data until the operator expires them.

## Quick start

Python 3.11+ and Tesseract 5 with local language data are required for OCR.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# POSIX: source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .

python backend/server.py
```

Open <http://127.0.0.1:8000/privacy>. The default bind address is loopback. To capture from another device, deliberately configure a trusted HTTPS endpoint and the relevant firewall/reverse-proxy controls; do not expose the development server directly to the public internet.

The API accepts only loopback hostnames by default (`SYNAPSE_ALLOWED_HOSTS`) and rejects browser requests whose `Origin` is not in `SYNAPSE_ALLOWED_ORIGINS`. This is a DNS-rebinding/browser boundary, not multi-user authentication. The legacy metadata-only capture monitor and `/ws` endpoint are disabled unless `SYNAPSE_CAPTURE_MONITOR_ENABLED=true` is explicitly set. When enabled, WebSocket clients still need an exact allowed origin. Observer work and WebSocket sends have bounded deadlines and never carry screenshot bytes.

Queue operations are explicit:

```bash
synapse-memory status
synapse-memory process-one
synapse-memory sweep
```

## Capture clients

- The iOS extension sends nothing unless `SYNAPSE_UPLOAD_URL` is explicitly supplied to its build settings as an HTTPS `/upload` URL. The committed public ngrok destination and arbitrary-transport exception were removed.
- The macOS hotkey pipes the selected PNG in memory to the local Next adapter; it does not create `/tmp/screenshot.png`.
- The Next adapter defaults to `http://127.0.0.1:8000`, forwards with a 10-second deadline, and never writes `public/latest.png`. A non-loopback backend additionally requires `SYNAPSE_REMOTE_CAPTURE_ENABLED=true` and HTTPS.

## Providers

The default providers are local Tesseract OCR, deterministic Pillow metadata, and a deterministic local hash embedding boundary. If Tesseract is missing or times out, the memory remains encrypted and the failure is visible; retry behavior is bounded.

Optional HTTP remote processing requires both:

```text
SYNAPSE_REMOTE_ENABLED=true
SYNAPSE_REMOTE_ENDPOINT=https://user-controlled.example/process
```

Only redacted OCR text, bounded image dimensions/format, policy version, source ID, and an idempotency key are sent. The raw image is not sent by the v1 remote adapter. Responses are capped at 64 KiB and must match the strict v1 JSON schema. Authorization/validation failures and ambiguous read/write timeouts are not automatically retried.

## Retention and deletion

The default `standard` retention class is 30 days; `session` is one day and `keep` has no automatic expiry. Override defaults with documented environment variables in [ONBOARDING.md](ONBOARDING.md).

Deletion immediately removes the searchable text and marks the item `deleting`. It then atomically claims each configured backend so overlapping delete requests cannot run the same adapter concurrently. A receipt is complete only after every configured store succeeds; active, failed, and recovered attempts stay visible and can be retried idempotently up to the attempt cap. Exhausted stores remain visible with `deletion_attempts_exhausted` and require operator repair rather than being described as retryable. Unconfigured graph/vector stores are explicitly reported as such. If deletion wins the small gap between ciphertext creation and the database reference update, ingest compensates by removing the late blob; a cleanup failure reopens a tracked partial deletion instead of reporting success.

Key rotation affects new blobs only. Running services reload the on-disk keyring before later blob access, so a completed CLI rotation is observed without a restart; an upload already in flight may finish with the prior retained key. Old keys remain in the keyring until every blob that needs them is deleted or re-encrypted. A rotation lock prevents concurrent lost-key updates; a stale lock intentionally blocks rotation until an operator verifies that no rotation process is active. Losing the keyring makes encrypted screenshots unrecoverable, but does not prevent deletion of a database-referenced ciphertext. Copying only the keyring without the database/blobs is not a usable backup. See [the threat model](docs/privacy-threat-model.md).

## Privacy status evidence

These browser captures use an empty synthetic local profile; they contain no personal screenshots or production data.

- [Before: prototype capture monitor](docs/privacy-status-before.png)
- [After: local privacy status on desktop](docs/privacy-status-after-desktop.png)
- [After: local privacy status at a 500 × 844 narrow viewport](docs/privacy-status-after-mobile.png)

## Development

```bash
ruff format --check backend/synapse_memory backend/server.py backend/dashboard.py backend/ws_manager.py backend/detection/app.py tests scripts frontend/brainApp/screenshot_app.py
ruff check backend/synapse_memory backend/server.py backend/dashboard.py backend/ws_manager.py backend/detection/app.py tests scripts frontend/brainApp/screenshot_app.py
mypy backend/synapse_memory backend/server.py backend/dashboard.py backend/ws_manager.py backend/detection/app.py
pytest --cov=synapse_memory --cov-report=term-missing --cov-fail-under=90
python -m build
python scripts/scan_secrets.py --base cdd926df300677e9f73f2422c9c1f0e11c0f1bc3
```

Core tests use generated synthetic images and block non-loopback network access; loopback remains available for the in-process HTTP test harness. They require no Gemini/OpenAI key, Neo4j, PostgreSQL, iOS device, or real screenshot.

## Limitations

- The default is a single-owner local service, not a hardened multi-tenant identity system.
- Local source observation recognizes only a small repository-defined set of app indicators and can miss or misclassify content; deny rules reduce accidental capture but are not a security boundary against a malicious local process.
- The opt-in capture monitor exposes coarse session/frame/app/scroll metadata to exact-origin local clients and has no separate login; keep it disabled outside the documented single-owner boundary.
- Tesseract quality depends on locally installed language data.
- The deterministic local search is evidence retrieval, not a generated semantic answer.
- The v1 remote interface sends redacted text only and does not implement provider authentication; put it behind a user-controlled authenticated adapter before use.
- Deletion cannot erase offline backups, filesystem snapshots, or copies made outside registered adapters.
- Existing committed prototype screenshot data is not migrated because its consent and ownership provenance cannot be established.
- Xcode/iOS compilation is not exercised by cross-platform Python CI.
- This repository currently has no upstream license file; downstream reuse rights remain unclear until the maintainer adds one.
