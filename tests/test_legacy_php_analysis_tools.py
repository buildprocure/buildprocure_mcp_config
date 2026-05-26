from __future__ import annotations

from tools.legacy_php_analysis_tools import LegacyPHPAnalysisTool


class FakeContentTool:
    tree = [
        "Buyer/boq_list.php",
        "Buyer/boq_upload.php",
        "Buyer/createPO.php",
        "app/Modules/Buyer/BOQ/BOQController.php",
        "Supplier/po_list.php",
        "README.md",
    ]

    files = {
        "Buyer/boq_list.php": """
            <?php
            session_start();
            require_once '../_dbconnect.php';
            $companyId = $_SESSION['company_id'];
            $boqId = $_GET['boq_id'];
            $result = mysqli_query($conn, "SELECT * FROM boqs WHERE id = $boqId");
            header("Location: boq_view.php");
        """,
        "Buyer/boq_upload.php": """
            <form method="post" action="boq_upload.php" enctype="multipart/form-data">
            <?php
            $file = $_FILES['boq_file'];
            move_uploaded_file($file['tmp_name'], '/tmp/example');
            INSERT INTO boq_items (boq_id, item_id) VALUES (1, 2);
        """,
        "app/Modules/Buyer/BOQ/BOQController.php": """
            <?php
            include_once 'BOQModel.php';
            $model->lock($_POST['boq_id']);
            UPDATE boqs SET status = 'locked';
        """,
    }

    def get_repo_tree(self, repo_name: str, target_ref: str = "main") -> dict:
        return {"ok": True, "repo_name": repo_name, "target_ref": target_ref, "tree": self.tree}

    def get_repo_files_batch(self, repo_name: str, paths: list[str], target_ref: str = "main") -> dict:
        return {
            "ok": True,
            "files": [
                {
                    "path": path,
                    "content": self.files.get(path, ""),
                    "html_url": f"https://example.test/{path}",
                    "content_truncated": False,
                }
                for path in paths
            ],
            "errors": [],
        }


class FakeDatabaseSchemaTool:
    def get_database_schema(self, schema_name=None, include_columns: bool = True, max_tables: int = 100) -> dict:
        return {
            "ok": True,
            "schema_name": "ilife",
            "table_count": 3,
            "truncated": False,
            "tables": [
                {"table_name": "boqs", "table_type": "BASE TABLE"},
                {"table_name": "boq_items", "table_type": "BASE TABLE"},
                {"table_name": "purchase_orders", "table_type": "BASE TABLE"},
            ],
        }


def _tool() -> LegacyPHPAnalysisTool:
    return LegacyPHPAnalysisTool(
        content_tool=FakeContentTool(),
        database_schema_tool=FakeDatabaseSchemaTool(),
    )


def test_legacy_php_analysis_metadata():
    names = [tool["name"] for tool in _tool().get_tools()]

    assert names == ["analyze_legacy_php_module"]


def test_analyze_legacy_php_module_uses_parameterized_scope():
    result = _tool().analyze_legacy_php_module(
        "procurex",
        module_path="Buyer",
        related_paths=["app/Modules/Buyer/BOQ"],
        focus_terms=["boq"],
    )

    assert result["ok"] is True
    assert result["agent"] == "legacy_php_analysis_agent"
    assert result["module_path"] == "Buyer"
    assert result["focus_terms"] == ["boq"]
    assert "Buyer/boq_list.php" in result["selected_paths"]
    assert "Buyer/createPO.php" not in result["selected_paths"]
    assert "app/Modules/Buyer/BOQ/BOQController.php" in result["selected_paths"]
    assert result["database_context"]["ok"] is True

    analysis = result["legacy_analysis"]
    assert analysis["file_count"] == 3
    assert "boqs" in analysis["referenced_tables"]
    assert "boq_items" in analysis["referenced_tables"]
    assert "company_id" in analysis["session_keys"]
    assert "boq_id" in analysis["request_params"]
    assert analysis["api_candidates"]
    assert analysis["migration_risks"]


def test_analyze_legacy_php_module_can_skip_database_schema():
    result = _tool().analyze_legacy_php_module(
        "procurex",
        module_path="Buyer",
        focus_terms=["boq"],
        include_database_schema=False,
    )

    assert result["database_context"] == {"enabled": False, "tables": []}
