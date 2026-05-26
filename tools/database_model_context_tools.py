"""
Database Model Context Agent Tools
Build read-only database model context for migration planning.
"""

from __future__ import annotations

import logging
from typing import Any

from tools.database_schema_tools import DatabaseSchemaTool

logger = logging.getLogger(__name__)

MAX_MODEL_TABLES = 40


class DatabaseModelContextTool:
    """Build bounded model context from MySQL schema metadata."""

    def __init__(self, database_schema_tool: DatabaseSchemaTool | None = None) -> None:
        self.database_schema_tool = database_schema_tool or DatabaseSchemaTool()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "build_database_model_context",
                "description": "Build read-only database model context for migration planning",
            }
        ]

    def build_database_model_context(
        self,
        schema_name: str | None = None,
        table_names: list[str] | None = None,
        focus_terms: list[str] | None = None,
        include_relationships: bool = True,
        max_tables: int = MAX_MODEL_TABLES,
    ) -> dict[str, Any]:
        selected_table_names_result = self._select_table_names(
            schema_name=schema_name,
            table_names=table_names or [],
            focus_terms=focus_terms or [],
            max_tables=max_tables,
        )
        if not selected_table_names_result.get("ok"):
            return {
                "ok": False,
                "agent": "database_model_context_agent",
                "schema_name": schema_name,
                "table_names": table_names or [],
                "focus_terms": focus_terms or [],
                "error": selected_table_names_result.get("error"),
                "model_context": self._empty_model_context(),
            }

        resolved_schema = selected_table_names_result.get("schema_name")
        selected_table_names = selected_table_names_result["table_names"]
        table_contexts = []
        errors = []

        for table_name in selected_table_names:
            description = self.database_schema_tool.describe_database_table(table_name, schema_name=resolved_schema)
            if not description.get("ok"):
                errors.append({"table_name": table_name, "error": description.get("error")})
                continue
            table_contexts.append(self._table_context(description))
        resolved_schema = resolved_schema or self._first_schema_name(table_contexts)

        model_context = {
            "table_count": len(table_contexts),
            "tables": table_contexts,
            "relationships": self._relationships(table_contexts) if include_relationships else [],
            "model_candidates": self._model_candidates(table_contexts),
            "data_contracts": self._data_contracts(table_contexts),
            "migration_risks": self._migration_risks(table_contexts, errors),
        }

        return {
            "ok": not errors,
            "agent": "database_model_context_agent",
            "schema_name": resolved_schema,
            "table_names": table_names or [],
            "focus_terms": focus_terms or [],
            "selected_table_names": selected_table_names,
            "include_relationships": include_relationships,
            "model_context": model_context,
            "table_errors": errors,
            "expected_agent_output": self._expected_agent_output(),
        }

    def _select_table_names(
        self,
        schema_name: str | None,
        table_names: list[str],
        focus_terms: list[str],
        max_tables: int,
    ) -> dict[str, Any]:
        max_tables = max(1, min(max_tables, MAX_MODEL_TABLES))
        if table_names:
            return {"ok": True, "schema_name": schema_name, "table_names": list(dict.fromkeys(table_names))[:max_tables]}

        tables_result = self.database_schema_tool.list_database_tables(schema_name=schema_name)
        if not tables_result.get("ok"):
            return tables_result

        terms = [term.lower() for term in focus_terms if term]
        tables = tables_result.get("tables", [])
        if terms:
            tables = [
                table
                for table in tables
                if any(term in table.get("table_name", "").lower() for term in terms)
            ]

        return {
            "ok": True,
            "schema_name": tables_result.get("schema_name"),
            "table_names": [table["table_name"] for table in tables if table.get("table_name")][:max_tables],
        }

    def _table_context(self, description: dict[str, Any]) -> dict[str, Any]:
        columns = description.get("columns", [])
        indexes = description.get("indexes", [])
        foreign_keys = description.get("foreign_keys", [])
        return {
            "schema_name": description.get("schema_name"),
            "table_name": description.get("table_name"),
            "columns": columns,
            "primary_keys": [column["column_name"] for column in columns if column.get("column_key") == "PRI"],
            "required_columns": [column["column_name"] for column in columns if column.get("is_nullable") == "NO"],
            "nullable_columns": [column["column_name"] for column in columns if column.get("is_nullable") == "YES"],
            "enum_columns": [self._enum_column(column) for column in columns if column.get("column_type", "").startswith("enum(")],
            "timestamp_columns": [
                column["column_name"]
                for column in columns
                if any(token in column.get("column_type", "").lower() for token in ("date", "time", "timestamp"))
            ],
            "indexes": indexes,
            "unique_indexes": [index for index in indexes if index.get("non_unique") == 0],
            "foreign_keys": foreign_keys,
            "relationship_hints": self._relationship_hints(description.get("table_name"), columns, foreign_keys),
        }

    def _enum_column(self, column: dict[str, Any]) -> dict[str, Any]:
        raw_type = column.get("column_type", "")
        values = []
        if raw_type.startswith("enum(") and raw_type.endswith(")"):
            values = [value.strip().strip("'") for value in raw_type[5:-1].split(",")]
        return {"column_name": column.get("column_name"), "values": values}

    def _relationship_hints(
        self,
        table_name: str | None,
        columns: list[dict[str, Any]],
        foreign_keys: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        hints = [
            {
                "type": "foreign_key",
                "column_name": fk.get("column_name"),
                "referenced_table_name": fk.get("referenced_table_name"),
                "referenced_column_name": fk.get("referenced_column_name"),
            }
            for fk in foreign_keys
        ]
        for column in columns:
            column_name = column.get("column_name", "")
            if column_name.endswith("_id") and not any(hint["column_name"] == column_name for hint in hints):
                hints.append(
                    {
                        "type": "naming_convention",
                        "column_name": column_name,
                        "referenced_table_name": column_name.removesuffix("_id"),
                        "referenced_column_name": "id",
                        "confidence": "medium",
                    }
                )
        if table_name and table_name.endswith("_items"):
            hints.append({"type": "line_item_table", "table_name": table_name, "confidence": "medium"})
        return hints

    def _relationships(self, table_contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        relationships = []
        known_tables = {table["table_name"] for table in table_contexts}
        for table in table_contexts:
            for hint in table.get("relationship_hints", []):
                referenced_table = hint.get("referenced_table_name")
                if hint.get("type") in {"foreign_key", "naming_convention"}:
                    relationships.append(
                        {
                            "from_table": table["table_name"],
                            "from_column": hint.get("column_name"),
                            "to_table": referenced_table,
                            "to_column": hint.get("referenced_column_name"),
                            "type": hint.get("type"),
                            "referenced_table_selected": referenced_table in known_tables,
                        }
                    )
        return relationships

    def _model_candidates(self, table_contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = []
        for table in table_contexts:
            candidates.append(
                {
                    "table_name": table["table_name"],
                    "model_name": self._model_name(table["table_name"]),
                    "primary_keys": table["primary_keys"],
                    "required_fields": table["required_columns"],
                    "enum_fields": table["enum_columns"],
                    "relationships": table["relationship_hints"],
                }
            )
        return candidates

    def _data_contracts(self, table_contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contracts = []
        for table in table_contexts:
            writable_columns = [
                column["column_name"]
                for column in table["columns"]
                if "auto_increment" not in column.get("extra", "").lower()
            ]
            contracts.append(
                {
                    "table_name": table["table_name"],
                    "read_fields": [column["column_name"] for column in table["columns"]],
                    "create_fields": writable_columns,
                    "update_fields": writable_columns,
                    "required_create_fields": [
                        column
                        for column in table["required_columns"]
                        if column in writable_columns
                    ],
                }
            )
        return contracts

    def _migration_risks(self, table_contexts: list[dict[str, Any]], errors: list[dict[str, Any]]) -> list[str]:
        risks = []
        if errors:
            risks.append("Some requested tables could not be described.")
        if any(not table["primary_keys"] for table in table_contexts):
            risks.append("Some tables do not expose a primary key in schema metadata.")
        if any(hint.get("type") == "naming_convention" for table in table_contexts for hint in table["relationship_hints"]):
            risks.append("Some relationships are inferred from *_id naming and should be verified.")
        if any(table["enum_columns"] for table in table_contexts):
            risks.append("Enum columns need explicit API validation and frontend option mapping.")
        return risks

    def _model_name(self, table_name: str) -> str:
        return "".join(part.capitalize() for part in table_name.split("_") if part)

    def _first_schema_name(self, table_contexts: list[dict[str, Any]]) -> str | None:
        return next((table.get("schema_name") for table in table_contexts if table.get("schema_name")), None)

    def _empty_model_context(self) -> dict[str, Any]:
        return {
            "table_count": 0,
            "tables": [],
            "relationships": [],
            "model_candidates": [],
            "data_contracts": [],
            "migration_risks": [],
        }

    def _expected_agent_output(self) -> dict[str, Any]:
        return {
            "domain_model_summary": "Plain-language summary of selected tables and ownership.",
            "model_candidates": ["Backend model/entity candidates with primary keys and required fields."],
            "relationships": ["Confirmed and inferred relationships with confidence."],
            "api_data_contracts": ["Read/create/update field contracts for Migration Spec Agent."],
            "frontend_mapping_notes": ["Enums, required fields, timestamps, and option lists for React forms."],
            "risks": ["Schema risks and relationships requiring verification."],
        }
