from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from conftest import FakeOCR, MutableClock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from synapse_memory.api import memory_error_handler, memory_router
from synapse_memory.config import MemoryConfig
from synapse_memory.dashboard import PRIVACY_DASHBOARD_HTML
from synapse_memory.errors import MemoryPipelineError
from synapse_memory.service import MemoryService


def _client(
    config: MemoryConfig,
    clock: MutableClock,
    *,
    observer: object | None = None,
    observer_timeout_seconds: float = 2.0,
) -> TestClient:
    service = MemoryService(config, clock=clock, ocr_provider=FakeOCR())
    app = FastAPI()
    app.add_exception_handler(MemoryPipelineError, memory_error_handler)  # type: ignore[arg-type]
    app.include_router(
        memory_router(
            service,
            upload_observer=observer,  # type: ignore[arg-type]
            upload_observer_timeout_seconds=observer_timeout_seconds,
        )
    )
    return TestClient(app)


def _upload(client: TestClient, image: bytes) -> dict[str, object]:
    response = client.post(
        "/upload",
        json={
            "type": "video",
            "payload": base64.b64encode(image).decode("ascii"),
            "source": "synthetic",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_upload_response_omits_raw_hash_and_sensitive_bytes(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    with _client(config, clock) as client:
        payload = _upload(client, synthetic_png)

    memory = payload["memory"]
    assert isinstance(memory, dict)
    assert "content_hash" not in memory
    serialized = str(payload)
    assert base64.b64encode(synthetic_png).decode("ascii") not in serialized
    assert synthetic_png.hex() not in serialized
    assert memory["state"] == "stored"


def test_strict_upload_validation_and_owner_boundary(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    with _client(config, clock) as client:
        extra = client.post(
            "/upload",
            json={
                "type": "video",
                "payload": base64.b64encode(synthetic_png).decode("ascii"),
                "unexpected": True,
            },
        )
        wrong_owner = client.get(
            "/privacy/status",
            headers={"X-Synapse-Owner": "different-owner"},
        )
        malformed = client.post(
            "/upload",
            json={"type": "video", "payload": "not-base64%%%"},
        )

    assert extra.status_code == 422
    assert wrong_owner.status_code == 403
    assert wrong_owner.json()["error"] == "owner_mismatch"
    assert malformed.status_code == 400
    assert malformed.json()["error"] == "invalid_upload"


def test_control_operations_require_explicit_intent_header(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    with _client(config, clock) as client:
        payload = _upload(client, synthetic_png)
        memory = payload["memory"]
        assert isinstance(memory, dict)
        content_id = memory["content_id"]
        assert isinstance(content_id, str)

        process_denied = client.post("/memory/process-next")
        delete_denied = client.delete(f"/memory/{content_id}")
        process_allowed = client.post(
            "/memory/process-next",
            headers={"X-Synapse-Intent": "process"},
        )
        delete_allowed = client.delete(
            f"/memory/{content_id}",
            headers={"X-Synapse-Intent": "delete"},
        )

    assert process_denied.status_code == 403
    assert delete_denied.status_code == 403
    assert process_allowed.status_code == 200
    assert process_allowed.json()["memory"]["state"] == "processed"
    assert "content_hash" not in process_allowed.json()["memory"]
    assert delete_allowed.status_code == 200
    assert delete_allowed.json()["complete"] is True


def test_transient_observer_failure_does_not_hide_successful_ingest(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    async def failing_observer(_image: bytes) -> dict[str, object]:
        raise RuntimeError("synthetic UI observer failure")

    with _client(config, clock, observer=failing_observer) as client:
        payload = _upload(client, synthetic_png)

    assert payload["created"] is True
    assert payload["capture_event"] == {
        "type": "capture",
        "metadata_status": "unavailable",
    }


def test_stalled_observer_is_bounded_and_does_not_hide_successful_ingest(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    async def stalled_observer(_image: bytes) -> dict[str, object]:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    with _client(
        config,
        clock,
        observer=stalled_observer,
        observer_timeout_seconds=0.01,
    ) as client:
        payload = _upload(client, synthetic_png)

    assert payload["created"] is True
    assert payload["capture_event"] == {
        "type": "capture",
        "metadata_status": "unavailable",
    }


def test_privacy_status_reports_mode_without_local_paths(
    config: MemoryConfig,
    clock: MutableClock,
) -> None:
    with _client(config, clock) as client:
        response = client.get("/privacy/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "local-only"
    assert payload["providers"]["remote"] == "disabled"
    assert "database_path" not in payload
    assert str(config.data_root) not in response.text


def test_privacy_dashboard_has_accessible_live_status_and_safe_dom_rendering() -> None:
    assert 'aria-live="polite"' in PRIVACY_DASHBOARD_HTML
    assert 'label for="content-id"' in PRIVACY_DASHBOARD_HTML
    assert ":focus-visible" in PRIVACY_DASHBOARD_HTML
    assert "prefers-reduced-motion" in PRIVACY_DASHBOARD_HTML
    assert "replaceChildren" in PRIVACY_DASHBOARD_HTML
    assert ".innerHTML" not in PRIVACY_DASHBOARD_HTML


def test_repository_default_frontends_contain_no_analytics_client() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    files = [
        repository_root / "frontend" / "personal-intelligence-system" / "app" / "layout.tsx",
        repository_root / "frontend" / "personal-intelligence-system" / "package.json",
    ]

    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "@vercel/analytics" not in combined
    assert "<Analytics" not in combined


def test_compatibility_routes_remain_local_source_grounded_and_retention_aware(
    config: MemoryConfig,
    clock: MutableClock,
    synthetic_png: bytes,
) -> None:
    encoded = base64.b64encode(synthetic_png).decode("ascii")
    with _client(config, clock) as client:
        assert client.get("/").status_code == 200
        assert client.get("/privacy").status_code == 200
        uploaded = client.post(
            "/upload",
            json={
                "type": "video",
                "payload": encoded,
                "source": "synthetic",
                "retention_class": "session",
            },
        ).json()
        content_id = uploaded["memory"]["content_id"]
        process = client.post(
            "/memory/process-next",
            headers={"X-Synapse-Intent": "process"},
        )
        search = client.get("/memory/search", params={"q": "synthetic invoice"})
        question = client.post("/ask_question", json={"question": "invoice reference"})
        screenshot = client.post(
            "/ask_screenshot",
            json={"screenshot": encoded, "question": "invoice"},
        )
        graph = client.get("/graph")
        clock.advance(days=2)
        sweep = client.post(
            "/memory/retention/sweep",
            headers={"X-Synapse-Intent": "retention"},
        )
        deletion = client.get(f"/memory/{content_id}/deletion")

    assert process.status_code == 200
    assert search.json()["evidence"][0]["source_id"] == content_id
    assert question.json()["result"]["sources"] == [content_id]
    assert screenshot.json()["memory"]["content_id"] == content_id
    assert graph.json() == {"nodes": [], "edges": [], "mode": "local-only"}
    assert sweep.json()["count"] == 1
    assert deletion.json()["complete"] is True
