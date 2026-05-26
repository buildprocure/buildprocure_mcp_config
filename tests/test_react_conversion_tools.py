from __future__ import annotations

from tools.react_conversion_tools import ReactConversionTool


class FakeMigrationSpecTool:
    def build_migration_spec(self, **kwargs) -> dict:
        return {
            "ok": True,
            "schema_name": "ilife",
            "migration_spec": {
                "backend_api_spec": [
                    {
                        "source_path": "Buyer/boq_list.php",
                        "route": "/api/legacy/buyer/boq-list",
                        "methods": ["GET"],
                        "tables": ["boqs"],
                        "contracts": [{"table_name": "boqs", "read_fields": ["id", "status"]}],
                        "notes": ["Depends on PHP session state; define auth/session contract."],
                    },
                    {
                        "source_path": "Buyer/boq_upload.php",
                        "route": "/api/legacy/buyer/boq-upload",
                        "methods": ["POST"],
                        "tables": ["boq_items"],
                        "contracts": [{"table_name": "boq_items", "create_fields": ["boq_id", "item_id"]}],
                        "notes": ["Handles file upload; define multipart/storage contract."],
                    },
                ],
                "database_model_spec": {
                    "data_contracts": [
                        {
                            "table_name": "boqs",
                            "create_fields": ["status"],
                            "update_fields": ["status"],
                            "required_create_fields": ["status"],
                        }
                    ]
                },
                "react_spec": {
                    "route_base": "/buyer-boq",
                    "screen_candidates": [
                        {
                            "source_path": "Buyer/boq_list.php",
                            "component_name": "BuyerBOQBoqList",
                            "role_hint": "read_view",
                        },
                        {
                            "source_path": "Buyer/boq_upload.php",
                            "component_name": "BuyerBOQBoqUpload",
                            "role_hint": "mutation_or_workflow",
                        },
                    ],
                    "api_dependencies": [
                        "/api/legacy/buyer/boq-list",
                        "/api/legacy/buyer/boq-upload",
                    ],
                    "form_contracts": [],
                    "state_notes": ["Replace direct PHP session access with API-backed auth/user context."],
                },
                "risks": ["File upload behavior must be preserved with explicit API/storage handling."],
                "open_questions": ["Where should uploaded files be stored?"],
            },
        }


def _tool() -> ReactConversionTool:
    return ReactConversionTool(migration_spec_tool=FakeMigrationSpecTool())


def test_react_conversion_metadata():
    names = [tool["name"] for tool in _tool().get_tools()]

    assert names == ["build_react_conversion_plan"]


def test_build_react_conversion_plan_from_migration_spec():
    result = _tool().build_react_conversion_plan(
        repo_name="procurex",
        module_name="Buyer BOQ",
        module_path="Buyer",
        related_paths=["app/Modules/Buyer/BOQ"],
        focus_terms=["boq"],
        table_names=["boqs", "boq_items"],
        schema_name="ilife",
        work_item_id=52,
        react_app_root="src",
    )

    assert result["ok"] is True
    assert result["agent"] == "react_conversion_agent"
    assert result["schema_name"] == "ilife"

    plan = result["react_conversion_plan"]
    assert plan["feature_slug"] == "buyer-boq"
    assert plan["feature_dir"] == "src/features/buyer-boq"
    assert plan["route_plan"]["route_base"] == "/buyer-boq"
    assert plan["route_plan"]["screen_routes"][0]["path"] == "/buyer-boq/boq-list"
    assert plan["file_plan"]["api_client"] == "src/features/buyer-boq/api/buyerBoqApi.ts"
    assert plan["file_plan"]["components"][0]["path"] == "src/features/buyer-boq/components/BuyerBOQBoqList.tsx"
    assert plan["file_plan"]["hooks"][1]["hook_name"] == "useBoqUpload"
    assert plan["component_plan"][1]["responsibility"] == "Render a workflow form/action screen with mutation handling."
    assert plan["form_plan"][0]["validation_notes"] == ["status is required"]
    assert "Verify upload form validation and submission states." in plan["test_plan"]
    assert result["migration_spec_context"]["ok"] is True
