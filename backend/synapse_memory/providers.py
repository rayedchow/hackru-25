"""Explicit local and opt-in remote processing provider boundaries."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
from dataclasses import dataclass
from typing import Protocol

import httpx
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from .errors import (
    AmbiguousRemoteFailure,
    ConfigurationError,
    InvalidUpload,
    ProviderTimeout,
    ProviderUnavailable,
    RemoteProcessingDisabled,
    RemoteResponseInvalid,
)
from .models import ImageMetadata, RemoteProcessingRequest, RemoteProcessingResponse

MAX_REMOTE_RESPONSE_BYTES = 64 * 1024
MAX_IMAGE_PIXELS = 40_000_000


class OCRProvider(Protocol):
    name: str

    def extract_text(self, image_bytes: bytes) -> str: ...


class ImageUnderstandingProvider(Protocol):
    name: str

    def describe(self, image_bytes: bytes) -> tuple[ImageMetadata, str]: ...


class EmbeddingProvider(Protocol):
    name: str

    def embed(self, text: str) -> tuple[int, ...]: ...


class RemoteProcessingProvider(Protocol):
    name: str

    def process(self, request: RemoteProcessingRequest) -> RemoteProcessingResponse: ...


class DeletionAdapter(Protocol):
    name: str

    def delete(self, *, owner_id: str, content_id: str) -> None: ...


@dataclass(slots=True)
class TesseractOCRProvider:
    executable: str = "tesseract"
    language: str = "eng"
    timeout_seconds: int = 20
    name: str = "tesseract-local"

    def extract_text(self, image_bytes: bytes) -> str:
        try:
            completed = subprocess.run(
                [self.executable, "stdin", "stdout", "-l", self.language, "--psm", "3"],
                input=image_bytes,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise ConfigurationError(
                "Local OCR is unavailable; install Tesseract or configure another local provider."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderTimeout("Local OCR exceeded its processing deadline.") from exc
        if completed.returncode != 0:
            raise ProviderUnavailable("Local OCR could not process this image.")
        return completed.stdout.decode("utf-8", errors="replace")[:20_000]


@dataclass(slots=True)
class DeterministicImageProvider:
    name: str = "pillow-metadata-local"

    def describe(self, image_bytes: bytes) -> tuple[ImageMetadata, str]:
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                metadata = ImageMetadata(
                    width=image.width,
                    height=image.height,
                    format=(image.format or "unknown").lower(),
                    mode=image.mode.lower(),
                )
                if metadata.width * metadata.height > MAX_IMAGE_PIXELS:
                    raise InvalidUpload("The image dimensions exceed the configured safety limit.")
                image.load()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise InvalidUpload("The payload is not a supported image.") from exc
        caption = f"Local {metadata.format} image ({metadata.width} x {metadata.height})."
        return metadata, caption


@dataclass(slots=True)
class DeterministicHashEmbeddingProvider:
    dimensions: int = 64
    name: str = "hash-embedding-local-v1"

    def embed(self, text: str) -> tuple[int, ...]:
        values = [0] * self.dimensions
        for token in sorted(set(text.casefold().split())):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            values[index] += 1 if digest[4] & 1 else -1
        return tuple(values)


@dataclass(slots=True)
class DisabledRemoteProvider:
    name: str = "disabled"

    def process(self, request: RemoteProcessingRequest) -> RemoteProcessingResponse:
        del request
        raise RemoteProcessingDisabled("Remote processing is disabled in local-only mode.")


class HTTPRemoteProvider:
    name = "http-remote-v1"

    def __init__(
        self, *, endpoint: str, timeout_seconds: int, client: httpx.Client | None = None
    ) -> None:
        if not endpoint:
            raise ConfigurationError("A remote endpoint is required for the HTTP provider.")
        self.endpoint = endpoint
        self.timeout = httpx.Timeout(
            timeout_seconds,
            connect=min(timeout_seconds, 5),
            read=timeout_seconds,
            write=timeout_seconds,
            pool=min(timeout_seconds, 5),
        )
        self._client = client or httpx.Client(follow_redirects=False)

    def process(self, request: RemoteProcessingRequest) -> RemoteProcessingResponse:
        try:
            with self._client.stream(
                "POST",
                self.endpoint,
                content=request.model_dump_json(),
                headers={
                    "Content-Type": "application/json",
                    "Idempotency-Key": request.idempotency_key,
                },
                timeout=self.timeout,
                follow_redirects=False,
            ) as response:
                if response.status_code in {401, 403}:
                    raise ConfigurationError("The optional remote provider rejected authorization.")
                if response.status_code == 429 or response.status_code >= 500:
                    raise ProviderUnavailable(
                        "The optional remote provider is temporarily unavailable."
                    )
                if response.status_code < 200 or response.status_code >= 300:
                    raise RemoteResponseInvalid(
                        "The optional remote provider rejected the request."
                    )
                encoded = bytearray()
                for chunk in response.iter_bytes():
                    if len(encoded) + len(chunk) > MAX_REMOTE_RESPONSE_BYTES:
                        raise RemoteResponseInvalid(
                            "The optional remote provider response exceeded its size limit."
                        )
                    encoded.extend(chunk)
        except (httpx.ConnectTimeout, httpx.ConnectError, httpx.PoolTimeout) as exc:
            raise ProviderUnavailable("The optional remote provider could not be reached.") from exc
        except (httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise AmbiguousRemoteFailure(
                "The optional remote request may have been received and will not be "
                "retried automatically."
            ) from exc
        except httpx.RequestError as exc:
            raise AmbiguousRemoteFailure("The optional remote request failed ambiguously.") from exc
        try:
            payload = json.loads(encoded)
            return RemoteProcessingResponse.model_validate(payload, strict=True)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RemoteResponseInvalid(
                "The optional remote provider returned an invalid response."
            ) from exc
