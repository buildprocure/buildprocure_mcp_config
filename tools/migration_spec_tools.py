"""
Migration Spec Agent Tools
Compose migration-ready specs from architecture, legacy PHP, and database context.
"""

from __future__ import annotations

from typing import Any

from tools.architecture_agent_tools import ArchitectureAgentTool
from tools.database_model_context_tools import DatabaseModelContextTool
from tools.legacy_php_analysis_tools import LegacyPHPAnalysisTool


class MigrationSpecTool:
    """Build a structured migration specification for one module slice."""

    def __init__(
        self,
        architecture_agent_tool: ArchitectureAgentTool | None = None,
        legacy_php_analysis_tool: LegacyPHPAnalysisTool | None = None,
        database_model_context_tool: DatabaseModelContextTool | None = None,
    ) -> None:
        self.architecture_agent_tool = architecture_agent_tool or ArchitectureAgentTool()
        self.legacy_php_analysis_tool = legacy_php_analysis_tool or LegacyPHPAnalysisTool()
        self.database_model_context_tool = database_model_context_tool or DatabaseModelContextTool()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "build_migration_spec",
                "description": "Build a structured PHP-to-React migration spec for one module slice",
            }
        ]

    def build_migration_spec(
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
        include_database_schema: bool = True,
    ) -> dict[str, Any]:
        focus_terms = focus_terms or []
        related_paths = related_paths or []
        table_names = table_names or []

        architecture_context = self.architecture_agent_tool.build_architecture_analysis(
            repo_name=repo_name,
            target_ref=target_ref,
            module_path=module_path,
            work_item_id=work_item_id,
            include_database_schema=include_database_schema,
        )
        legacy_context = self.legacy_php_analysis_tool.analyze_legacy_php_module(
            repo_name=repo_name,
            target_ref=target_ref,
            module_path=module_path,
            related_paths=related_paths,
            focus_terms=focus_terms,
            include_database_schema=include_database_schema,
        )
        database_context = self.database_model_context_tool.build_database_model_context(
            schema_name=schema_name,
            table_names=table_names,
            focus_terms=focus_terms if not table_names else [],
            include_relationships=True,
        )

        spec = self._build_spec(
            module_name=module_name,
            module_path=module_path,
            focus_terms=focus_terms,
            architecture_context=architecture_context,
            legacy_context=legacy_context,
            database_context=database_context,
        )

        return {
            "ok": bool(
                architecture_context.get("ok")
                and legacy_context.get("ok")
                and database_context.get("ok")
            ),
            "agent": "migration_spec_agent",
            "repo_name": repo_name,
            "target_ref": target_ref,
            "module_name": module_name,
            "module_path": module_path,
            "related_paths": related_paths,
            "focus_terms": focus_terms,
            "table_names": table_names,
            "schema_name": database_context.get("schema_name") or schema_name,
            "work_item_id": work_item_id,
            "migration_spec": spec,
            "source_context": {
                "architecture_context": architecture_context,
                "legacy_php_context": legacy_context,
                "database_model_context": database_context,
            },
            "expected_agent_output": self._expected_agent_output(),
        }

    def _build_spec(
        self,
        module_name: str,
        module_path: str | None,
        focus_terms: list[str],
        architecture_context: dict[str, Any],
        legacy_context: dict[str, Any],
        database_context: dict[str, Any],
    ) -> dict[str, Any]:
        legacy_analysis = legacy_context.get("legacy_analysis", {})
        model_context = database_context.get("model_context", {})
        files = legacy_analysis.get("files", [])
        api_candidates = legacy_analysis.get("api_candidates", [])
        data_contracts = model_context.get("data_contracts", [])

        return {
            "scope": {
                "module_name": module_name,
                "module_path": module_path,
                "focus_terms": focus_terms,
                "source_file_count": legacy_analysis.get("file_count", 0),
                "table_count": model_context.get("table_count", 0),
            },
            "source_files": [
                {
                    "path": item.get("path"),
                    "role_hint": item.get("role_hint"),
                    "referenced_tables": item.get("referenced_tables", []),
                    "session_keys": item.get("session_keys", []),
                    "request_params": item.get("request_params", []),
                    "upload_fields": item.get("upload_fields", []),
                    "redirects": item.get("redirects", []),
                }
                for item in files
            ],
            "backend_api_spec": self._backend_api_spec(api_candidates, data_contracts),
            "database_model_spec": {
                "model_candidates": model_context.get("model_candidates", []),
                "relationships": model_context.get("relationships", []),
                "data_contracts": data_contracts,
            },
            "react_spec": self._react_spec(module_name, files, api_candidates, model_context),
            "migration_steps": self._migration_steps(module_name, api_candidates, data_contracts),
            "acceptance_criteria": self._acceptance_criteria(module_name, files, api_candidates),
            "risks": self._risks(architecture_context, legacy_context, database_context),
            "open_questions": self._open_questions(legacy_analysis, model_context),
        }

    def _backend_api_spec(
        self,
        api_candidates: list[dict[str, Any]],
        data_contracts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        contracts_by_table = {contract.get("table_name"): contract for contract in data_contracts}
        specs = []
        for candidate in api_candidates:
            specs.append(
                {
                    "source_path": candidate.get("source_path"),
                    "route": candidate.get("suggested_route"),
                    "methods": candidate.get("http_methods", []),
                    "tables": candidate.get("tables", []),
                    "contracts": [
                        contracts_by_table[table_name]
                        for table_name in candidate.get("tables", [])
                        if table_name in contracts_by_table
                    ],
                    "notes": candidate.get("notes", []),
                }
            )
        return specs

    def _react_spec(
        self,
        module_name: str,
        files: list[dict[str, Any]],
        api_candidates: list[dict[str, Any]],
        model_context: dict[str, Any],
    ) -> dict[str, Any]:
        route_base = "/" + module_name.strip().lower().replace(" ", "-").replace("_", "-")
        return {
            "route_base": route_base,
            "screen_candidates": [
                {
                    "source_path": item.get("path"),
                    "component_name": self._component_name(item.get("path", ""), module_name),
                    "role_hint": item.get("role_hint"),
                }
                for item in files
                if item.get("role_hint") in {"read_view", "mutation_or_workflow", "legacy_entrypoint"}
            ],
            "api_dependencies": [candidate.get("suggested_route") for candidate in api_candidates],
            "form_contracts": model_context.get("data_contracts", []),
            "state_notes": self._state_notes(files),
        }

    def _migration_steps(
        self,
        module_name: str,
        api_candidates: list[dict[str, Any]],
        data_contracts: list[dict[str, Any]],
    ) -> list[str]:
        steps = [
            f"Confirm {module_name} legacy behavior and table ownership with product/engineering.",
            "Create backend API endpoints for the selected legacy workflows.",
        ]
        if data_contracts:
            steps.append("Implement backend model/data contracts for selected tables.")
        if api_candidates:
            steps.append("Build React routes and screens against the new API contracts.")
        steps.extend(
            [
                "Run behavior parity checks against legacy PHP flows.",
                "Open a migration PR and run the migration-aware PR review flow.",
            ]
        )
        return steps

    def _acceptance_criteria(
        self,
        module_name: str,
        files: list[dict[str, Any]],
        api_candidates: list[dict[str, Any]],
    ) -> list[str]:
        criteria = [
            f"{module_name} React route renders the migrated workflows without relying on PHP page rendering.",
            "Backend APIs preserve required legacy request, session, and data behavior.",
            "Create/update/read flows validate required fields and handle backend errors.",
        ]
        if any(item.get("upload_fields") for item in files):
            criteria.append("File upload behavior is preserved with explicit API/storage handling.")
        if api_candidates:
            criteria.append("All API candidates in the spec have implementation or deferral notes.")
        return criteria

    def _risks(
        self,
        architecture_context: dict[str, Any],
        legacy_context: dict[str, Any],
        database_context: dict[str, Any],
    ) -> list[str]:
        risks = []
        risks.extend(architecture_context.get("architecture_context", {}).get("migration_risks", []))
        risks.extend(legacy_context.get("legacy_analysis", {}).get("migration_risks", []))
        risks.extend(database_context.get("model_context", {}).get("migration_risks", []))
        if not architecture_context.get("ok"):
            risks.append("Architecture context collection did not fully succeed.")
        if not legacy_context.get("ok"):
            risks.append("Legacy PHP analysis did not fully succeed.")
        if not database_context.get("ok"):
            risks.append("Database model context did not fully succeed.")
        return list(dict.fromkeys(risks))

    def _open_questions(
        self,
        legacy_analysis: dict[str, Any],
        model_context: dict[str, Any],
    ) -> list[str]:
        questions = []
        if legacy_analysis.get("session_keys"):
            questions.append("Which session keys should become API auth claims versus request parameters?")
        if any(file_data.get("upload_fields") for file_data in legacy_analysis.get("files", [])):
            questions.append("Where should uploaded files be stored and how should React display upload status?")
        if any(table.get("relationship_hints") for table in model_context.get("tables", [])):
            questions.append("Which inferred database relationships should be confirmed before implementation?")
        return questions

    def _state_notes(self, files: list[dict[str, Any]]) -> list[str]:
        notes = []
        if any(item.get("session_keys") for item in files):
            notes.append("Replace direct PHP session access with API-backed auth/user context.")
        if any(item.get("request_params") for item in files):
            notes.append("Map legacy request parameters to route params, query params, or form state.")
        if any(item.get("redirects") for item in files):
            notes.append("Map legacy redirects to React navigation states.")
        return notes

    def _component_name(self, path: str, module_name: str) -> str:
        stem = path.rsplit("/", 1)[-1].removesuffix(".php")
        words = [
            word
            for part in [module_name, stem]
            for word in part.replace("-", "_").replace(" ", "_").split("_")
            if word
        ]
        return "".join(word[:1].upper() + word[1:] for word in words) or "MigratedScreen"

    def _expected_agent_output(self) -> dict[str, Any]:
        return {
            "migration_summary": "One-page summary of the module migration scope.",
            "backend_api_spec": ["Endpoint contracts and backend model needs."],
            "react_spec": ["Routes, screens, components, state, forms, and API dependencies."],
            "acceptance_criteria": ["Behavioral checks required before completion."],
            "implementation_tasks": ["Ordered backend, frontend, test, and rollout tasks."],
            "risks_and_open_questions": ["Risks and decisions that need confirmation."],
        }
