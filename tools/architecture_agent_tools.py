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
            },
            {
                "name": "create_architecture_child_tickets",
                "description": "Suggest or create Azure Boards child tickets from architecture migration evidence",
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

    def create_architecture_child_tickets(
        self,
        parent_work_item_id: int,
        repo_name: str,
        migration_goal: str,
        target_ref: str = "main",
        module_name: str | None = None,
        module_path: str | None = None,
        work_item_type: str = "User Story",
        assigned_to: str | None = None,
        dry_run: bool = True,
        include_database_schema: bool = True,
    ) -> dict[str, Any]:
        """Suggest and optionally create child Azure Boards tickets for migration sequencing."""
        analysis = self.build_architecture_analysis(
            repo_name=repo_name,
            target_ref=target_ref,
            module_path=module_path,
            work_item_id=parent_work_item_id,
            include_database_schema=include_database_schema,
        )
        suggestions = self._suggest_child_tickets(
            migration_goal=migration_goal,
            module_name=module_name,
            module_path=module_path,
            architecture_context=analysis.get("architecture_context", {}),
        )

        created_tickets = []
        errors = []
        if not dry_run:
            parent = analysis.get("azure_context", {}).get("work_item", {})
            for suggestion in suggestions:
                try:
                    created_tickets.append(
                        self.azure.create_child_work_item(
                            parent_work_item_id=parent_work_item_id,
                            title=suggestion["title"],
                            description=suggestion["description"],
                            acceptance_criteria=suggestion["acceptance_criteria"],
                            work_item_type=work_item_type,
                            assigned_to=assigned_to,
                            tags=suggestion["tags"],
                            priority=parent.get("priority"),
                            area_path=parent.get("area_path"),
                            iteration_path=parent.get("iteration_path"),
                        )
                    )
                except Exception as exc:
                    logger.warning("Failed to create architecture child ticket: %s", exc)
                    errors.append({"title": suggestion["title"], "error": str(exc)})

        return {
            "ok": bool(analysis.get("ok") and (dry_run or not errors)),
            "agent": "architecture_agent",
            "parent_work_item_id": parent_work_item_id,
            "repo_name": repo_name,
            "target_ref": target_ref,
            "module_name": module_name,
            "module_path": module_path,
            "migration_goal": migration_goal,
            "dry_run": dry_run,
            "work_item_type": work_item_type,
            "assigned_to": assigned_to,
            "suggested_ticket_count": len(suggestions),
            "suggested_tickets": suggestions,
            "created_ticket_count": len(created_tickets),
            "created_tickets": created_tickets,
            "errors": errors,
            "architecture_summary": {
                "migration_risks": analysis.get("architecture_context", {}).get("migration_risks", []),
                "auth_session_hints_count": len(analysis.get("architecture_context", {}).get("auth_session_hints", [])),
                "sql_usage_hints_count": len(analysis.get("architecture_context", {}).get("sql_usage_hints", [])),
                "file_upload_hints_count": len(analysis.get("architecture_context", {}).get("file_upload_hints", [])),
            },
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

    def _suggest_child_tickets(
        self,
        migration_goal: str,
        module_name: str | None,
        module_path: str | None,
        architecture_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        label = module_name or module_path or migration_goal
        tickets = []
        risks = architecture_context.get("migration_risks", [])
        role_module = any(role in label.lower() for role in ("buyer", "supplier", "admin"))
        auth_needed = (
            role_module
            or bool(architecture_context.get("auth_session_hints"))
            or any("Session-based" in risk for risk in risks)
        )
        api_needed = bool(architecture_context.get("sql_usage_hints")) or bool(architecture_context.get("database_tables"))
        upload_needed = bool(architecture_context.get("file_upload_hints")) or any("upload" in risk.lower() for risk in risks)

        if auth_needed:
            tickets.append(
                self._ticket_suggestion(
                    title=f"Implement React auth/session bridge for {label}",
                    purpose="Remove the session/auth blocker before migrating protected React screens.",
                    affected=["login.php", "logout.php", "session_check.php", "app/Core/Auth.php", "_config.php"],
                    endpoints=["GET /api/auth/session", "POST /api/auth/login", "POST /api/auth/logout"],
                    acceptance=[
                        "React can check current logged-in user and role without rendering protected pages blindly.",
                        "Buyer role is available to migrated Buyer module screens through an auth context.",
                        "Existing PHP session behavior remains compatible during incremental migration.",
                    ],
                    tags=["architecture", "auth", "migration"],
                )
            )

        if api_needed:
            tickets.append(
                self._ticket_suggestion(
                    title=f"Implement backend API bridge for {label}",
                    purpose="Expose legacy PHP/database behavior through JSON endpoints consumed by React.",
                    affected=[module_path or "legacy PHP module", "api/legacy", "database model tables"],
                    endpoints=["GET/POST module-specific /api/legacy/... endpoints"],
                    acceptance=[
                        "React can load module data through JSON without scraping legacy PHP pages.",
                        "API responses use consistent ok/data/error shapes.",
                        "Protected endpoints enforce the migrated auth/session contract.",
                    ],
                    tags=["architecture", "api", "migration"],
                )
            )

        tickets.append(
            self._ticket_suggestion(
                title=f"Create migration spec for {label}",
                purpose="Lock scope, source files, routes, data contracts, and risks before code conversion.",
                affected=[module_path or "selected migration module"],
                endpoints=[],
                acceptance=[
                    "Spec lists source PHP files, React routes/components, API contracts, database tables, and risks.",
                    "Spec identifies what is in scope and what is explicitly deferred.",
                    "Spec can be consumed by React conversion and code writer agents.",
                ],
                tags=["architecture", "spec", "migration"],
            )
        )

        tickets.append(
            self._ticket_suggestion(
                title=f"Convert {label} UI to React",
                purpose="Generate and refine React components, hooks, and routes for the migration slice.",
                affected=["procurex-react/src"],
                endpoints=[],
                acceptance=[
                    "React screen renders the migrated workflow using the migration spec.",
                    "UI calls the backend API bridge and handles loading, empty, error, and unauthorized states.",
                    "Generated code stays local until tested.",
                ],
                tags=["architecture", "react", "migration"],
            )
        )

        if upload_needed:
            tickets.append(
                self._ticket_suggestion(
                    title=f"Define file upload contract for {label}",
                    purpose="Preserve legacy upload behavior through explicit multipart API and storage rules.",
                    affected=[module_path or "legacy PHP upload files", "storage/files"],
                    endpoints=["POST module-specific multipart upload endpoint"],
                    acceptance=[
                        "Allowed file types, size limits, storage path, and validation behavior are documented.",
                        "React upload flow receives structured success/error responses.",
                        "Legacy storage compatibility is preserved or migration differences are documented.",
                    ],
                    tags=["architecture", "upload", "migration"],
                )
            )

        return tickets

    def _ticket_suggestion(
        self,
        title: str,
        purpose: str,
        affected: list[str],
        endpoints: list[str],
        acceptance: list[str],
        tags: list[str],
    ) -> dict[str, Any]:
        description_lines = [
            f"Purpose: {purpose}",
            "",
            "Affected files/modules:",
            *[f"- {item}" for item in affected],
        ]
        if endpoints:
            description_lines.extend(["", "Expected API endpoints:", *[f"- {endpoint}" for endpoint in endpoints]])
        return {
            "title": title,
            "description": "\n".join(description_lines),
            "acceptance_criteria": "\n".join(f"- {item}" for item in acceptance),
            "tags": tags,
            "assigned_to": None,
            "recommended_owner": "Architecture Agent creates the ticket; implementation agents execute it.",
        }

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
