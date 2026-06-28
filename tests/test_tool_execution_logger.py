from __future__ import annotations

import json
from pathlib import Path

from utils.tool_execution_logger import logged_tool


def test_logged_tool_writes_jsonl_record_and_redacts_secrets(tmp_path: Path, monkeypatch):
    log_file = tmp_path / "tool-execution.jsonl"
    monkeypatch.setenv("MCP_TOOL_LOG_FILE", str(log_file))

    @logged_tool("build_migration_spec")
    def fake_tool(repo_name: str, password: str) -> dict:
        return {"ok": True, "agent": "migration_spec_agent", "repo_name": repo_name, "file_count": 3}

    result = fake_tool(repo_name="procurex", password="secret-value")

    assert result["ok"] is True
    record = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert record["event"] == "tool_execution"
    assert record["tool_name"] == "build_migration_spec"
    assert record["agent"] == "migration_spec_agent"
    assert record["status"] == "success"
    assert record["inputs"]["repo_name"] == "procurex"
    assert record["inputs"]["password"] == "[REDACTED]"
    assert record["result_summary"]["file_count"] == 3


def test_logged_tool_records_errors(tmp_path: Path, monkeypatch):
    log_file = tmp_path / "tool-errors.jsonl"
    monkeypatch.setenv("MCP_TOOL_LOG_FILE", str(log_file))

    @logged_tool("get_repo_file")
    def failing_tool(repo_name: str) -> dict:
        raise RuntimeError(f"cannot read {repo_name}")

    try:
        failing_tool(repo_name="procurex")
    except RuntimeError:
        pass

    record = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert record["tool_name"] == "get_repo_file"
    assert record["status"] == "error"
    assert "RuntimeError" in record["error"]
