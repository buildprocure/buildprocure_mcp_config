"""
Legacy PHP Analysis Agent Tools
Evidence gathering for one legacy PHP migration slice.
"""

from __future__ import annotations

import logging
import re
from pathlib import PurePosixPath
from typing import Any

from tools.database_schema_tools import DatabaseSchemaTool
from tools.repository_content_tools import RepositoryContentTool
from utils.github_helpers import GitHubHelper

logger = logging.getLogger(__name__)

MAX_LEGACY_FILES = 50
MAX_DATABASE_TABLES = 150
PHP_EXTENSIONS = (".php", ".inc")
INCLUDE_RE = re.compile(r"\b(?:require|require_once|include|include_once)\s*\(?\s*['\"]([^'\"]+)['\"]", re.I)
FORM_RE = re.compile(r"<form\b[^>]*>", re.I)
ACTION_RE = re.compile(r"\baction\s*=\s*['\"]([^'\"]*)['\"]", re.I)
METHOD_RE = re.compile(r"\bmethod\s*=\s*['\"]([^'\"]*)['\"]", re.I)
SESSION_RE = re.compile(r"\$_SESSION\s*\[\s*['\"]([^'\"]+)['\"]\s*\]")
REQUEST_RE = re.compile(r"\$_(?:GET|POST|REQUEST)\s*\[\s*['\"]([^'\"]+)['\"]\s*\]")
UPLOAD_RE = re.compile(r"\$_FILES\s*\[\s*['\"]([^'\"]+)['\"]\s*\]")
REDIRECT_RE = re.compile(r"header\s*\(\s*['\"]Location:\s*([^'\"]+)['\"]", re.I)
SQL_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b[\s\S]{0,500}", re.I)


