"""
Backend API Bridge Agent Tools
Generate local PHP API bridge files for a migration slice.
"""

from __future__ import annotations

from typing import Any

from tools.migration_spec_tools import MigrationSpecTool


class BackendAPIBridgeTool:
    """Generate backend API bridge files without writing to remote GitHub."""

    def __init__(self, migration_spec_tool: MigrationSpecTool | None = None) -> None:
        self.migration_spec_tool = migration_spec_tool or MigrationSpecTool()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "generate_backend_api_bridge_files",
                "description": "Generate local PHP API bridge files for a PHP-to-React migration slice",
            }
        ]

    def generate_backend_api_bridge_files(
        self,
        repo_name: str,
        module_name: str,
        target_ref: str = "main",
        module_path: str | None = None,
        related_paths: list[str] | None = None,
        focus_terms: list[str] | None = None,
        table_names: list[str] | None = None,
        schema_name: str | None = None,
        work_item_id: int | None = None,
        api_root: str = "api",
        include_database_schema: bool = True,
    ) -> dict[str, Any]:
        spec_result = self.migration_spec_tool.build_migration_spec(
            repo_name=repo_name,
            module_name=module_name,
            target_ref=target_ref,
            module_path=module_path,
            related_paths=related_paths,
            focus_terms=focus_terms,
            table_names=table_names,
            schema_name=schema_name,
            work_item_id=work_item_id,
            include_database_schema=include_database_schema,
        )
        if not spec_result.get("ok"):
            return {
                "ok": False,
                "agent": "backend_api_bridge_agent",
                "error": "Migration spec failed",
                "migration_spec_context": spec_result,
            }

        migration_spec = spec_result.get("migration_spec", {})
        local_files = self._generate_files(module_name, api_root, migration_spec)
        return {
            "ok": True,
            "agent": "backend_api_bridge_agent",
            "repo_name": repo_name,
            "target_ref": target_ref,
            "module_name": module_name,
            "module_path": module_path,
            "related_paths": related_paths or [],
            "focus_terms": focus_terms or [],
            "table_names": table_names or [],
            "schema_name": spec_result.get("schema_name") or schema_name,
            "work_item_id": work_item_id,
            "api_root": api_root,
            "remote_writes_enabled": False,
            "file_count": len(local_files),
            "local_files": local_files,
            "migration_spec_context": spec_result,
            "expected_agent_output": self._expected_agent_output(),
        }

    def _generate_files(self, module_name: str, api_root: str, migration_spec: dict[str, Any]) -> list[dict[str, str]]:
        feature_slug = self._slug(module_name)
        feature_dir = f"{api_root.rstrip('/')}/{feature_slug}"
        files = [
            {"path": f"{feature_dir}/bootstrap.php", "content": self._bootstrap_content()},
            {"path": f"{feature_dir}/response.php", "content": self._response_content()},
            {"path": f"{feature_dir}/README.md", "content": self._readme_content(module_name, migration_spec)},
        ]
        for endpoint in migration_spec.get("backend_api_spec", []):
            files.append(
                {
                    "path": f"{feature_dir}/{self._endpoint_file_name(endpoint)}.php",
                    "content": self._endpoint_content(endpoint),
                }
            )
        return files

    def _bootstrap_content(self) -> str:
        return """<?php
declare(strict_types=1);

require_once __DIR__ . '/../../_dbconnect.php';
require_once __DIR__ . '/response.php';

if (session_status() !== PHP_SESSION_ACTIVE) {
    session_start();
}

function require_api_session(): array
{
    if (empty($_SESSION)) {
        api_error('Unauthorized', 401);
    }

    return $_SESSION;
}
"""

    def _response_content(self) -> str:
        return """<?php
declare(strict_types=1);

function api_json(array $payload, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json');
    echo json_encode($payload);
    exit;
}

function api_error(string $message, int $status = 400, array $context = []): void
{
    api_json(['ok' => false, 'error' => $message, 'context' => $context], $status);
}
"""

    def _endpoint_content(self, endpoint: dict[str, Any]) -> str:
        methods = endpoint.get("methods", ["GET"])
        primary_method = methods[0] if methods else "GET"
        tables = endpoint.get("tables", [])
        contracts = endpoint.get("contracts", [])
        route = endpoint.get("route")
        source_path = endpoint.get("source_path")
        notes = endpoint.get("notes", [])
        table_comment = ", ".join(tables) or "unknown tables"
        contract_comment = self._contract_comment(contracts)
        notes_comment = "\n".join(f"// - {note}" for note in notes) or "// - No notes captured."
        body = self._endpoint_body(primary_method, tables)
        return f"""<?php
declare(strict_types=1);

require_once __DIR__ . '/bootstrap.php';

// Generated bridge endpoint for {route}
// Legacy source: {source_path}
// Tables: {table_comment}
// Contracts: {contract_comment}
// Notes:
{notes_comment}

if ($_SERVER['REQUEST_METHOD'] !== '{primary_method}') {{
    api_error('Method not allowed', 405, ['allowed' => ['{primary_method}']]);
}}

$session = require_api_session();

try {{
{body}
}} catch (Throwable $exception) {{
    api_error('Backend API bridge failed', 500, ['message' => $exception->getMessage()]);
}}
"""

    def _endpoint_body(self, method: str, tables: list[str]) -> str:
        table = tables[0] if tables else None
        if method == "GET" and table:
            return f"""    $sql = 'SELECT * FROM `{table}` LIMIT 200';
    $result = mysqli_query($conn, $sql);
    if (!$result) {{
        api_error('Query failed', 500, ['mysql_error' => mysqli_error($conn)]);
    }}

    $rows = [];
    while ($row = mysqli_fetch_assoc($result)) {{
        $rows[] = $row;
    }}

    api_json(['ok' => true, 'data' => $rows]);"""
        return """    $payload = json_decode(file_get_contents('php://input'), true) ?: [];
    api_json([
        'ok' => true,
        'data' => null,
        'payload' => $payload,
        'message' => 'TODO: implement mutation behavior using legacy PHP evidence.',
    ]);"""

    def _endpoint_file_name(self, endpoint: dict[str, Any]) -> str:
        route = endpoint.get("route") or endpoint.get("source_path") or "endpoint"
        return self._slug(route.rsplit("/", 1)[-1] or "endpoint")

    def _contract_comment(self, contracts: list[dict[str, Any]]) -> str:
        if not contracts:
            return "none"
        return "; ".join(
            f"{contract.get('table_name')}: create={contract.get('create_fields', [])}, update={contract.get('update_fields', [])}"
            for contract in contracts
        )

    def _readme_content(self, module_name: str, migration_spec: dict[str, Any]) -> str:
        endpoints = "\n".join(
            f"- `{endpoint.get('route')}` from `{endpoint.get('source_path')}`"
            for endpoint in migration_spec.get("backend_api_spec", [])
        )
        risks = "\n".join(f"- {risk}" for risk in migration_spec.get("risks", []))
        return f"""# {module_name} Backend API Bridge

Generated local PHP API bridge scaffold.

## Endpoints
{endpoints or "- No endpoints generated."}

## Risks
{risks or "- None captured."}

Review and test locally before committing.
"""

    def _slug(self, value: str) -> str:
        normalized = value.replace("_", "-").replace("/", "-").replace(" ", "-").lower()
        return "-".join(part for part in normalized.split("-") if part)

    def _expected_agent_output(self) -> dict[str, Any]:
        return {
            "local_files": ["PHP API bridge files for local application in the source repo."],
            "next_steps": ["Apply local_files to the local source repo, wire routing/proxy, test with React locally."],
            "remote_writes_enabled": False,
        }
