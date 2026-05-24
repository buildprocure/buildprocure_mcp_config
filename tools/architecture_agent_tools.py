"""
Architecture Agent Tools
Evidence gathering for PHP-to-React migration architecture.
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath
from typing import Any

from tools.agent_context_tools import AgentContextTool
from tools.database_schema_tools import DatabaseSchemaTool
from tools.repository_content_tools import RepositoryContentTool
from utils.azure_devops_helper import AzureDevOpsHelper
from utils.github_helpers import GitHubHelper

logger = logging.getLogger(__name__)

PHP_EXTENSIONS = (".php", ".inc")
CONFIG_NAMES = {
    ".env.example",
    "composer.json",
    "package.json",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
}
MAX_ARCHITECTURE_FILES = 80
MAX_DATABASE_TABLES = 150


class ArchitectureAgentTool:
    """Build architecture evidence for ProcureX migration planning."""

    def __init__(
        self,
        github: GitHubHelper | None = None,
        agent_context_tool: AgentContextTool | None = None,
        content_tool: RepositoryContentTool | None = None,
        database_schema_tool: DatabaseSchemaTool | None = None,
        azure: AzureDevOpsHelper | None = None,
    ) -> None:
        self.github = github or GitHubHelper()
        self.agent_context_tool = agent_context_tool or AgentContextTool(github=self.github)
        self.content_tool = content_tool or RepositoryContentTool(github=self.github)
        self.database_schema_tool = database_schema_tool or DatabaseSchemaTool()
        self.azure = azure or AzureDevOpsHelper()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "build_architecture_analysis",
                "description": "Collect architecture evidence for PHP-to-React migration planning",
            }
        ]

    def build_architecture_analysis(
        self,
        repo_name: str,
        target_ref: str = "main",
        module_path: str | None = None,
        work_item_id: int | None = None,
        include_database_schema: bool = True,
    ) -> dict[str, Any]:
        tree_result = self.content_tool.get_repo_tree(repo_name, target_ref=target_ref)
        tree = tree_result.get("tree", [])
        scoped_tree = self._scope_tree(tree, module_path)

        selected_paths = self._select_architecture_files(scoped_tree)
        agent_context = self.agent_context_tool.build_agent_context(
            repo_name,
            target_ref=target_ref,
            paths=selected_paths,
        )

        database_context = self._get_database_context(include_database_schema)
        azure_context = self._get_azure_context(work_item_id)
        architecture_context = self._build_architecture_context(
            tree=scoped_tree,
            selected_files=agent_context.get("selected_files", []),
            database_context=database_context,
        )

        return {
            "ok": bool(tree_result.get("ok") and agent_context.get("ok")),
            "agent": "architecture_agent",
            "repo_name": repo_name,
            "target_ref": target_ref,
            "module_path": module_path,
            "work_item_id": work_item_id,
            "architecture_context": architecture_context,
            "repository_context": {
                "repository": agent_context.get("repository"),
                "tree_file_count": len(scoped_tree),
                "selected_paths": selected_paths,
                "selected_files": agent_context.get("selected_files", []),
                "file_errors": agent_context.get("file_errors", []),
                "manifest_summary": agent_context.get("manifest_summary", {}),
                "config_summary": agent_context.get("config_summary", {}),
                "tree_error": tree_result.get("error"),
            },
            "database_context": database_context,
            "azure_context": azure_context,
            "expected_agent_output": self._expected_agent_output(),
        }

    def _scope_tree(self, tree: list[str], module_path: str | None) -> list[str]:
        if not module_path:
            return tree
        prefix = module_path.strip("/")
        return [path for path in tree if path == prefix or path.startswith(f"{prefix}/")]

    def _select_architecture_files(self, tree: list[str]) -> list[str]:
        selected = []
        for path in tree:
            path_obj = PurePosixPath(path)
            name = path_obj.name
            lower_path = path.lower()
            if name in CONFIG_NAMES:
                selected.append(path)
            elif name.lower() in {"index.php", "config.php", "db.php", "database.php", "autoload.php"}:
                selected.append(path)
            elif lower_path.startswith((".github/workflows/", "config/", "includes/", "inc/", "lib/")):
                selected.append(path)
            elif lower_path.endswith(PHP_EXTENSIONS) and self._looks_like_entrypoint(path):
                selected.append(path)
        return list(dict.fromkeys(selected))[:MAX_ARCHITECTURE_FILES]

    def _looks_like_entrypoint(self, path: str) -> bool:
        parts = PurePosixPath(path).parts
        if len(parts) <= 2:
            return True
        return any(part.lower() in {"pages", "views", "modules", "controllers"} for part in parts)

    def _build_architecture_context(
        self,
        tree: list[str],
        selected_files: list[dict[str, Any]],
        database_context: dict[str, Any],
    ) -> dict[str, Any]:
        php_files = [path for path in tree if path.lower().endswith(PHP_EXTENSIONS)]
        return {
            "repo_shape": self._repo_shape(tree),
            "legacy_php_entrypoints": self._entrypoint_candidates(php_files),
            "shared_includes": self._shared_include_candidates(tree),
            "module_candidates": self._module_candidates(tree, database_context.get("tables", [])),
            "database_tables": database_context.get("tables", []),
            "routing_hints": self._routing_hints(tree),
            "auth_session_hints": self._content_hints(selected_files, ["$_SESSION", "session_start", "auth", "login"]),
            "sql_usage_hints": self._content_hints(selected_files, ["SELECT ", "INSERT ", "UPDATE ", "DELETE ", "mysqli", "PDO"]),
            "file_upload_hints": self._content_hints(selected_files, ["$_FILES", "move_uploaded_file", "multipart/form-data"]),
            "migration_risks": self._migration_risks(tree, selected_files, database_context),
        }

    def _repo_shape(self, tree: list[str]) -> dict[str, Any]:
        top_level = sorted({PurePosixPath(path).parts[0] for path in tree if PurePosixPath(path).parts})
        return {
            "top_level_entries": top_level,
            "php_file_count": len([path for path in tree if path.lower().endswith(PHP_EXTENSIONS)]),
            "config_file_count": len([path for path in tree if PurePosixPath(path).name in CONFIG_NAMES]),
        }

    def _entrypoint_candidates(self, php_files: list[str]) -> list[str]:
        return [
            path
            for path in php_files
            if self._looks_like_entrypoint(path)
            and not any(part.startswith(".") for part in PurePosixPath(path).parts)
        ][:100]

    def _shared_include_candidates(self, tree: list[str]) -> list[str]:
        prefixes = ("includes/", "include/", "inc/", "lib/", "config/", "common/")
        return [path for path in tree if path.lower().startswith(prefixes) and path.lower().endswith(PHP_EXTENSIONS)][:100]

    def _module_candidates(self, tree: list[str], tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
        folders = sorted(
            {
                PurePosixPath(path).parts[0]
                for path in tree
                if len(PurePosixPath(path).parts) > 1
                and not PurePosixPath(path).parts[0].startswith(".")
            }
        )
        table_names = [table.get("table_name") for table in tables if table.get("table_name")]
        candidates = [{"name": folder, "source": "folder"} for folder in folders[:60]]
        candidates.extend({"name": table_name, "source": "database_table"} for table_name in table_names[:60])
        return candidates

    def _routing_hints(self, tree: list[str]) -> list[dict[str, str]]:
        hints = []
        for path in tree:
            lower_path = path.lower()
            if lower_path.endswith(".php") and self._looks_like_entrypoint(path):
                route = "/" + path.removesuffix(".php").replace("\\", "/")
                if route.endswith("/index"):
                    route = route[: -len("/index")] or "/"
                hints.append({"path": path, "route_hint": route})
        return hints[:100]

    def _content_hints(self, selected_files: list[dict[str, Any]], needles: list[str]) -> list[dict[str, str]]:
        hints = []
        lowered_needles = [needle.lower() for needle in needles]
        for file_data in selected_files:
            content = file_data.get("content", "") or ""
            content_lower = content.lower()
            matched = [needle for needle, lowered in zip(needles, lowered_needles) if lowered in content_lower]
            if matched:
                hints.append({"path": file_data.get("path", ""), "matched": ", ".join(matched)})
        return hints

    def _migration_risks(
        self,
        tree: list[str],
        selected_files: list[dict[str, Any]],
        database_context: dict[str, Any],
    ) -> list[str]:
        risks = []
        if self._content_hints(selected_files, ["$_SESSION", "session_start"]):
            risks.append("Session-based auth/state must be redesigned or bridged for React/API usage.")
        if self._content_hints(selected_files, ["$_FILES", "move_uploaded_file"]):
            risks.append("File upload workflows need explicit API and storage contracts.")
        if self._content_hints(selected_files, ["SELECT ", "INSERT ", "UPDATE ", "DELETE "]):
            risks.append("Inline SQL usage must be mapped to API endpoints and database models.")
        if database_context.get("ok") is False:
            risks.append("Database schema context is unavailable, reducing migration accuracy.")
        if any(path.lower().endswith(".php") for path in tree) and not any("composer.json" in path for path in tree):
            risks.append("Legacy PHP dependency boundaries may be implicit because composer.json was not found.")
        return risks

    def _get_database_context(self, include_database_schema: bool) -> dict[str, Any]:
        if not include_database_schema:
            return {"enabled": False, "tables": []}

        schema = self.database_schema_tool.get_database_schema(include_columns=False, max_tables=MAX_DATABASE_TABLES)
        if not schema.get("ok"):
            return {"enabled": True, "ok": False, "error": schema.get("error"), "tables": []}

        return {
            "enabled": True,
            "ok": True,
            "schema_name": schema.get("schema_name"),
            "table_count": schema.get("table_count"),
            "tables": schema.get("tables", []),
            "truncated": schema.get("truncated", False),
        }

    def _get_azure_context(self, work_item_id: int | None) -> dict[str, Any]:
        if not work_item_id:
            return {"enabled": False}
        try:
            return {"enabled": True, "ok": True, "work_item": self.azure.get_work_item(work_item_id)}
        except Exception as exc:
            logger.warning("Failed to fetch Azure work item %s: %s", work_item_id, exc)
            return {"enabled": True, "ok": False, "work_item_id": work_item_id, "error": str(exc)}

    def _expected_agent_output(self) -> dict[str, Any]:
        return {
            "current_architecture_summary": "Evidence-based summary of the current PHP architecture.",
            "domain_modules": ["Domain/module inventory with source evidence."],
            "migration_boundaries": ["Recommended boundaries for incremental PHP-to-React migration."],
            "target_react_architecture": {
                "routing": "Target routing structure.",
                "state_management": "State and data-fetching approach.",
                "api_boundary": "Backend/API boundary needed by React.",
                "shared_components": "Reusable UI/component candidates.",
            },
            "recommended_migration_order": ["Smallest safe modules first, with dependencies noted."],
            "risks": ["Architecture and migration risks grounded in evidence."],
            "open_questions": ["Questions that need product or engineering confirmation."],
        }
