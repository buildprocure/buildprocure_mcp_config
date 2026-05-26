from __future__ import annotations

from tools.backend_api_bridge_tools import BackendAPIBridgeTool


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
                        "contracts": [
                            {
                                "table_name": "boqs",
                                "create_fields": ["status"],
                                "update_fields": ["status"],
                            }
                        ],
                        "notes": ["Depends on PHP session state; define auth/session contract."],
                    },
                    {
                        "source_path": "Buyer/boq_upload.php",
                        "route": "/api/legacy/buyer/boq-upload",
                        "methods": ["POST"],
                        "tables": ["boq_items"],
                        "contracts": [],
                        "notes": ["Handles file upload; define multipart/storage contract."],
                    },
                ],
                "risks": ["File upload behavior must be preserved with explicit API/storage handling."],
            },
        }


def _tool() -> BackendAPIBridgeTool:
    return BackendAPIBridgeTool(migration_spec_tool=FakeMigrationSpecTool())


def test_backend_api_bridge_metadata():
    names = [tool["name"] for tool in _tool().get_tools()]

    assert names == ["generate_backend_api_bridge_files"]


def test_generate_backend_api_bridge_files_returns_local_php_files():
    result = _tool().generate_backend_api_bridge_files(
        repo_name="procurex",
        module_name="Buyer BOQ",
        module_path="Buyer",
        focus_terms=["boq"],
        table_names=["boqs", "boq_items"],
        schema_name="ilife",
        work_item_id=56,
    )

    assert result["ok"] is True
    assert result["agent"] == "backend_api_bridge_agent"
    assert result["remote_writes_enabled"] is False
    assert result["schema_name"] == "ilife"

    paths = {file_data["path"] for file_data in result["local_files"]}
    assert "api/buyer-boq/bootstrap.php" in paths
    assert "api/buyer-boq/response.php" in paths
    assert "api/buyer-boq/boq-list.php" in paths
    assert "api/buyer-boq/boq-upload.php" in paths
    assert "api/buyer-boq/README.md" in paths

    list_file = next(file_data for file_data in result["local_files"] if file_data["path"] == "api/buyer-boq/boq-list.php")
    assert "SELECT * FROM `boqs` LIMIT 200" in list_file["content"]
    assert "Buyer/boq_list.php" in list_file["content"]

    upload_file = next(file_data for file_data in result["local_files"] if file_data["path"] == "api/buyer-boq/boq-upload.php")
    assert "TODO: implement mutation behavior" in upload_file["content"]


def test_generate_backend_api_bridge_files_handles_failed_spec():
    class FailedSpec:
        def build_migration_spec(self, **kwargs) -> dict:
            return {"ok": False, "error": "missing context"}

    result = BackendAPIBridgeTool(migration_spec_tool=FailedSpec()).generate_backend_api_bridge_files(
        repo_name="procurex",
        module_name="Buyer BOQ",
    )

    assert result["ok"] is False
    assert result["error"] == "Migration spec failed"
