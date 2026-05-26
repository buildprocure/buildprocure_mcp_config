from __future__ import annotations

from tools.migration_spec_tools import MigrationSpecTool


class FakeArchitectureTool:
    def build_architecture_analysis(self, **kwargs) -> dict:
        return {
            "ok": True,
            "architecture_context": {
                "migration_risks": ["Session-based auth/state must be redesigned or bridged for React/API usage."]
            },
        }


class FakeLegacyTool:
    def analyze_legacy_php_module(self, **kwargs) -> dict:
        return {
            "ok": True,
            "legacy_analysis": {
                "file_count": 2,
                "session_keys": ["company_id"],
                "files": [
                    {
                        "path": "Buyer/boq_list.php",
                        "role_hint": "read_view",
                        "referenced_tables": ["boqs"],
                        "session_keys": ["company_id"],
                        "request_params": ["boq_id"],
                        "upload_fields": [],
                        "redirects": ["boq_view.php"],
                    },
                    {
                        "path": "Buyer/boq_upload.php",
                        "role_hint": "mutation_or_workflow",
                        "referenced_tables": ["boq_items"],
                        "session_keys": ["company_id"],
                        "request_params": [],
                        "upload_fields": ["boq_file"],
                        "redirects": [],
                    },
                ],
                "api_candidates": [
                    {
                        "source_path": "Buyer/boq_list.php",
                        "suggested_route": "/api/legacy/buyer/boq-list",
                        "http_methods": ["GET"],
                        "tables": ["boqs"],
                        "notes": ["Depends on PHP session state; define auth/session contract."],
                    },
                    {
                        "source_path": "Buyer/boq_upload.php",
                        "suggested_route": "/api/legacy/buyer/boq-upload",
                        "http_methods": ["POST"],
                        "tables": ["boq_items"],
                        "notes": ["Handles file upload; define multipart/storage contract."],
                    },
                ],
                "migration_risks": ["File upload behavior must be preserved with explicit API/storage handling."],
            },
        }


class FakeDatabaseModelTool:
    def build_database_model_context(self, **kwargs) -> dict:
        return {
            "ok": True,
            "schema_name": "ilife",
            "model_context": {
                "table_count": 2,
                "model_candidates": [
                    {"table_name": "boqs", "model_name": "Boqs", "primary_keys": ["id"]},
                    {"table_name": "boq_items", "model_name": "BoqItems", "primary_keys": ["id"]},
                ],
                "relationships": [
                    {
                        "from_table": "boq_items",
                        "from_column": "boq_id",
                        "to_table": "boqs",
                        "to_column": "id",
                        "type": "foreign_key",
                    }
                ],
                "data_contracts": [
                    {
                        "table_name": "boqs",
                        "read_fields": ["id", "status"],
                        "create_fields": ["status"],
                        "update_fields": ["status"],
                        "required_create_fields": ["status"],
                    },
                    {
                        "table_name": "boq_items",
                        "read_fields": ["id", "boq_id", "item_id"],
                        "create_fields": ["boq_id", "item_id"],
                        "update_fields": ["boq_id", "item_id"],
                        "required_create_fields": ["boq_id", "item_id"],
                    },
                ],
                "migration_risks": ["Some relationships are inferred from *_id naming and should be verified."],
                "tables": [{"table_name": "boq_items", "relationship_hints": [{"type": "foreign_key"}]}],
            },
        }


def _tool() -> MigrationSpecTool:
    return MigrationSpecTool(
        architecture_agent_tool=FakeArchitectureTool(),
        legacy_php_analysis_tool=FakeLegacyTool(),
        database_model_context_tool=FakeDatabaseModelTool(),
    )


def test_migration_spec_metadata():
    names = [tool["name"] for tool in _tool().get_tools()]

    assert names == ["build_migration_spec"]


def test_build_migration_spec_composes_contexts():
    result = _tool().build_migration_spec(
        repo_name="procurex",
        module_name="Buyer BOQ",
        module_path="Buyer",
        related_paths=["app/Modules/Buyer/BOQ"],
        focus_terms=["boq"],
        table_names=["boqs", "boq_items"],
        work_item_id=51,
    )

    assert result["ok"] is True
    assert result["agent"] == "migration_spec_agent"
    assert result["module_name"] == "Buyer BOQ"
    assert result["schema_name"] == "ilife"
    assert "source_context" in result

    spec = result["migration_spec"]
    assert spec["scope"]["source_file_count"] == 2
    assert spec["backend_api_spec"][0]["route"] == "/api/legacy/buyer/boq-list"
    assert spec["database_model_spec"]["model_candidates"][1]["model_name"] == "BoqItems"
    assert spec["react_spec"]["route_base"] == "/buyer-boq"
    assert spec["react_spec"]["screen_candidates"][0]["component_name"] == "BuyerBOQBoqList"
    assert "File upload behavior is preserved with explicit API/storage handling." in spec["acceptance_criteria"]
    assert "Which session keys should become API auth claims versus request parameters?" in spec["open_questions"]
    assert spec["risks"]
