"""
React Conversion Agent Tools
Build React implementation blueprints from migration specs.
"""

from __future__ import annotations

from typing import Any

from tools.migration_spec_tools import MigrationSpecTool


class ReactConversionTool:
    """Plan React conversion work for one PHP-to-React migration slice."""

    def __init__(self, migration_spec_tool: MigrationSpecTool | None = None) -> None:
        self.migration_spec_tool = migration_spec_tool or MigrationSpecTool()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "build_react_conversion_plan",
                "description": "Build a React implementation blueprint from a migration spec",
            }
        ]

    def build_react_conversion_plan(
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
        react_app_root: str = "frontend/src",
        include_database_schema: bool = True,
    ) -> dict[str, Any]:
        migration_result = self.migration_spec_tool.build_migration_spec(
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
        migration_spec = migration_result.get("migration_spec", {})
        conversion_plan = self._conversion_plan(module_name, react_app_root, migration_spec)

        return {
            "ok": bool(migration_result.get("ok")),
            "agent": "react_conversion_agent",
            "repo_name": repo_name,
            "target_ref": target_ref,
            "module_name": module_name,
            "module_path": module_path,
            "related_paths": related_paths or [],
            "focus_terms": focus_terms or [],
            "table_names": table_names or [],
            "schema_name": migration_result.get("schema_name") or schema_name,
            "work_item_id": work_item_id,
            "react_app_root": react_app_root,
            "react_conversion_plan": conversion_plan,
            "migration_spec_context": migration_result,
            "expected_agent_output": self._expected_agent_output(),
        }

    def _conversion_plan(
        self,
        module_name: str,
        react_app_root: str,
        migration_spec: dict[str, Any],
    ) -> dict[str, Any]:
        react_spec = migration_spec.get("react_spec", {})
        backend_api_spec = migration_spec.get("backend_api_spec", [])
        database_model_spec = migration_spec.get("database_model_spec", {})
        feature_slug = self._slug(module_name)
        feature_dir = f"{react_app_root.rstrip('/')}/features/{feature_slug}"
        screen_candidates = react_spec.get("screen_candidates", [])
        component_files = self._component_files(feature_dir, screen_candidates)

        return {
            "feature_slug": feature_slug,
            "feature_dir": feature_dir,
            "route_plan": {
                "route_base": react_spec.get("route_base") or f"/{feature_slug}",
                "route_file": f"{feature_dir}/routes.tsx",
                "screen_routes": [
                    {
                        "path": self._screen_route(react_spec.get("route_base") or f"/{feature_slug}", item),
                        "component_name": item.get("component_name"),
                        "source_path": item.get("source_path"),
                    }
                    for item in screen_candidates
                ],
            },
            "file_plan": {
                "components": component_files,
                "hooks": self._hook_files(feature_dir, backend_api_spec),
                "api_client": f"{feature_dir}/api/{self._camel(feature_slug)}Api.ts",
                "types": f"{feature_dir}/types.ts",
                "index": f"{feature_dir}/index.ts",
                "tests": self._test_files(feature_dir, screen_candidates),
            },
            "component_plan": self._component_plan(screen_candidates, react_spec),
            "data_fetching_plan": self._data_fetching_plan(backend_api_spec),
            "form_plan": self._form_plan(database_model_spec.get("data_contracts", [])),
            "state_plan": react_spec.get("state_notes", []),
            "implementation_steps": self._implementation_steps(module_name, component_files, backend_api_spec),
            "test_plan": self._test_plan(screen_candidates, backend_api_spec),
            "risks": migration_spec.get("risks", []),
            "open_questions": migration_spec.get("open_questions", []),
        }

    def _component_files(self, feature_dir: str, screen_candidates: list[dict[str, Any]]) -> list[dict[str, str | None]]:
        return [
            {
                "component_name": item.get("component_name"),
                "path": f"{feature_dir}/components/{item.get('component_name')}.tsx",
                "source_path": item.get("source_path"),
                "role_hint": item.get("role_hint"),
            }
            for item in screen_candidates
            if item.get("component_name")
        ]

    def _hook_files(self, feature_dir: str, backend_api_spec: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hooks = []
        for api_spec in backend_api_spec:
            route = api_spec.get("route", "")
            hook_name = f"use{self._pascal(route.rsplit('/', 1)[-1] or 'Data')}"
            hooks.append(
                {
                    "hook_name": hook_name,
                    "path": f"{feature_dir}/hooks/{hook_name}.ts",
                    "api_route": route,
                    "methods": api_spec.get("methods", []),
                }
            )
        return hooks

    def _test_files(self, feature_dir: str, screen_candidates: list[dict[str, Any]]) -> list[str]:
        return [
            f"{feature_dir}/__tests__/{item.get('component_name')}.test.tsx"
            for item in screen_candidates
            if item.get("component_name")
        ]

    def _component_plan(
        self,
        screen_candidates: list[dict[str, Any]],
        react_spec: dict[str, Any],
    ) -> list[dict[str, Any]]:
        api_dependencies = react_spec.get("api_dependencies", [])
        return [
            {
                "component_name": item.get("component_name"),
                "legacy_source_path": item.get("source_path"),
                "responsibility": self._responsibility(item.get("role_hint")),
                "api_dependencies": api_dependencies,
                "state_notes": react_spec.get("state_notes", []),
            }
            for item in screen_candidates
        ]

    def _data_fetching_plan(self, backend_api_spec: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "route": item.get("route"),
                "methods": item.get("methods", []),
                "tables": item.get("tables", []),
                "client_function": self._client_function(item.get("route", ""), item.get("methods", [])),
                "notes": item.get("notes", []),
            }
            for item in backend_api_spec
        ]

    def _form_plan(self, data_contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "table_name": contract.get("table_name"),
                "create_fields": contract.get("create_fields", []),
                "update_fields": contract.get("update_fields", []),
                "required_fields": contract.get("required_create_fields", []),
                "validation_notes": [
                    f"{field} is required"
                    for field in contract.get("required_create_fields", [])
                ],
            }
            for contract in data_contracts
        ]

    def _implementation_steps(
        self,
        module_name: str,
        component_files: list[dict[str, str | None]],
        backend_api_spec: list[dict[str, Any]],
    ) -> list[str]:
        steps = [
            f"Create the {module_name} feature folder and route registration.",
            "Add shared TypeScript types for API payloads and UI state.",
        ]
        if backend_api_spec:
            steps.append("Implement API client functions and data-fetching hooks for each backend route.")
        if component_files:
            steps.append("Build screen components from the legacy source file responsibilities.")
        steps.extend(
            [
                "Wire forms, loading states, error states, and navigation behavior.",
                "Add component and hook tests using the migration spec acceptance criteria.",
            ]
        )
        return steps

    def _test_plan(
        self,
        screen_candidates: list[dict[str, Any]],
        backend_api_spec: list[dict[str, Any]],
    ) -> list[str]:
        tests = [
            "Render each migrated screen with mocked API data.",
            "Verify loading, empty, error, and success states.",
        ]
        if backend_api_spec:
            tests.append("Verify API client methods call the expected backend routes and methods.")
        if any("upload" in (item.get("source_path") or "").lower() for item in screen_candidates):
            tests.append("Verify upload form validation and submission states.")
        return tests

    def _screen_route(self, route_base: str, item: dict[str, Any]) -> str:
        source_path = item.get("source_path") or ""
        stem = source_path.rsplit("/", 1)[-1].removesuffix(".php")
        if not stem or stem.lower() in {"index", "list"}:
            return route_base
        return f"{route_base}/{self._slug(stem)}"

    def _responsibility(self, role_hint: str | None) -> str:
        return {
            "read_view": "Render a read/list/detail screen backed by API data.",
            "mutation_or_workflow": "Render a workflow form/action screen with mutation handling.",
            "legacy_entrypoint": "Render migrated legacy page behavior behind a React route.",
        }.get(role_hint or "", "Support the migrated feature UI.")

    def _client_function(self, route: str, methods: list[str]) -> str:
        prefix = "fetch"
        if "POST" in methods or "PUT" in methods or "PATCH" in methods:
            prefix = "submit"
        return f"{prefix}{self._pascal(route.rsplit('/', 1)[-1] or 'Data')}"

    def _slug(self, value: str) -> str:
        normalized = value.replace("_", "-").replace("/", "-").replace(" ", "-").lower()
        return "-".join(part for part in normalized.split("-") if part)

    def _camel(self, value: str) -> str:
        pascal = self._pascal(value)
        return pascal[:1].lower() + pascal[1:] if pascal else "feature"

    def _pascal(self, value: str) -> str:
        cleaned = value.replace("_", "-").replace(" ", "-")
        return "".join(part[:1].upper() + part[1:] for part in cleaned.split("-") if part)

    def _expected_agent_output(self) -> dict[str, Any]:
        return {
            "conversion_summary": "What React feature should be created and why.",
            "file_plan": ["React files to create or update."],
            "component_plan": ["Screens/components with responsibilities and data dependencies."],
            "api_and_hook_plan": ["API client functions, hooks, and backend dependencies."],
            "form_and_state_plan": ["Form fields, validation, route params, and state handling."],
            "test_plan": ["Component, hook, and behavior parity tests."],
            "implementation_order": ["Recommended file-by-file implementation order."],
        }
