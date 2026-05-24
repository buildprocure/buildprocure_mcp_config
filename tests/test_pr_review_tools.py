from __future__ import annotations

from tools.pr_review_tools import PRReviewTool


class FakeGitHub:
    def __init__(self, tree: list[str] | None = None) -> None:
        self.tree = tree if tree is not None else ["README.md", "models/invoice.py"]

    def list_open_pull_requests(self, repo_name: str) -> list[dict]:
        return [self._pr()]

    def get_pull_request(self, repo_name: str, pr_number: int) -> dict:
        return self._pr()

    def get_pull_request_files(self, repo_name: str, pr_number: int) -> list[dict]:
        return [
            {
                "filename": "models/invoice.py",
                "status": "modified",
                "additions": 4,
                "deletions": 1,
                "changes": 5,
                "patch": "SELECT * FROM Invoice WHERE id = invoice_id",
                "raw_url": "https://example.test/raw",
                "blob_url": "https://example.test/blob",
            }
        ]

    def get_pull_request_diff(self, repo_name: str, pr_number: int) -> str:
        return "diff --git a/models/invoice.py b/models/invoice.py\n+SELECT * FROM Invoice"

    def get_repo_tree_safe(self, repo_name: str, ref: str = "main") -> dict:
        return {
            "ok": True,
            "repo_name": repo_name,
            "target_ref": ref,
            "file_count": len(self.tree),
            "tree": self.tree,
        }

    def _pr(self) -> dict:
        return {
            "number": 7,
            "title": "AB#123 Update invoice query",
            "body": "Uses Invoice table",
            "state": "open",
            "html_url": "https://example.test/pr/7",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
            "user": {"login": "developer"},
            "base": {"ref": "main", "sha": "base-sha"},
            "head": {"ref": "feature/invoice", "sha": "head-sha"},
        }


class FakeAzure:
    def __init__(self) -> None:
        self.calls = 0

    def get_context_for_text(self, text: str) -> dict:
        self.calls += 1
        return {
            "work_item_ids": [123],
            "work_items": [{"id": 123, "title": "Update invoice query"}],
            "wiki_pages": [],
        }

    def extract_work_item_ids(self, text: str) -> list[int]:
        return [123]


class FakeAgentContext:
    def build_agent_context(self, repo_name: str, target_ref: str = "main", paths: list[str] | None = None) -> dict:
        return {
            "ok": True,
            "selected_paths": paths or [],
            "selected_files": [
                {
                    "path": "models/invoice.py",
                    "html_url": "https://example.test/models/invoice.py",
                    "content": "def get_invoice(): pass",
                }
            ]
            if paths
            else [],
            "file_errors": [],
            "manifest_summary": {"ok": True, "stack_summary": {"runtime_hints": ["python"]}},
            "config_summary": {"configs": {}},
        }


class FakeDatabaseSchema:
    def list_database_tables(self) -> dict:
        return {
            "ok": True,
            "schema_name": "ilife",
            "tables": [
                {"table_name": "Invoice", "table_type": "BASE TABLE"},
                {"table_name": "projects", "table_type": "BASE TABLE"},
            ],
        }

    def describe_database_table(self, table_name: str) -> dict:
        return {
            "ok": True,
            "schema_name": "ilife",
            "table_name": table_name,
            "columns": [{"column_name": "id", "column_type": "int"}],
            "indexes": [],
            "foreign_keys": [],
        }


def _tool(tree: list[str] | None = None, azure: FakeAzure | None = None) -> PRReviewTool:
    return PRReviewTool(
        github=FakeGitHub(tree=tree),
        azure=azure or FakeAzure(),
        agent_context_tool=FakeAgentContext(),
        database_schema_tool=FakeDatabaseSchema(),
    )


def test_pr_review_tool_metadata():
    tool = _tool()
    tools = tool.get_tools()
    names = [t["name"] for t in tools]

    assert "list_open_pull_requests" in names
    assert "get_pull_request_details" in names
    assert "get_pr_review_context" in names


def test_list_open_pull_requests_returns_normalized_result():
    result = _tool().list_open_pull_requests("procurex")

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["pull_requests"][0]["number"] == 7
    assert result["pull_requests"][0]["base_branch"] == "main"


def test_get_pr_review_context_includes_azure_repo_and_database_context():
    azure = FakeAzure()
    result = _tool(azure=azure).get_pr_review_context("procurex", 7)

    assert result["ok"] is True
    assert result["pr_number"] == 7
    assert result["azure_devops_context"]["work_item_ids"] == [123]
    assert azure.calls == 1
    assert "models/invoice.py" in result["repository_context"]["selected_context_files"]
    assert result["database_schema_context"]["matched_table_names"] == ["Invoice"]
    assert result["database_schema_context"]["matched_tables"][0]["table_name"] == "Invoice"
    assert "database_schema_impact" in result["expected_review_output_format"]


def test_get_pr_review_context_handles_empty_context_file_selection():
    azure = FakeAzure()
    result = _tool(tree=[], azure=azure).get_pr_review_context("procurex", 7)

    assert result["ok"] is True
    assert result["repository_context"]["selected_context_files"] == []
    assert result["repository_context"]["files"] == {}
    assert result["azure_devops_context"]["work_item_ids"] == [123]
    assert azure.calls == 1


def test_get_pr_review_context_can_skip_database_schema():
    result = _tool().get_pr_review_context("procurex", 7, include_database_schema=False)

    assert result["ok"] is True
    assert result["database_schema_context"] == {"enabled": False}
