from __future__ import annotations

from tools.react_code_writer_tools import ReactCodeWriterTool


class FakeReactConversionTool:
    def build_react_conversion_plan(self, **kwargs) -> dict:
        return {
            "ok": True,
            "schema_name": "ilife",
            "react_conversion_plan": {
                "feature_slug": "buyer-boq",
                "feature_dir": "src/features/buyer-boq",
                "route_plan": {
                    "route_base": "/buyer-boq",
                    "route_file": "src/features/buyer-boq/routes.tsx",
                    "screen_routes": [
                        {
                            "path": "/buyer-boq/boq-list",
                            "component_name": "BuyerBOQBoqList",
                            "source_path": "Buyer/boq_list.php",
                        }
                    ],
                },
                "file_plan": {
                    "components": [
                        {
                            "component_name": "BuyerBOQBoqList",
                            "path": "src/features/buyer-boq/components/BuyerBOQBoqList.tsx",
                            "source_path": "Buyer/boq_list.php",
                            "role_hint": "read_view",
                        }
                    ],
                    "hooks": [
                        {
                            "hook_name": "useBoqList",
                            "path": "src/features/buyer-boq/hooks/useBoqList.ts",
                            "api_route": "/api/legacy/buyer/boq-list",
                            "methods": ["GET"],
                        }
                    ],
                    "api_client": "src/features/buyer-boq/api/buyerBoqApi.ts",
                    "types": "src/features/buyer-boq/types.ts",
                    "index": "src/features/buyer-boq/index.ts",
                    "tests": ["src/features/buyer-boq/__tests__/BuyerBOQBoqList.test.tsx"],
                },
                "component_plan": [],
                "data_fetching_plan": [
                    {
                        "route": "/api/legacy/buyer/boq-list",
                        "methods": ["GET"],
                        "tables": ["boqs"],
                        "client_function": "fetchBoqList",
                        "notes": [],
                    }
                ],
                "form_plan": [
                    {
                        "table_name": "boqs",
                        "create_fields": ["status"],
                        "update_fields": ["status"],
                        "required_fields": ["status"],
                    }
                ],
                "state_plan": [],
                "implementation_steps": ["Create feature folder."],
                "test_plan": ["Render each migrated screen with mocked API data."],
                "risks": [],
                "open_questions": [],
            },
        }


def _tool() -> ReactCodeWriterTool:
    return ReactCodeWriterTool(react_conversion_tool=FakeReactConversionTool())


def test_react_code_writer_metadata():
    names = [tool["name"] for tool in _tool().get_tools()]

    assert names == ["write_react_conversion_files"]


def test_write_react_conversion_files_generates_local_files_only():
    result = _tool().write_react_conversion_files(
        source_repo_name="procurex",
        target_repo_name="procurex-react",
        module_name="Buyer BOQ",
        work_item_id=53,
        dry_run=False,
        create_pull_request=True,
    )

    assert result["ok"] is True
    assert result["agent"] == "react_code_writer_agent"
    assert result["dry_run"] is True
    assert result["requested_dry_run"] is False
    assert result["requested_create_pull_request"] is True
    assert result["remote_writes_enabled"] is False
    assert result["target_branch"] == "ab-53-buyer-boq-react-scaffold"
    assert result["file_count"] >= 7

    paths = {file_data["path"] for file_data in result["generated_files"]}
    assert "src/features/buyer-boq/types.ts" in paths
    assert "src/features/buyer-boq/api/buyerBoqApi.ts" in paths
    assert "src/features/buyer-boq/components/BuyerBOQBoqList.tsx" in paths
    assert "src/features/buyer-boq/hooks/useBoqList.ts" in paths
    assert "src/features/buyer-boq/routes.tsx" in paths
    assert result["local_files"] == result["generated_files"]
    assert result["write_results"] == []
    assert result["pull_request"] is None

    api_file = next(file_data for file_data in result["generated_files"] if file_data["path"].endswith("buyerBoqApi.ts"))
    assert "export async function fetchBoqList" in api_file["content"]
