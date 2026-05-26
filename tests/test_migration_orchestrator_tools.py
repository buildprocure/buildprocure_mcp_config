from __future__ import annotations

from tools.migration_orchestrator_tools import MigrationOrchestratorTool


class FakeReactCodeWriterTool:
    def __init__(self) -> None:
        self.calls = []

    def write_react_conversion_files(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {
            "ok": True,
            "agent": "react_code_writer_agent",
            "target_branch": kwargs["target_branch"],
            "dry_run": kwargs["dry_run"],
            "file_count": 3,
            "generated_files": [
                {"path": "src/features/buyer-boq/routes.tsx", "content": "..."},
            ],
        }


def _tool(fake_writer: FakeReactCodeWriterTool | None = None) -> MigrationOrchestratorTool:
    return MigrationOrchestratorTool(react_code_writer_tool=fake_writer or FakeReactCodeWriterTool())


def test_migration_orchestrator_metadata():
    names = [tool["name"] for tool in _tool().get_tools()]

    assert names == ["run_migration_request"]


def test_run_migration_request_infers_buyer_boq_inputs():
    fake_writer = FakeReactCodeWriterTool()
    result = _tool(fake_writer).run_migration_request(
        request_text="Convert BOQ of Buyer module to React",
        source_repo_name="procurex",
        target_repo_name="procurex-react",
        schema_name="ilife",
        work_item_id=54,
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["agent"] == "migration_orchestrator_agent"
    assert result["inferred_inputs"]["module_name"] == "Buyer BOQ"
    assert result["inferred_inputs"]["module_path"] == "Buyer"
    assert result["inferred_inputs"]["related_paths"] == ["app/Modules/Buyer/BOQ"]
    assert result["inferred_inputs"]["focus_terms"] == ["boq"]
    assert result["inferred_inputs"]["table_names"] == ["boqs", "boq_items"]
    assert result["inferred_inputs"]["target_branch"] == "ab-54-buyer-boq-react-scaffold"

    call = fake_writer.calls[0]
    assert call["source_repo_name"] == "procurex"
    assert call["target_repo_name"] == "procurex-react"
    assert call["module_name"] == "Buyer BOQ"
    assert call["module_path"] == "Buyer"
    assert call["dry_run"] is True
    assert call["schema_name"] == "ilife"


def test_run_migration_request_accepts_overrides():
    fake_writer = FakeReactCodeWriterTool()
    result = _tool(fake_writer).run_migration_request(
        request_text="Convert the selected module to React",
        source_repo_name="procurex",
        target_repo_name="procurex-react",
        module_name="Buyer BOQ",
        module_path="Buyer",
        focus_terms=["boq"],
        table_names=["boqs", "boq_items"],
        related_paths=["app/Modules/Buyer/BOQ"],
        target_branch="custom-branch",
    )

    assert result["ok"] is True
    assert result["inferred_inputs"]["target_branch"] == "custom-branch"
    assert fake_writer.calls[0]["target_branch"] == "custom-branch"


def test_run_migration_request_reports_missing_inputs_when_vague():
    result = _tool().run_migration_request(
        request_text="Convert this to React",
        source_repo_name="procurex",
        target_repo_name="procurex-react",
    )

    assert result["ok"] is False
    assert "module_name" in result["missing_inputs"]
    assert "module_path" in result["missing_inputs"]
