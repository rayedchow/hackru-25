"""Synapse local-first API and transient capture monitor."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from io import BytesIO

import uvicorn
import ws_manager
from detection.app import detect_app
from detection.scroll import detect_scroll
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from synapse_memory import MemoryConfig, MemoryService
from synapse_memory.api import memory_error_handler, memory_router
from synapse_memory.errors import MemoryPipelineError

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logging.getLogger("PIL").setLevel(logging.WARNING)
logger = logging.getLogger("synapse")


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
    *, service: MemoryService | None = None, observer: CaptureObserver | None = None
) -> FastAPI:
    selected_service = service or MemoryService(MemoryConfig.from_env())
    selected_observer = observer or CaptureObserver()
    application = FastAPI(
        title="Synapse local memory",
        version="1.0.0",
        description="Local-first encrypted screenshot memory and explicit retention status.",
    )
    allowed_origins = tuple(
        value.strip()
        for value in os.getenv(
            "SYNAPSE_ALLOWED_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000"
        ).split(",")
        if value.strip()
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Accept", "X-Synapse-Owner", "X-Synapse-Intent"],
    )
    application.add_exception_handler(MemoryPipelineError, memory_error_handler)
    application.include_router(
        memory_router(selected_service, upload_observer=selected_observer.observe)
    )
    application.state.memory_service = selected_service

    @application.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await ws_manager.websocket_endpoint(websocket)

    return application


app = create_app()


if __name__ == "__main__":
    bind_host = os.getenv("SYNAPSE_BIND_HOST", "127.0.0.1")
    bind_port = int(os.getenv("SYNAPSE_BIND_PORT", "8000"))
    logger.info("Synapse privacy status: http://%s:%s/privacy", bind_host, bind_port)
    uvicorn.run("server:app", host=bind_host, port=bind_port, reload=False)
