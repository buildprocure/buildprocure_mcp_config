from __future__ import annotations

from tools.database_model_context_tools import DatabaseModelContextTool


class FakeDatabaseSchemaTool:
    def list_database_tables(self, schema_name=None) -> dict:
        return {
            "ok": True,
            "schema_name": schema_name or "ilife",
            "tables": [
                {"table_name": "boqs"},
                {"table_name": "boq_items"},
                {"table_name": "purchase_orders"},
            ],
        }

    def describe_database_table(self, table_name: str, schema_name=None) -> dict:
        descriptions = {
            "boqs": {
                "columns": [
                    self._column("id", "int", "NO", "PRI", "auto_increment"),
                    self._column("project_id", "int", "NO"),
                    self._column("status", "enum('Draft','Locked')", "NO"),
                    self._column("created_at", "datetime", "NO"),
                ],
                "indexes": [
                    {"index_name": "PRIMARY", "non_unique": 0, "column_name": "id"},
                    {"index_name": "project_id", "non_unique": 1, "column_name": "project_id"},
                ],
                "foreign_keys": [],
            },
            "boq_items": {
                "columns": [
                    self._column("id", "int", "NO", "PRI", "auto_increment"),
                    self._column("boq_id", "int", "NO"),
                    self._column("item_id", "int", "NO"),
                    self._column("quantity", "decimal(10,2)", "NO"),
                ],
                "indexes": [{"index_name": "PRIMARY", "non_unique": 0, "column_name": "id"}],
                "foreign_keys": [
                    {
                        "constraint_name": "fk_boq_items_boq",
                        "column_name": "boq_id",
                        "referenced_table_name": "boqs",
                        "referenced_column_name": "id",
                    }
                ],
            },
        }
        if table_name not in descriptions:
            return {"ok": False, "error": f"missing {table_name}"}
        return {
            "ok": True,
            "schema_name": schema_name or "ilife",
            "table_name": table_name,
            **descriptions[table_name],
        }

    def _column(self, name: str, column_type: str, nullable: str, key: str = "", extra: str = "") -> dict:
        return {
            "column_name": name,
            "column_type": column_type,
            "is_nullable": nullable,
            "column_key": key,
            "extra": extra,
            "column_default": None,
            "column_comment": "",
            "ordinal_position": 1,
        }


def _tool() -> DatabaseModelContextTool:
    return DatabaseModelContextTool(database_schema_tool=FakeDatabaseSchemaTool())


def test_database_model_context_metadata():
    names = [tool["name"] for tool in _tool().get_tools()]

    assert names == ["build_database_model_context"]


def test_build_database_model_context_for_explicit_tables():
    result = _tool().build_database_model_context(table_names=["boqs", "boq_items"])

    assert result["ok"] is True
    assert result["agent"] == "database_model_context_agent"
    assert result["schema_name"] == "ilife"
    assert result["selected_table_names"] == ["boqs", "boq_items"]
    assert result["model_context"]["table_count"] == 2
    assert result["model_context"]["model_candidates"][0]["model_name"] == "Boqs"
    assert result["model_context"]["tables"][0]["enum_columns"][0]["column_name"] == "status"
    assert result["model_context"]["relationships"][0]["from_table"] == "boqs"
    assert "Enum columns need explicit API validation and frontend option mapping." in result["model_context"]["migration_risks"]


def test_build_database_model_context_can_select_by_focus_terms():
    result = _tool().build_database_model_context(focus_terms=["boq"])

    assert result["ok"] is True
    assert result["selected_table_names"] == ["boqs", "boq_items"]


def test_build_database_model_context_reports_missing_tables():
    result = _tool().build_database_model_context(table_names=["boqs", "missing_table"])

    assert result["ok"] is False
    assert result["table_errors"] == [{"table_name": "missing_table", "error": "missing missing_table"}]
