from __future__ import annotations

from tools.architecture_agent_tools import ArchitectureAgentTool


class FakeContentTool:
    def get_repo_tree(self, repo_name: str, target_ref: str = "main") -> dict:
        return {
            "ok": True,
            "repo_name": repo_name,
            "target_ref": target_ref,
            "file_count": 8,
            "tree": [
                "index.php",
                "login.php",
                "includes/db.php",
                "includes/auth.php",
                "modules/invoices/list.php",
                "modules/invoices/upload.php",
                "assets/app.css",
                "composer.json",
            ],
        }


class FakeAgentContextTool:
    def build_agent_context(self, repo_name: str, target_ref: str = "main", paths: list[str] | None = None) -> dict:
        selected_files = []
        for path in paths or []:
            content = ""
            if path.endswith("auth.php"):
                content = "session_start(); $_SESSION['user_id'];"
            elif path.endswith("db.php"):
                content = "mysqli_connect();"
            elif path.endswith("list.php"):
                content = "SELECT * FROM Invoice"
            elif path.endswith("upload.php"):
                content = "$_FILES['invoice']; move_uploaded_file();"
            selected_files.append({"path": path, "content": content, "html_url": f"https://example.test/{path}"})

        return {
            "ok": True,
            "repository": {"name": repo_name, "default_branch": target_ref},
            "selected_paths": paths or [],
            "selected_files": selected_files,
            "file_errors": [],
            "manifest_summary": {"ok": True, "stack_summary": {"runtime_hints": ["php"]}},
            "config_summary": {"configs": {}},
        }


class FakeDatabaseSchemaTool:
    def get_database_schema(self, schema_name=None, include_columns: bool = True, max_tables: int = 100) -> dict:
        return {
            "ok": True,
            "schema_name": "ilife",
            "table_count": 2,
            "truncated": False,
            "tables": [
                {"table_name": "Invoice", "table_type": "BASE TABLE"},
                {"table_name": "projects", "table_type": "BASE TABLE"},
            ],
        }


class FakeAzure:
    def __init__(self) -> None:
        self.created = []

    def get_work_item(self, work_item_id: int) -> dict:
        return {
            "id": work_item_id,
            "type": "Feature",
            "title": "Architecture Agent",
            "priority": 2,
            "area_path": "BuildProcure",
            "iteration_path": "BuildProcure\\Sprint 1",
        }

    def create_child_work_item(self, **kwargs) -> dict:
        self.created.append(kwargs)
        return {
            "id": 100 + len(self.created),
            "type": kwargs["work_item_type"],
            "title": kwargs["title"],
            "assigned_to": kwargs.get("assigned_to"),
            "url": f"https://example.test/{100 + len(self.created)}",
        }


def _tool() -> ArchitectureAgentTool:
    return ArchitectureAgentTool(
        agent_context_tool=FakeAgentContextTool(),
        content_tool=FakeContentTool(),
        database_schema_tool=FakeDatabaseSchemaTool(),
        azure=FakeAzure(),
    )


def test_architecture_agent_metadata():
    names = [tool["name"] for tool in _tool().get_tools()]

    assert names == ["build_architecture_analysis", "create_architecture_child_tickets"]


def test_build_architecture_analysis_collects_migration_evidence():
    result = _tool().build_architecture_analysis("procurex", work_item_id=47)

    assert result["ok"] is True
    assert result["agent"] == "architecture_agent"
    assert result["azure_context"]["work_item"]["id"] == 47
    assert "index.php" in result["architecture_context"]["legacy_php_entrypoints"]
    assert "includes/db.php" in result["architecture_context"]["shared_includes"]
    assert {"path": "index.php", "route_hint": "/"} in result["architecture_context"]["routing_hints"]
    assert result["database_context"]["tables"][0]["table_name"] == "Invoice"
    assert result["architecture_context"]["auth_session_hints"]
    assert result["architecture_context"]["sql_usage_hints"]
    assert result["architecture_context"]["file_upload_hints"]
    assert result["architecture_context"]["migration_risks"]
    assert "target_react_architecture" in result["expected_agent_output"]


def test_build_architecture_analysis_can_skip_database_schema():
    result = _tool().build_architecture_analysis("procurex", include_database_schema=False)

    assert result["database_context"] == {"enabled": False, "tables": []}
    assert result["architecture_context"]["database_tables"] == []


def test_create_architecture_child_tickets_dry_run_suggests_without_creating():
    tool = _tool()
    result = tool.create_architecture_child_tickets(
        parent_work_item_id=47,
        repo_name="procurex",
        migration_goal="Migrate Buyer BOQ to React",
        module_name="Buyer BOQ",
        module_path="Buyer",
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["created_tickets"] == []
    assert result["suggested_ticket_count"] >= 3
    assert any("auth/session bridge" in ticket["title"] for ticket in result["suggested_tickets"])
    assert any("backend API bridge" in ticket["title"] for ticket in result["suggested_tickets"])


def test_create_architecture_child_tickets_creates_when_dry_run_false():
    azure = FakeAzure()
    tool = ArchitectureAgentTool(
        agent_context_tool=FakeAgentContextTool(),
        content_tool=FakeContentTool(),
        database_schema_tool=FakeDatabaseSchemaTool(),
        azure=azure,
    )

    result = tool.create_architecture_child_tickets(
        parent_work_item_id=47,
        repo_name="procurex",
        migration_goal="Migrate Buyer BOQ to React",
        module_name="Buyer BOQ",
        module_path="Buyer",
        assigned_to="rabin@example.test",
        dry_run=False,
    )

    assert result["ok"] is True
    assert result["created_ticket_count"] == result["suggested_ticket_count"]
    assert azure.created
    assert azure.created[0]["parent_work_item_id"] == 47
    assert azure.created[0]["assigned_to"] == "rabin@example.test"
