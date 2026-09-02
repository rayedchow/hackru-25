"""Synapse local-first API and transient capture monitor."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from io import BytesIO

import uvicorn
import ws_manager
from detection.app import KEYWORDS, detect_app
from detection.scroll import detect_scroll
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from PIL import Image
from starlette.middleware.trustedhost import TrustedHostMiddleware
from synapse_memory import MemoryConfig, MemoryService
from synapse_memory.api import memory_error_handler, memory_router
from synapse_memory.errors import MemoryPipelineError
from synapse_memory.providers import TesseractOCRProvider

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logging.getLogger("PIL").setLevel(logging.WARNING)
logger = logging.getLogger("synapse")


def _enabled(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "on"}


class LocalAppSourceProvider:
    """Observe a coarse app label locally before deny-policy persistence."""

    name = "local-app-detector-v1"

    def __init__(self) -> None:
        self._ocr = TesseractOCRProvider(timeout_seconds=5)

    def detect(self, image_bytes: bytes) -> str:
        text = self._ocr.extract_text(image_bytes).casefold()
        for app_name, keywords in KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return app_name
        return "unknown"


class CaptureObserver:
    """Best-effort in-memory UI metadata; screenshot bytes are never broadcast."""

    def __init__(self) -> None:
        self.session_id = str(uuid.uuid4())
        self.frame_count = 0
        self.last_hash: int | None = None
        self.last_scroll_time = 0.0
        self._lock = asyncio.Lock()

    async def observe(self, image_bytes: bytes) -> dict[str, object]:
        async with self._lock:
            app_name, scroll_detected, current_hash = await asyncio.to_thread(
                self._inspect, image_bytes, self.last_hash
            )
            self.frame_count += 1
            now = time.monotonic()
            self.last_hash = current_hash
            did_scroll = scroll_detected and now - self.last_scroll_time >= 2.5
            if did_scroll:
                self.last_scroll_time = now
            event = {
                "type": "capture",
                "session_id": self.session_id,
                "frame_number": self.frame_count,
                "app": app_name,
                "did_scroll": did_scroll,
            }
            await ws_manager.broadcast(event)
            return event

    @staticmethod
    def _inspect(image_bytes: bytes, previous_hash: int | None) -> tuple[str, bool, int]:
        with Image.open(BytesIO(image_bytes)) as opened:
            image = opened.convert("RGB")
            app_name = detect_app(image)
            scroll_detected, current_hash = detect_scroll(image, previous_hash)
        return app_name, scroll_detected, current_hash


def create_app(
    *,
    service: MemoryService | None = None,
    observer: CaptureObserver | None = None,
    capture_monitor_enabled: bool | None = None,
    allowed_origins: tuple[str, ...] | None = None,
    allowed_hosts: tuple[str, ...] | None = None,
) -> FastAPI:
    if service is None:
        config = MemoryConfig.from_env()
        source_provider = LocalAppSourceProvider() if config.denied_sources else None
        selected_service = MemoryService(config, source_observation_provider=source_provider)
    else:
        selected_service = service
    monitor_enabled = (
        _enabled(os.getenv("SYNAPSE_CAPTURE_MONITOR_ENABLED"))
        if capture_monitor_enabled is None
        else capture_monitor_enabled
    )
    selected_observer = (observer or CaptureObserver()) if monitor_enabled else None
    application = FastAPI(
        title="Synapse local memory",
        version="1.0.0",
        description="Local-first encrypted screenshot memory and explicit retention status.",
    )
    selected_origins = (
        allowed_origins
        if allowed_origins is not None
        else tuple(
            value.strip()
            for value in os.getenv(
                "SYNAPSE_ALLOWED_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000"
            ).split(",")
            if value.strip()
        )
    )
    selected_hosts = (
        allowed_hosts
        if allowed_hosts is not None
        else tuple(
            value.strip()
            for value in os.getenv("SYNAPSE_ALLOWED_HOSTS", "127.0.0.1,localhost,[::1]").split(",")
            if value.strip()
        )
    )
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=list(selected_hosts))

    @application.middleware("http")
    async def reject_untrusted_browser_origin(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        origin = request.headers.get("origin")
        if origin is not None and origin not in selected_origins:
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "error": "untrusted_origin",
                    "message": "The browser origin is not allowed by local policy.",
                },
            )
        return await call_next(request)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(selected_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Accept", "X-Synapse-Owner", "X-Synapse-Intent"],
    )
    application.add_exception_handler(MemoryPipelineError, memory_error_handler)
    application.include_router(
        memory_router(
            selected_service,
            upload_observer=selected_observer.observe if selected_observer is not None else None,
        )
    )
    application.state.memory_service = selected_service
    application.state.capture_monitor_enabled = monitor_enabled

    @application.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        if not monitor_enabled or websocket.headers.get("origin") not in selected_origins:
            await websocket.close(code=1008)
            return
        await ws_manager.websocket_endpoint(websocket)

    return application


app = create_app()


if __name__ == "__main__":
    bind_host = os.getenv("SYNAPSE_BIND_HOST", "127.0.0.1")
    bind_port = int(os.getenv("SYNAPSE_BIND_PORT", "8000"))
    logger.info("Synapse privacy status: http://%s:%s/privacy", bind_host, bind_port)
    uvicorn.run("server:app", host=bind_host, port=bind_port, reload=False)
