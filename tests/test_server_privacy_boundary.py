from __future__ import annotations

import asyncio
import importlib
import io
import sys
from pathlib import Path
from types import ModuleType

import pytest
from conftest import FakeOCR
from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect
from synapse_memory.config import MemoryConfig
from synapse_memory.service import MemoryService


@pytest.fixture
def server_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("SYNAPSE_DATA_ROOT", str(tmp_path / "module-default"))
    monkeypatch.delenv("SYNAPSE_CAPTURE_MONITOR_ENABLED", raising=False)
    sys.modules.pop("server", None)
    return importlib.import_module("server")


def _service(tmp_path: Path) -> MemoryService:
    return MemoryService(
        MemoryConfig(data_root=tmp_path / "service"),
        ocr_provider=FakeOCR(),
    )


def test_capture_metadata_websocket_is_disabled_by_default(
    server_module: ModuleType,
    tmp_path: Path,
) -> None:
    app = server_module.create_app(service=_service(tmp_path))

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as rejected,
        client.websocket_connect(
            "/ws",
            headers={"origin": "http://127.0.0.1:3000"},
        ),
    ):
        pass

    assert rejected.value.code == 1008


def test_capture_metadata_websocket_requires_an_exact_allowed_origin(
    server_module: ModuleType,
    tmp_path: Path,
) -> None:
    allowed = "http://127.0.0.1:3000"
    app = server_module.create_app(
        service=_service(tmp_path),
        capture_monitor_enabled=True,
        allowed_origins=(allowed,),
    )

    with TestClient(app) as client:
        with (
            pytest.raises(WebSocketDisconnect) as rejected,
            client.websocket_connect(
                "/ws",
                headers={"origin": "https://attacker.invalid"},
            ),
        ):
            pass
        assert rejected.value.code == 1008

        with client.websocket_connect("/ws", headers={"origin": allowed}) as websocket:
            assert websocket is not None
            assert len(server_module.ws_manager.connections) == 1

    assert server_module.ws_manager.connections == []


def test_slow_capture_monitor_client_is_timed_out_and_removed(
    server_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowSocket:
        async def send_json(self, _message: object) -> None:
            await asyncio.Event().wait()

    socket = SlowSocket()
    server_module.ws_manager.connections.append(socket)
    monkeypatch.setattr(server_module.ws_manager, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.01)

    asyncio.run(server_module.ws_manager.broadcast({"type": "capture"}))

    assert server_module.ws_manager.connections == []


def test_legacy_local_app_detection_applies_a_subprocess_deadline(
    server_module: ModuleType,
    synthetic_png: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_timeout: list[int] = []

    class FakeTesseract:
        @staticmethod
        def image_to_string(_image: Image.Image, *, timeout: int) -> str:
            observed_timeout.append(timeout)
            return "youtube"

    detection = importlib.import_module("detection.app")
    monkeypatch.setattr(detection, "OCR_AVAILABLE", True)
    monkeypatch.setattr(detection, "pytesseract", FakeTesseract, raising=False)
    with Image.open(io.BytesIO(synthetic_png)) as image:
        assert detection.detect_app(image) == "youtube"

    assert observed_timeout == [5]
