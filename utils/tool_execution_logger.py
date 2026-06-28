from __future__ import annotations

import functools
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar, cast

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "password",
    "pat",
    "secret",
    "token",
)
MAX_STRING_LENGTH = 500
MAX_LIST_ITEMS = 20
MAX_DICT_ITEMS = 30


def logged_tool(tool_name: str) -> Callable[[F], F]:
    """Log a structured JSONL record for each MCP tool execution."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            result: Any = None
            error: str | None = None
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as exc:
                error = f"{exc.__class__.__name__}: {exc}"
                raise
            finally:
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                log_tool_execution(
                    tool_name=tool_name,
                    args=args,
                    kwargs=kwargs,
                    result=result,
                    duration_ms=duration_ms,
                    error=error,
                )

        return cast(F, wrapper)

    return decorator


def log_tool_execution(
    tool_name: str,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    result: Any = None,
    duration_ms: float | None = None,
    error: str | None = None,
) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": os.getenv("MCP_SERVER_NAME", "buildprocure-mcp"),
        "event": "tool_execution",
        "tool_name": tool_name,
        "agent": _agent_name(tool_name, result),
        "status": _status(result, error),
        "duration_ms": duration_ms,
        "inputs": _summarize_inputs(args, kwargs or {}),
        "result_summary": _summarize_result(result),
        "error": error,
    }
    _write_jsonl(record)
    logger.info(
        "MCP tool executed tool=%s agent=%s status=%s duration_ms=%s",
        record["tool_name"],
        record["agent"],
        record["status"],
        duration_ms,
    )


def _agent_name(tool_name: str, result: Any) -> str:
    if isinstance(result, dict) and result.get("agent"):
        return str(result["agent"])
    if tool_name.startswith("build_architecture") or tool_name.startswith("create_architecture"):
        return "architecture_agent"
    if tool_name.startswith("analyze_legacy_php"):
        return "legacy_php_analysis_agent"
    if tool_name.startswith("build_database_model"):
        return "database_model_context_agent"
    if tool_name.startswith("build_migration_spec"):
        return "migration_spec_agent"
    if tool_name.startswith("build_react_conversion"):
        return "react_conversion_agent"
    if tool_name.startswith("write_react_conversion"):
        return "react_code_writer_agent"
    if tool_name.startswith("run_migration_request"):
        return "migration_orchestrator_agent"
    if tool_name.startswith("generate_backend_api_bridge"):
        return "backend_api_bridge_agent"
    if "pr_review" in tool_name or tool_name.startswith("get_pull_request") or tool_name.startswith("list_open_pull"):
        return "pr_review_agent"
    return "basic_tool"


def _status(result: Any, error: str | None) -> str:
    if error:
        return "error"
    if isinstance(result, dict) and result.get("ok") is False:
        return "failed"
    return "success"


def _summarize_inputs(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    summarized = {key: _sanitize_value(key, value) for key, value in kwargs.items()}
    if args:
        summarized["_positional_count"] = len(args)
    return summarized


def _summarize_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"type": type(result).__name__}

    summary_keys = (
        "ok",
        "repo_name",
        "target_ref",
        "module_name",
        "work_item_id",
        "pr_number",
        "count",
        "result_count",
        "file_count",
        "table_count",
        "created_ticket_count",
        "suggested_ticket_count",
        "error",
    )
    return {
        key: _sanitize_value(key, result.get(key))
        for key in summary_keys
        if key in result
    }


def _sanitize_value(key: str, value: Any) -> Any:
    key_lower = key.lower()
    if any(part in key_lower for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, str):
        return value if len(value) <= MAX_STRING_LENGTH else value[:MAX_STRING_LENGTH] + "...[truncated]"
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return [_sanitize_value(key, item) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, tuple):
        return [_sanitize_value(key, item) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, dict):
        items = list(value.items())[:MAX_DICT_ITEMS]
        return {str(item_key): _sanitize_value(str(item_key), item_value) for item_key, item_value in items}
    return str(value)


def _write_jsonl(record: dict[str, Any]) -> None:
    log_path = Path(os.getenv("MCP_TOOL_LOG_FILE", "logs/tool-execution.jsonl"))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        logger.warning("Failed to write MCP tool execution log to %s: %s", log_path, exc)
