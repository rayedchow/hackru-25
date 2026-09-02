"""Operational commands for the local queue and key lifecycle."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .config import MemoryConfig
from .service import MemoryService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="synapse-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="print provider, retention, and queue status")
    subparsers.add_parser("process-one", help="claim and process at most one queued memory")
    sweep = subparsers.add_parser("sweep", help="delete expired local memories")
    sweep.add_argument("--limit", type=int, default=100)
    subparsers.add_parser(
        "rotate-key", help="use a new key for future blobs while retaining decrypt-only old keys"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    service = MemoryService(MemoryConfig.from_env())
    if arguments.command == "status":
        payload: object = service.status().model_dump(mode="json")
    elif arguments.command == "process-one":
        record = service.process_next()
        payload = {
            "processed": record is not None,
            "memory": record.envelope.model_dump(mode="json") if record else None,
        }
    elif arguments.command == "sweep":
        receipts = service.sweep_expired(limit=arguments.limit)
        payload = [receipt.model_dump(mode="json") for receipt in receipts]
    else:
        payload = {"active_key_id": service.rotate_key()}
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