class LegacyPHPAnalysisTool:
    """Analyze one legacy PHP module before migration specification work."""

    def __init__(
        self,
        github: GitHubHelper | None = None,
        content_tool: RepositoryContentTool | None = None,
        database_schema_tool: DatabaseSchemaTool | None = None,
    ) -> None:
        self.github = github or GitHubHelper()
        self.content_tool = content_tool or RepositoryContentTool(github=self.github)
        self.database_schema_tool = database_schema_tool or DatabaseSchemaTool()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "analyze_legacy_php_module",
                "description": "Analyze a focused legacy PHP module before PHP-to-React migration",
            }
        ]

    def analyze_legacy_php_module(
        self,
        repo_name: str,
        target_ref: str = "main",
        module_path: str | None = None,
        related_paths: list[str] | None = None,
        focus_terms: list[str] | None = None,
        include_database_schema: bool = True,
    ) -> dict[str, Any]:
        tree_result = self.content_tool.get_repo_tree(repo_name, target_ref=target_ref)
        tree = tree_result.get("tree", [])
        selected_paths = self._select_module_files(tree, module_path, related_paths or [], focus_terms or [])
        files_result = self.content_tool.get_repo_files_batch(repo_name, selected_paths, target_ref=target_ref)
        selected_files = files_result.get("files", [])
        database_context = self._get_database_context(include_database_schema)
        analysis = self._build_analysis(selected_files, database_context.get("tables", []))

        return {
            "ok": bool(tree_result.get("ok") and files_result.get("ok", True)),
            "agent": "legacy_php_analysis_agent",
            "repo_name": repo_name,
            "target_ref": target_ref,
            "module_path": module_path,
            "related_paths": related_paths or [],
            "focus_terms": focus_terms or [],
            "selected_paths": selected_paths,
            "file_errors": files_result.get("errors", []),
            "legacy_analysis": analysis,
            "database_context": database_context,
            "expected_agent_output": self._expected_agent_output(),
            "errors": [item for item in [tree_result if not tree_result.get("ok") else None] if item],
        }

    def _select_module_files(
        self,
        tree: list[str],
        module_path: str | None,
        related_paths: list[str],
        focus_terms: list[str],
    ) -> list[str]:
        prefixes = [item.strip("/").lower() for item in [module_path, *related_paths] if item]
        terms = [term.lower() for term in focus_terms if term]
        selected = []

        for path in tree:
            lower_path = path.lower()
            if not lower_path.endswith(PHP_EXTENSIONS):
                continue
            path_matches_prefix = not prefixes or any(lower_path == prefix or lower_path.startswith(f"{prefix}/") for prefix in prefixes)
            path_matches_term = not terms or any(term in lower_path for term in terms)
            if path_matches_prefix and path_matches_term:
                selected.append(path)

        if not selected and prefixes:
            selected = [
                path
                for path in tree
                if path.lower().endswith(PHP_EXTENSIONS)
                and any(path.lower() == prefix or path.lower().startswith(f"{prefix}/") for prefix in prefixes)
            ]

        return list(dict.fromkeys(selected))[:MAX_LEGACY_FILES]

    def _build_analysis(
        self,
        selected_files: list[dict[str, Any]],
        database_tables: list[dict[str, Any]],
    ) -> dict[str, Any]:
        file_summaries = [self._analyze_file(file_data, database_tables) for file_data in selected_files]
        all_tables = sorted({table for item in file_summaries for table in item["referenced_tables"]})
        all_session_keys = sorted({key for item in file_summaries for key in item["session_keys"]})
        all_request_params = sorted({param for item in file_summaries for param in item["request_params"]})
        return {
            "file_count": len(file_summaries),
            "files": file_summaries,
            "referenced_tables": all_tables,
            "session_keys": all_session_keys,
            "request_params": all_request_params,
            "api_candidates": self._api_candidates(file_summaries),
            "migration_risks": self._migration_risks(file_summaries),
        }

    def _analyze_file(
        self,
        file_data: dict[str, Any],
        database_tables: list[dict[str, Any]],
    ) -> dict[str, Any]:
        content = file_data.get("content", "") or ""
        path = file_data.get("path", "")
        return {
            "path": path,
            "role_hint": self._role_hint(path),
            "includes": sorted(set(INCLUDE_RE.findall(content))),
            "forms": self._forms(content),
            "session_keys": sorted(set(SESSION_RE.findall(content))),
            "request_params": sorted(set(REQUEST_RE.findall(content))),
            "upload_fields": sorted(set(UPLOAD_RE.findall(content))),
            "redirects": sorted(set(REDIRECT_RE.findall(content))),
            "sql_operations": self._sql_operations(content),
            "referenced_tables": self._referenced_tables(content, database_tables),
            "uses_mysqli": "mysqli" in content.lower(),
            "uses_pdo": "pdo" in content.lower(),
            "content_truncated": bool(file_data.get("content_truncated")),
            "html_url": file_data.get("html_url"),
        }

    def _role_hint(self, path: str) -> str:
        name = PurePosixPath(path).name.lower()
        if any(token in name for token in ("list", "view", "details")):
            return "read_view"
        if any(token in name for token in ("create", "edit", "update", "save", "upload", "delete", "lock")):
            return "mutation_or_workflow"
        if any(token in name for token in ("function", "controller", "model")):
            return "supporting_logic"
        return "legacy_entrypoint"

    def _forms(self, content: str) -> list[dict[str, str | None]]:
        forms = []
        for match in FORM_RE.finditer(content):
            tag = match.group(0)
            action_match = ACTION_RE.search(tag)
            method_match = METHOD_RE.search(tag)
            forms.append(
                {
                    "action": action_match.group(1) if action_match else None,
                    "method": method_match.group(1).upper() if method_match else "GET",
                }
            )
        return forms

    def _sql_operations(self, content: str) -> list[dict[str, str]]:
        operations = []
        for match in SQL_RE.finditer(content):
            snippet = " ".join(match.group(0).split())
            operations.append({"operation": match.group(1).upper(), "snippet": snippet[:240]})
        return operations[:20]

    def _referenced_tables(self, content: str, database_tables: list[dict[str, Any]]) -> list[str]:
        lowered = content.lower()
        found = []
        for table in database_tables:
            table_name = table.get("table_name")
            if table_name and re.search(rf"(?<![A-Za-z0-9_]){re.escape(table_name.lower())}(?![A-Za-z0-9_])", lowered):
                found.append(table_name)
        return sorted(set(found))

    def _api_candidates(self, file_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = []
        for item in file_summaries:
            methods = sorted({form["method"] for form in item["forms"] if form.get("method")})
            operations = sorted({operation["operation"] for operation in item["sql_operations"]})
            if methods or operations or item["upload_fields"]:
                candidates.append(
                    {
                        "source_path": item["path"],
                        "suggested_route": self._suggested_api_route(item["path"]),
                        "http_methods": self._suggested_http_methods(methods, operations, bool(item["upload_fields"])),
                        "tables": item["referenced_tables"],
                        "notes": self._api_notes(item),
                    }
                )
        return candidates

    def _suggested_api_route(self, path: str) -> str:
        route = "/" + path.removesuffix(".php").lower().replace("\\", "/")
        route = route.replace("_", "-")
        return f"/api/legacy{route}"

    def _suggested_http_methods(self, form_methods: list[str], sql_operations: list[str], has_upload: bool) -> list[str]:
        methods = set(form_methods)
        if {"INSERT", "UPDATE", "DELETE"} & set(sql_operations) or has_upload:
            methods.add("POST")
        if "SELECT" in sql_operations:
            methods.add("GET")
        return sorted(methods or {"GET"})

    def _api_notes(self, item: dict[str, Any]) -> list[str]:
        notes = []
        if item["session_keys"]:
            notes.append("Depends on PHP session state; define auth/session contract.")
        if item["upload_fields"]:
            notes.append("Handles file upload; define multipart/storage contract.")
        if item["redirects"]:
            notes.append("Uses redirects; convert to API response states for React.")
        return notes

    def _migration_risks(self, file_summaries: list[dict[str, Any]]) -> list[str]:
        risks = []
        if any(item["session_keys"] for item in file_summaries):
            risks.append("Session keys are read directly by legacy PHP files.")
        if any(item["upload_fields"] for item in file_summaries):
            risks.append("File upload behavior must be preserved with explicit API/storage handling.")
        if any(item["sql_operations"] for item in file_summaries):
            risks.append("Inline SQL needs API/model extraction before React conversion.")
        if any(item["redirects"] for item in file_summaries):
            risks.append("Legacy redirects need React route or API response equivalents.")
        if any(item["content_truncated"] for item in file_summaries):
            risks.append("Some files were truncated, so manual inspection may still be needed.")
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

    def _expected_agent_output(self) -> dict[str, Any]:
        return {
            "legacy_behavior_summary": "What the PHP slice currently does, grounded in files and SQL.",
            "source_file_map": ["Entrypoints and supporting files with roles."],
            "data_contract_candidates": ["Tables, request params, session keys, and upload fields."],
            "api_candidates": ["Suggested backend endpoints required before React conversion."],
            "migration_risks": ["Risks that must be addressed before or during conversion."],
            "open_questions": ["Questions requiring product or engineering confirmation."],
        }
