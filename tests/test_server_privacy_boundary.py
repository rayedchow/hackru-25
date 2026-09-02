from __future__ import annotations

import asyncio
import importlib
import io
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from conftest import FakeOCR
from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect
from synapse_memory.config import MemoryConfig
from synapse_memory.errors import ContentDenied
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
    app = server_module.create_app(service=_service(tmp_path), allowed_hosts=("testserver",))

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
        allowed_hosts=("testserver",),
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


def test_http_api_rejects_dns_rebinding_host_and_untrusted_origin(
    server_module: ModuleType,
    tmp_path: Path,
    synthetic_png: bytes,
) -> None:
    service = _service(tmp_path)
    envelope, _ = service.ingest(synthetic_png, source="synthetic")
    app = server_module.create_app(
        service=service,
        allowed_hosts=("testserver",),
        allowed_origins=("http://127.0.0.1:3000",),
    )

    with TestClient(app) as client:
        rebound = client.get("/privacy/status", headers={"host": "attacker.invalid"})
        cross_origin = client.get("/privacy/status", headers={"origin": "https://attacker.invalid"})
        rebound_delete = client.delete(
            f"/memory/{envelope.content_id}",
            headers={
                "host": "attacker.invalid",
                "x-synapse-owner": service.config.owner_id,
                "x-synapse-intent": "delete",
            },
        )
        local = client.get("/privacy/status")

    assert rebound.status_code == 400
    assert cross_origin.status_code == 403
    assert cross_origin.json()["error"] == "untrusted_origin"
    assert rebound_delete.status_code == 400
    assert (
        service.database.get(envelope.content_id, service.config.owner_id).envelope.state.value
        == "stored"
    )
    assert local.status_code == 200


def test_source_detector_uses_declared_local_ocr_boundary(
    server_module: ModuleType,
    synthetic_png: bytes,
) -> None:
    class YouTubeOCR:
        @staticmethod
        def extract_text(_image_bytes: bytes) -> str:
            return "Synthetic YouTube subscribe label"

    provider = server_module.LocalAppSourceProvider()
    provider._ocr = YouTubeOCR()

    assert provider.detect(synthetic_png) == "youtube"


def test_declared_deny_rule_rejects_observed_source_before_persistence(
    server_module: ModuleType,
    tmp_path: Path,
    synthetic_png: bytes,
) -> None:
    class YouTubeOCR:
        @staticmethod
        def extract_text(_image_bytes: bytes) -> str:
            return "Synthetic YouTube subscribe label"

    provider = server_module.LocalAppSourceProvider()
    provider._ocr = YouTubeOCR()
    config = replace(MemoryConfig(data_root=tmp_path / "denied"), denied_sources=("youtube",))
    service = MemoryService(
        config,
        ocr_provider=FakeOCR(),
        source_observation_provider=provider,
    )

    with pytest.raises(ContentDenied):
        service.ingest(synthetic_png, source="desktop-hotkey")

    assert list(config.blob_root.glob("*")) == []
    assert all(count == 0 for count in service.database.state_counts(config.owner_id).values())
