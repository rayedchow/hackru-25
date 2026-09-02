"""FastAPI boundary for the local-first memory service."""

from __future__ import annotations

import base64
import binascii
import hmac
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import StringConstraints

from .dashboard import PRIVACY_DASHBOARD_HTML
from .errors import InvalidUpload, MemoryPipelineError, OwnerMismatch
from .models import MemorySummary, RetentionClass, StrictModel
from .service import MemoryService


class UploadBody(StrictModel):
    type: Literal["video"]
    payload: Annotated[str, StringConstraints(min_length=4, max_length=45_000_000)]
    source: Annotated[str, StringConstraints(max_length=64)] | None = None
    retention_class: Literal["session", "standard", "keep"] = "standard"


class QuestionBody(StrictModel):
    question: Annotated[str, StringConstraints(min_length=1, max_length=2_000)]


class ScreenshotQuestionBody(StrictModel):
    screenshot: Annotated[str, StringConstraints(min_length=4, max_length=45_000_000)]
    question: Annotated[str, StringConstraints(min_length=1, max_length=2_000)] | None = None


def decode_image_payload(payload: str, max_bytes: int) -> bytes:
    if len(payload) > ((max_bytes + 2) // 3) * 4 + 8:
        raise InvalidUpload("The screenshot exceeds the configured upload limit.")
    try:
        value = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidUpload("The screenshot payload is not valid base64.") from exc
    if len(value) > max_bytes:
        raise InvalidUpload("The screenshot exceeds the configured upload limit.")
    return value


UploadObserver = Callable[[bytes], Awaitable[dict[str, object]]]
logger = logging.getLogger(__name__)


def memory_router(
    service: MemoryService, *, upload_observer: UploadObserver | None = None
) -> APIRouter:
    router = APIRouter()

    def owner_from_header(value: str | None) -> str:
        if value and not hmac.compare_digest(
            value.encode("utf-8"), service.config.owner_id.encode("utf-8")
        ):
            raise OwnerMismatch("The requested owner is not available in this local profile.")
        return service.config.owner_id

    def require_intent(value: str | None, expected: str) -> None:
        if value is None or not hmac.compare_digest(value, expected):
            raise OwnerMismatch("This local control operation requires an explicit intent header.")

    @router.get("/", response_class=HTMLResponse)
    @router.get("/privacy", response_class=HTMLResponse)
    async def privacy_dashboard() -> str:
        return PRIVACY_DASHBOARD_HTML

    @router.get("/privacy/status")
    async def privacy_status(
        x_synapse_owner: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        owner_id = owner_from_header(x_synapse_owner)
        status = await run_in_threadpool(service.status, owner_id=owner_id)
        return status.model_dump(mode="json")

    @router.post("/upload")
    async def upload(
        body: UploadBody,
        x_synapse_owner: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        owner_id = owner_from_header(x_synapse_owner)
        image_bytes = await run_in_threadpool(
            decode_image_payload, body.payload, service.config.max_upload_bytes
        )
        envelope, created = await run_in_threadpool(
            service.ingest,
            image_bytes,
            owner_id=owner_id,
            source=body.source,
            retention_class=RetentionClass(body.retention_class),
        )
        event: dict[str, object] | None = None
        if upload_observer:
            try:
                event = await upload_observer(image_bytes)
            except Exception:
                # The ciphertext and queue row already exist. A best-effort transient
                # dashboard observation must not turn that success into an ambiguous 5xx.
                logger.exception("Transient capture observation failed after encrypted ingest")
                event = {"type": "capture", "metadata_status": "unavailable"}
        return {
            "ok": True,
            "created": created,
            "memory": MemorySummary.from_envelope(envelope).model_dump(mode="json"),
            "capture_event": event,
        }

    @router.post("/memory/process-next")
    async def process_next(
        x_synapse_intent: Annotated[str | None, Header()] = None,
        x_synapse_owner: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_intent(x_synapse_intent, "process")
        owner_id = owner_from_header(x_synapse_owner)
        record = await run_in_threadpool(service.process_next, owner_id=owner_id)
        return {
            "processed": record is not None,
            "memory": (
                MemorySummary.from_envelope(record.envelope).model_dump(mode="json")
                if record
                else None
            ),
        }

    @router.get("/memory/search")
    async def search_memory(
        q: Annotated[str, Query(min_length=1, max_length=2_000)],
        limit: Annotated[int, Query(ge=1, le=50)] = 10,
        x_synapse_owner: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        owner_id = owner_from_header(x_synapse_owner)
        result = await run_in_threadpool(service.search, q, owner_id=owner_id, limit=limit)
        return result.model_dump(mode="json")

    @router.delete("/memory/{content_id}")
    async def delete_memory(
        content_id: str,
        x_synapse_intent: Annotated[str | None, Header()] = None,
        x_synapse_owner: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        require_intent(x_synapse_intent, "delete")
        owner_id = owner_from_header(x_synapse_owner)
        receipt = await run_in_threadpool(service.delete, content_id, owner_id=owner_id)
        return JSONResponse(
            receipt.model_dump(mode="json"), status_code=200 if receipt.complete else 202
        )

    @router.get("/memory/{content_id}/deletion")
    async def deletion_status(
        content_id: str,
        x_synapse_owner: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        owner_id = owner_from_header(x_synapse_owner)
        receipt = await run_in_threadpool(
            service.database.deletion_receipt,
            content_id=content_id,
            owner_id=owner_id,
        )
        return receipt.model_dump(mode="json")

    @router.post("/memory/retention/sweep")
    async def sweep_retention(
        limit: Annotated[int, Query(ge=1, le=1_000)] = 100,
        x_synapse_intent: Annotated[str | None, Header()] = None,
        x_synapse_owner: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_intent(x_synapse_intent, "retention")
        owner_id = owner_from_header(x_synapse_owner)
        receipts = await run_in_threadpool(service.sweep_expired, owner_id=owner_id, limit=limit)
        return {
            "count": len(receipts),
            "receipts": [receipt.model_dump(mode="json") for receipt in receipts],
        }

    @router.post("/ask_question")
    async def ask_question(
        body: QuestionBody,
        x_synapse_owner: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        owner_id = owner_from_header(x_synapse_owner)
        result = await run_in_threadpool(service.search, body.question, owner_id=owner_id)
        return {
            "status": "received",
            "result": {
                "answer": result.answer,
                "communities": [],
                "cards": [hit.model_dump(mode="json") for hit in result.evidence],
                "projection": "none",
                "sources": [hit.source_id for hit in result.evidence],
                "insufficient_evidence": result.insufficient_evidence,
            },
        }

    @router.post("/ask_screenshot")
    async def ask_screenshot(
        body: ScreenshotQuestionBody,
        x_synapse_owner: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        owner_id = owner_from_header(x_synapse_owner)
        image_bytes = await run_in_threadpool(
            decode_image_payload, body.screenshot, service.config.max_upload_bytes
        )
        envelope, created = await run_in_threadpool(
            service.ingest,
            image_bytes,
            owner_id=owner_id,
            source="desktop",
        )
        result = await run_in_threadpool(
            service.search,
            body.question or "screenshot",
            owner_id=owner_id,
        )
        return {
            "status": "stored",
            "created": created,
            "memory": MemorySummary.from_envelope(envelope).model_dump(mode="json"),
            "result": {
                "answer": result.answer,
                "communities": [],
                "cards": [hit.model_dump(mode="json") for hit in result.evidence],
                "projection": "none",
                "sources": [hit.source_id for hit in result.evidence],
                "insufficient_evidence": result.insufficient_evidence,
            },
        }

    @router.get("/graph")
    async def local_graph() -> dict[str, object]:
        return {"nodes": [], "edges": [], "mode": "local-only"}

    return router


async def memory_error_handler(_request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, MemoryPipelineError):
        raise error
    return JSONResponse(
        {"ok": False, "error": error.code, "message": error.public_message},
        status_code=error.status_code,
    )
