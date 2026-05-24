from __future__ import annotations

from tools.database_schema_tools import DatabaseSchemaTool


class FakeCursor:
    def __init__(self, rows_by_query: dict[str, list[dict]]) -> None:
        self.rows_by_query = rows_by_query
        self.rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def execute(self, query: str, params: tuple | None = None) -> None:
        normalized_query = " ".join(query.split())
        for key, rows in self.rows_by_query.items():
            if key in normalized_query:
                self.rows = rows
                return
        self.rows = []

    def fetchone(self) -> dict:
        return self.rows[0] if self.rows else {}

    def fetchall(self) -> list[dict]:
        return self.rows


class FakeConnection:
    def __init__(self, rows_by_query: dict[str, list[dict]]) -> None:
        self.rows_by_query = rows_by_query

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.rows_by_query)


def _tool(monkeypatch, rows_by_query: dict[str, list[dict]]) -> DatabaseSchemaTool:
    monkeypatch.setenv("MYSQL_HOST", "db.example.test")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_USER", "readonly")
    monkeypatch.setenv("MYSQL_PASSWORD", "secret")
    monkeypatch.setenv("MYSQL_DATABASE", "buildprocure")
    return DatabaseSchemaTool(connection_factory=lambda: FakeConnection(rows_by_query))


def test_database_connection_uses_configured_schema(monkeypatch):
    tool = _tool(
        monkeypatch,
        {
            "SELECT DATABASE()": [
                {"database_name": "buildprocure", "mysql_version": "8.0.36"},
            ],
        },
    )

    result = tool.test_database_connection()

    assert result["ok"] is True
    assert result["database"] == "buildprocure"
    assert result["mysql_version"] == "8.0.36"


def test_list_database_tables(monkeypatch):
    tool = _tool(
        monkeypatch,
        {
            "FROM information_schema.TABLES": [
                {"table_name": "users", "table_type": "BASE TABLE", "engine": "InnoDB", "estimated_rows": 5},
            ],
        },
    )

    result = tool.list_database_tables()

    assert result["ok"] is True
    assert result["schema_name"] == "buildprocure"
    assert result["tables"][0]["table_name"] == "users"


def test_describe_database_table(monkeypatch):
    tool = _tool(
        monkeypatch,
        {
            "FROM information_schema.COLUMNS": [
                {"column_name": "id", "column_type": "int", "is_nullable": "NO"},
            ],
            "FROM information_schema.STATISTICS": [
                {"index_name": "PRIMARY", "column_name": "id", "non_unique": 0},
            ],
            "FROM information_schema.KEY_COLUMN_USAGE": [],
        },
    )

    result = tool.describe_database_table("users")

    assert result["ok"] is True
    assert result["table_name"] == "users"
    assert result["columns"][0]["column_name"] == "id"
    assert result["indexes"][0]["index_name"] == "PRIMARY"
    assert result["foreign_keys"] == []


def test_invalid_table_name_is_rejected(monkeypatch):
    tool = _tool(monkeypatch, {})

    result = tool.describe_database_table("users; DROP TABLE users")

    assert result["ok"] is False
    assert "Invalid table name" in result["error"]


def test_missing_config_returns_readable_error(monkeypatch):
    monkeypatch.delenv("MYSQL_USER", raising=False)
    monkeypatch.setenv("MYSQL_HOST", "localhost")
    monkeypatch.setenv("MYSQL_PASSWORD", "secret")
    monkeypatch.setenv("MYSQL_DATABASE", "buildprocure")

    result = DatabaseSchemaTool(connection_factory=lambda: FakeConnection({})).list_database_tables()

    assert result["ok"] is False
    assert "MYSQL_USER" in result["error"]
