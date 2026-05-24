"""
Database Schema Tools
Read-only MySQL schema inspection using information_schema.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_$]+$")


class DatabaseSchemaTool:
    """Expose read-only MySQL schema metadata for MCP clients."""

    def __init__(self, connection_factory: Any | None = None) -> None:
        self.connection_factory = connection_factory
        self.host = os.getenv("MYSQL_HOST", "localhost")
        self.port = int(os.getenv("MYSQL_PORT", "3306"))
        self.user = os.getenv("MYSQL_USER")
        self.password = os.getenv("MYSQL_PASSWORD")
        self.database = os.getenv("MYSQL_DATABASE")
        self.connect_timeout = int(os.getenv("MYSQL_CONNECT_TIMEOUT", "10"))

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "test_database_connection",
                "description": "Check whether the configured MySQL schema connection works",
            },
            {
                "name": "list_database_tables",
                "description": "List tables and views from the configured MySQL database",
            },
            {
                "name": "describe_database_table",
                "description": "Describe columns, indexes, and foreign keys for one MySQL table",
            },
            {
                "name": "get_database_schema",
                "description": "Get a bounded schema summary for the configured MySQL database",
            },
        ]

    def test_database_connection(self) -> dict[str, Any]:
        config_error = self._validate_config()
        if config_error:
            return config_error

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT DATABASE() AS database_name, VERSION() AS mysql_version")
                    row = cursor.fetchone()
            return {
                "ok": True,
                "host": self.host,
                "port": self.port,
                "database": row.get("database_name"),
                "mysql_version": row.get("mysql_version"),
            }
        except Exception as exc:
            logger.warning("Database connection check failed: %s", exc)
            return self._error(f"Database connection failed: {exc}")

    def list_database_tables(self, schema_name: str | None = None) -> dict[str, Any]:
        schema = self._schema_name(schema_name)
        if isinstance(schema, dict):
            return schema

        query = """
            SELECT
                TABLE_NAME AS table_name,
                TABLE_TYPE AS table_type,
                ENGINE AS engine,
                TABLE_ROWS AS estimated_rows,
                TABLE_COMMENT AS table_comment
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME
        """

        return self._fetch_all(
            query,
            (schema,),
            {"schema_name": schema},
            result_key="tables",
        )

    def describe_database_table(self, table_name: str, schema_name: str | None = None) -> dict[str, Any]:
        schema = self._schema_name(schema_name)
        if isinstance(schema, dict):
            return schema
        if not self._valid_identifier(table_name):
            return self._error(f"Invalid table name: {table_name}")

        columns = self._fetch_all(
            """
            SELECT
                COLUMN_NAME AS column_name,
                COLUMN_TYPE AS column_type,
                IS_NULLABLE AS is_nullable,
                COLUMN_DEFAULT AS column_default,
                COLUMN_KEY AS column_key,
                EXTRA AS extra,
                COLUMN_COMMENT AS column_comment,
                ORDINAL_POSITION AS ordinal_position
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (schema, table_name),
            {},
            result_key="columns",
        )
        if not columns.get("ok"):
            return columns

        indexes = self._fetch_all(
            """
            SELECT
                INDEX_NAME AS index_name,
                NON_UNIQUE AS non_unique,
                COLUMN_NAME AS column_name,
                SEQ_IN_INDEX AS sequence_in_index,
                INDEX_TYPE AS index_type
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
            """,
            (schema, table_name),
            {},
            result_key="indexes",
        )
        if not indexes.get("ok"):
            return indexes

        foreign_keys = self._fetch_all(
            """
            SELECT
                CONSTRAINT_NAME AS constraint_name,
                COLUMN_NAME AS column_name,
                REFERENCED_TABLE_NAME AS referenced_table_name,
                REFERENCED_COLUMN_NAME AS referenced_column_name
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE
                TABLE_SCHEMA = %s
                AND TABLE_NAME = %s
                AND REFERENCED_TABLE_NAME IS NOT NULL
            ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION
            """,
            (schema, table_name),
            {},
            result_key="foreign_keys",
        )
        if not foreign_keys.get("ok"):
            return foreign_keys

        return {
            "ok": True,
            "schema_name": schema,
            "table_name": table_name,
            "columns": columns["columns"],
            "indexes": indexes["indexes"],
            "foreign_keys": foreign_keys["foreign_keys"],
        }

    def get_database_schema(
        self,
        schema_name: str | None = None,
        include_columns: bool = True,
        max_tables: int = 100,
    ) -> dict[str, Any]:
        schema = self._schema_name(schema_name)
        if isinstance(schema, dict):
            return schema

        tables_result = self.list_database_tables(schema)
        if not tables_result.get("ok"):
            return tables_result

        max_tables = max(1, min(max_tables, 500))
        tables = tables_result.get("tables", [])[:max_tables]

        if not include_columns:
            return {
                "ok": True,
                "schema_name": schema,
                "table_count": len(tables_result.get("tables", [])),
                "returned_table_count": len(tables),
                "truncated": len(tables_result.get("tables", [])) > max_tables,
                "tables": tables,
            }

        schema_tables = []
        for table in tables:
            description = self.describe_database_table(table["table_name"], schema_name=schema)
            schema_tables.append(
                {
                    **table,
                    "columns": description.get("columns", []),
                    "indexes": description.get("indexes", []),
                    "foreign_keys": description.get("foreign_keys", []),
                    "error": description.get("error"),
                }
            )

        return {
            "ok": True,
            "schema_name": schema,
            "table_count": len(tables_result.get("tables", [])),
            "returned_table_count": len(schema_tables),
            "truncated": len(tables_result.get("tables", [])) > max_tables,
            "tables": schema_tables,
        }

    def _connect(self) -> Any:
        if self.connection_factory:
            return self.connection_factory()

        import pymysql
        from pymysql.cursors import DictCursor

        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            cursorclass=DictCursor,
            connect_timeout=self.connect_timeout,
            read_timeout=self.connect_timeout,
            write_timeout=self.connect_timeout,
        )

    def _fetch_all(
        self,
        query: str,
        params: tuple[Any, ...],
        metadata: dict[str, Any],
        result_key: str,
    ) -> dict[str, Any]:
        config_error = self._validate_config()
        if config_error:
            return config_error | metadata | {result_key: []}

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
            return {"ok": True, **metadata, result_key: list(rows)}
        except Exception as exc:
            logger.warning("Database schema query failed: %s", exc)
            return self._error(f"Database schema query failed: {exc}") | metadata | {result_key: []}

    def _schema_name(self, schema_name: str | None) -> str | dict[str, Any]:
        schema = schema_name or self.database
        if not schema:
            return self._error("MYSQL_DATABASE is required")
        if not self._valid_identifier(schema):
            return self._error(f"Invalid schema name: {schema}")
        return schema

    def _validate_config(self) -> dict[str, Any] | None:
        missing = [
            name
            for name, value in {
                "MYSQL_HOST": self.host,
                "MYSQL_USER": self.user,
                "MYSQL_PASSWORD": self.password,
                "MYSQL_DATABASE": self.database,
            }.items()
            if not value
        ]
        if missing:
            return self._error(f"Missing database configuration: {', '.join(missing)}")
        return None

    def _valid_identifier(self, value: str) -> bool:
        return bool(IDENTIFIER_PATTERN.match(value))

    def _error(self, message: str) -> dict[str, Any]:
        return {"ok": False, "error": message}
