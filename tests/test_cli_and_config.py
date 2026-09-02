from __future__ import annotations

import json
from pathlib import Path

import pytest
from synapse_memory.cli import main
from synapse_memory.config import MemoryConfig
from synapse_memory.errors import ConfigurationError


def test_operational_cli_commands_use_local_state_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SYNAPSE_DATA_ROOT", str(tmp_path / "private"))

    assert main(["status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["mode"] == "local-only"
    assert status["providers"]["remote"] == "disabled"

    assert main(["process-one"]) == 0
    assert json.loads(capsys.readouterr().out) == {"memory": None, "processed": False}

    assert main(["sweep", "--limit", "7"]) == 0
    assert json.loads(capsys.readouterr().out) == []

    assert main(["rotate-key"]) == 0
    rotated = json.loads(capsys.readouterr().out)
    assert rotated["active_key_id"].startswith("key-")


def test_environment_configuration_is_bounded_and_normalized(tmp_path: Path) -> None:
    config = MemoryConfig.from_env(
        {
            "SYNAPSE_DATA_ROOT": str(tmp_path / "private"),
            "SYNAPSE_OWNER_ID": "owner-fixture",
            "SYNAPSE_REMOTE_ENABLED": "true",
            "SYNAPSE_REMOTE_ENDPOINT": "http://127.0.0.1:9000/process",
            "SYNAPSE_REMOTE_TIMEOUT_SECONDS": "12",
            "SYNAPSE_DEFAULT_RETENTION_DAYS": "45",
            "SYNAPSE_SESSION_RETENTION_DAYS": "2",
            "SYNAPSE_MAX_UPLOAD_BYTES": "4096",
            "SYNAPSE_LEASE_SECONDS": "15",
            "SYNAPSE_MAX_RETRIES": "4",
            "SYNAPSE_DISABLE_KEY_AUTOCREATE": "yes",
            "SYNAPSE_DENIED_SOURCES": "Private App, private app, BANK",
            "SYNAPSE_EXCLUSION_TERMS": "Project Mica, CLIENT",
        }
    )

    assert config.owner_id == "owner-fixture"
    assert config.remote_enabled is True
    assert config.remote_timeout_seconds == 12
    assert config.default_retention_days == 45
    assert config.auto_create_key is False
    assert config.denied_sources == ("bank", "private app")
    assert config.exclusion_terms == ("client", "project mica")


def test_environment_rejects_invalid_integer(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="must be an integer"):
        MemoryConfig.from_env(
            {
                "SYNAPSE_DATA_ROOT": str(tmp_path),
                "SYNAPSE_MAX_RETRIES": "many",
            }
        )
