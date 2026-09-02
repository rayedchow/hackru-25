"""Versioned keyring and authenticated encrypted blob storage."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import EncryptionKeyUnavailable, StorageIntegrityError

KEYRING_VERSION = 1
BLOB_MAGIC = b"SYNAPSE-BLOB-1\x00"
NONCE_BYTES = 12
KEY_BYTES = 32
KEY_ID_PATTERN = re.compile(r"^key-[0-9a-f]{16}$")
BLOB_NAME_PATTERN = re.compile(r"^[0-9a-f]{64}\.blob$")


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def _key_id(key: bytes) -> str:
    digest = hashlib.sha256(b"synapse-key-id-v1\x00" + key).hexdigest()
    return f"key-{digest[:16]}"


def _set_private_permissions(path: Path, *, directory: bool = False) -> None:
    with suppress(OSError):
        path.chmod(0o700 if directory else 0o600)
    # Windows ACLs and some filesystems do not implement POSIX mode bits.


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class Keyring:
    active_key_id: str
    keys: dict[str, bytes]

    @property
    def active_key(self) -> bytes:
        try:
            return self.keys[self.active_key_id]
        except KeyError as exc:
            raise EncryptionKeyUnavailable("The active encryption key is unavailable.") from exc

    def key(self, key_id: str) -> bytes:
        try:
            return self.keys[key_id]
        except KeyError as exc:
            raise EncryptionKeyUnavailable(
                "The key required to decrypt this memory is unavailable."
            ) from exc

    def to_json(self) -> dict[str, object]:
        return {
            "version": KEYRING_VERSION,
            "active_key_id": self.active_key_id,
            "keys": {
                key_id: base64.urlsafe_b64encode(key).decode("ascii")
                for key_id, key in sorted(self.keys.items())
            },
        }


def _parse_keyring(raw: object) -> Keyring:
    if not isinstance(raw, dict) or set(raw) != {"version", "active_key_id", "keys"}:
        raise EncryptionKeyUnavailable("The local encryption keyring is invalid.")
    if raw["version"] != KEYRING_VERSION:
        raise EncryptionKeyUnavailable("The local encryption keyring version is unsupported.")
    active_key_id = raw["active_key_id"]
    encoded_keys = raw["keys"]
    if not isinstance(active_key_id, str) or not KEY_ID_PATTERN.fullmatch(active_key_id):
        raise EncryptionKeyUnavailable("The local encryption keyring has an invalid active key.")
    if not isinstance(encoded_keys, dict) or not encoded_keys:
        raise EncryptionKeyUnavailable("The local encryption keyring contains no keys.")
    keys: dict[str, bytes] = {}
    for key_id, encoded in encoded_keys.items():
        if not isinstance(key_id, str) or not KEY_ID_PATTERN.fullmatch(key_id):
            raise EncryptionKeyUnavailable(
                "The local encryption keyring contains an invalid key ID."
            )
        if not isinstance(encoded, str):
            raise EncryptionKeyUnavailable("The local encryption keyring contains an invalid key.")
        try:
            key = base64.b64decode(encoded, altchars=b"-_", validate=True)
        except (ValueError, TypeError) as exc:
            raise EncryptionKeyUnavailable(
                "The local encryption keyring contains invalid base64."
            ) from exc
        if len(key) != KEY_BYTES or _key_id(key) != key_id:
            raise EncryptionKeyUnavailable("The local encryption keyring failed integrity checks.")
        keys[key_id] = key
    if active_key_id not in keys:
        raise EncryptionKeyUnavailable("The active encryption key is missing from the keyring.")
    return Keyring(active_key_id=active_key_id, keys=keys)


def load_keyring(path: Path) -> Keyring:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EncryptionKeyUnavailable("The local encryption keyring cannot be read.") from exc
    keyring = _parse_keyring(raw)
    _set_private_permissions(path.parent, directory=True)
    _set_private_permissions(path)
    return keyring


def load_or_create_keyring(path: Path, *, auto_create: bool) -> Keyring:
    if path.exists():
        return load_keyring(path)
    if not auto_create:
        raise EncryptionKeyUnavailable(
            "No encryption key is available; create or restore the local keyring before ingesting."
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    _set_private_permissions(path.parent, directory=True)
    key = secrets.token_bytes(KEY_BYTES)
    key_id = _key_id(key)
    keyring = Keyring(active_key_id=key_id, keys={key_id: key})
    payload = _canonical_json(keyring.to_json())
    try:
        with path.open("xb") as handle:
            _set_private_permissions(path)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
        return keyring
    except FileExistsError:
        # Another local process won the exclusive create race.
        return load_keyring(path)
    except OSError as exc:
        raise EncryptionKeyUnavailable(
            "The local encryption keyring could not be created."
        ) from exc


def rotate_keyring(path: Path) -> Keyring:
    lock_path = path.with_name(path.name + ".rotation.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise EncryptionKeyUnavailable(
            "Key rotation is already in progress or its stale lock needs operator review."
        ) from exc
    try:
        os.write(descriptor, b"synapse-key-rotation-v1\n")
        os.fsync(descriptor)
        current = load_keyring(path)
        key = secrets.token_bytes(KEY_BYTES)
        key_id = _key_id(key)
        rotated = Keyring(active_key_id=key_id, keys={**current.keys, key_id: key})
        _atomic_write(path, _canonical_json(rotated.to_json()))
        _set_private_permissions(path)
        return rotated
    finally:
        os.close(descriptor)
        with suppress(OSError):
            lock_path.unlink()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=".synapse-", suffix=".tmp", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            _set_private_permissions(temporary_path)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except OSError:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
        raise


@dataclass(frozen=True, slots=True)
class StoredBlob:
    blob_name: str
    key_id: str
    created: bool


class EncryptedBlobStore:
    """AES-GCM blobs addressed by a keyed, non-disclosing identifier."""

    def __init__(self, root: Path, keyring: Keyring) -> None:
        self.root = root
        self.keyring = keyring
        root.mkdir(parents=True, exist_ok=True)
        _set_private_permissions(root, directory=True)
        self._store_lock = threading.Lock()

    @staticmethod
    def content_hash(plaintext: bytes) -> str:
        return hashlib.sha256(plaintext).hexdigest()

    def blob_name(self, owner_id: str, content_hash: str, key_id: str | None = None) -> str:
        selected_key_id = key_id or self.keyring.active_key_id
        key = self.keyring.key(selected_key_id)
        naming_key = hmac.digest(key, b"synapse-blob-name-key-v1", "sha256")
        digest = hmac.digest(
            naming_key, owner_id.encode("utf-8") + b"\x00" + content_hash.encode("ascii"), "sha256"
        ).hex()
        return f"{digest}.blob"

    @staticmethod
    def _aad(*, owner_id: str, content_id: str, content_hash: str, key_id: str) -> bytes:
        return _canonical_json(
            {
                "blob_version": 1,
                "content_hash": content_hash,
                "content_id": content_id,
                "key_id": key_id,
                "owner_id": owner_id,
            }
        )

    def store(
        self, *, owner_id: str, content_id: str, content_hash: str, plaintext: bytes
    ) -> StoredBlob:
        if self.content_hash(plaintext) != content_hash:
            raise StorageIntegrityError("The supplied content hash does not match the image bytes.")
        with self._store_lock:
            return self._store_locked(
                owner_id=owner_id,
                content_id=content_id,
                content_hash=content_hash,
                plaintext=plaintext,
            )

    def _store_locked(
        self, *, owner_id: str, content_id: str, content_hash: str, plaintext: bytes
    ) -> StoredBlob:
        key_id = self.keyring.active_key_id
        blob_name = self.blob_name(owner_id, content_hash, key_id)
        path = self._path(blob_name)
        if path.exists():
            # Verify a prior idempotent write instead of silently trusting it.
            self.read(
                blob_name=blob_name,
                owner_id=owner_id,
                content_id=content_id,
                content_hash=content_hash,
            )
            return StoredBlob(blob_name=blob_name, key_id=key_id, created=False)

        nonce = secrets.token_bytes(NONCE_BYTES)
        aad = self._aad(
            owner_id=owner_id,
            content_id=content_id,
            content_hash=content_hash,
            key_id=key_id,
        )
        ciphertext = AESGCM(self.keyring.active_key).encrypt(nonce, plaintext, aad)
        key_id_bytes = key_id.encode("ascii")
        encoded = BLOB_MAGIC + bytes([len(key_id_bytes)]) + key_id_bytes + nonce + ciphertext
        try:
            # Exclusive creation is provided by the keyed deterministic name plus atomic replace.
            # Competing identical uploads write equivalent authenticated content; the database
            # uniqueness constraint chooses the canonical envelope.
            _atomic_write(path, encoded)
        except OSError as exc:
            raise StorageIntegrityError("The encrypted screenshot could not be stored.") from exc
        return StoredBlob(blob_name=blob_name, key_id=key_id, created=True)

    def read(self, *, blob_name: str, owner_id: str, content_id: str, content_hash: str) -> bytes:
        path = self._path(blob_name)
        try:
            encoded = path.read_bytes()
        except OSError as exc:
            raise StorageIntegrityError("The encrypted screenshot is unavailable.") from exc
        minimum = len(BLOB_MAGIC) + 1 + 1 + NONCE_BYTES + 16
        if len(encoded) < minimum or not encoded.startswith(BLOB_MAGIC):
            raise StorageIntegrityError("The encrypted screenshot format is invalid.")
        key_id_length = encoded[len(BLOB_MAGIC)]
        key_start = len(BLOB_MAGIC) + 1
        key_end = key_start + key_id_length
        try:
            key_id = encoded[key_start:key_end].decode("ascii")
        except UnicodeDecodeError as exc:
            raise StorageIntegrityError("The encrypted screenshot key ID is invalid.") from exc
        if not KEY_ID_PATTERN.fullmatch(key_id):
            raise StorageIntegrityError("The encrypted screenshot key ID is invalid.")
        nonce = encoded[key_end : key_end + NONCE_BYTES]
        ciphertext = encoded[key_end + NONCE_BYTES :]
        if len(nonce) != NONCE_BYTES or len(ciphertext) < 16:
            raise StorageIntegrityError("The encrypted screenshot is truncated.")
        aad = self._aad(
            owner_id=owner_id,
            content_id=content_id,
            content_hash=content_hash,
            key_id=key_id,
        )
        try:
            plaintext = AESGCM(self.keyring.key(key_id)).decrypt(nonce, ciphertext, aad)
        except (InvalidTag, EncryptionKeyUnavailable) as exc:
            raise StorageIntegrityError(
                "The encrypted screenshot failed integrity verification."
            ) from exc
        if not hmac.compare_digest(self.content_hash(plaintext), content_hash):
            raise StorageIntegrityError(
                "The decrypted screenshot hash does not match its envelope."
            )
        return plaintext

    def delete(self, blob_name: str) -> None:
        delete_encrypted_blob(self.root, blob_name)

    def exists(self, blob_name: str) -> bool:
        return self._path(blob_name).is_file()

    def _path(self, blob_name: str) -> Path:
        if not BLOB_NAME_PATTERN.fullmatch(blob_name):
            raise StorageIntegrityError("The encrypted blob identifier is invalid.")
        return self.root / blob_name


def delete_encrypted_blob(root: Path, blob_name: str) -> None:
    """Delete a validated ciphertext path without requiring decryption key material."""
    if not BLOB_NAME_PATTERN.fullmatch(blob_name):
        raise StorageIntegrityError("The encrypted blob identifier is invalid.")
    (root / blob_name).unlink(missing_ok=True)
