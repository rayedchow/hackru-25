from __future__ import annotations

import io
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image
from synapse_memory.config import MemoryConfig


class MutableClock:
    def __init__(self, value: datetime | None = None) -> None:
        self.value = value or datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: int) -> None:
        self.value += timedelta(**kwargs)


class FakeOCR:
    name = "fake-local-ocr"

    def __init__(self, text: str = "Synthetic invoice reference alpha") -> None:
        self.text = text
        self.calls = 0

    def extract_text(self, image_bytes: bytes) -> str:
        assert image_bytes.startswith(b"\x89PNG")
        self.calls += 1
        return self.text


def make_png(*, color: tuple[int, int, int] = (12, 45, 78)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def is_loopback(address: object) -> bool:
        return isinstance(address, tuple) and bool(address) and address[0] in {"127.0.0.1", "::1"}

    def guarded_connect(sock: socket.socket, address: object) -> object:
        if is_loopback(address):
            return original_connect(sock, address)  # type: ignore[arg-type]
        raise AssertionError("network access is forbidden in the core test suite")

    def guarded_create_connection(address: object, *args: object, **kwargs: object) -> object:
        if is_loopback(address):
            return original_create_connection(address, *args, **kwargs)  # type: ignore[arg-type]
        raise AssertionError("network access is forbidden in the core test suite")

    # AnyIO uses a loopback socketpair to wake the Windows event loop. Permit only
    # that local transport while failing every non-loopback connection attempt.
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock()


@pytest.fixture
def config(tmp_path: Path) -> MemoryConfig:
    return MemoryConfig(
        data_root=tmp_path / "private",
        default_retention_days=30,
        session_retention_days=1,
        lease_seconds=10,
        max_retries=2,
    )


@pytest.fixture
def synthetic_png() -> bytes:
    return make_png()
