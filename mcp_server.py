#!/usr/bin/env python3
"""
BuildProcure MCP Server
Main entry point for the reusable basic Model Context Protocol tools.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from tools.agent_context_tools import AgentContextTool
from tools.architecture_agent_tools import ArchitectureAgentTool
from tools.config_tools import ConfigTool
from tools.cross_repo_search_tools import CrossRepoSearchTool
from tools.database_schema_tools import DatabaseSchemaTool
from tools.dependency_analyzer_tools import DependencyAnalyzerTool
from tools.pr_review_tools import PRReviewTool
from tools.repository_content_tools import RepositoryContentTool
from tools.unified_workspace_tools import UnifiedWorkspaceTool
from utils.config_manager import ConfigManager
from utils.github_helpers import GitHubHelper
from utils.repo_discovery import RepositoryDiscovery

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

mcp = FastMCP("buildprocure-mcp")


class BuildProcureService:
    def __init__(self) -> None:
        self.name = os.getenv("MCP_SERVER_NAME", "buildprocure-mcp")
        self.version = os.getenv("MCP_SERVER_VERSION", "1.0.0")
        self.config = ConfigManager()
        self.github = GitHubHelper()
        self.discovery = RepositoryDiscovery(github=self.github, config=self.config)

        self.workspace_tool = UnifiedWorkspaceTool(discovery=self.discovery)
        self.content_tool = RepositoryContentTool(github=self.github)
        self.search_tool = CrossRepoSearchTool(github=self.github, discovery=self.discovery)
        self.dep_tool = DependencyAnalyzerTool(github=self.github)
        self.config_tool = ConfigTool(config=self.config)
        self.database_schema_tool = DatabaseSchemaTool()
        self.agent_context_tool = AgentContextTool(
            github=self.github,
            config=self.config,
            content_tool=self.content_tool,
            dependency_tool=self.dep_tool,
        )
        self.architecture_agent_tool = ArchitectureAgentTool(
            github=self.github,
            agent_context_tool=self.agent_context_tool,
            content_tool=self.content_tool,
            database_schema_tool=self.database_schema_tool,
        )
        self.pr_review_tool = PRReviewTool(
            github=self.github,
            agent_context_tool=self.agent_context_tool,
            database_schema_tool=self.database_schema_tool,
        )

        logger.info("Initializing basic MCP tools...")
        for tool_group in [
            self.workspace_tool,
            self.content_tool,
            self.search_tool,
            self.dep_tool,
            self.config_tool,
            self.database_schema_tool,
            self.agent_context_tool,
            self.architecture_agent_tool,
            self.pr_review_tool,
        ]:
            logger.info("Loaded %s tools from %s", len(tool_group.get_tools()), tool_group.__class__.__name__)


service = BuildProcureService()


@mcp.tool()
def list_all_repos(include_archived: bool = False) -> dict[str, Any]:
    """List BuildProcure repositories that match discovery policy."""
    return service.workspace_tool.list_all_repos(include_archived=include_archived)


@mcp.tool()
def get_repo_info(repo_name: str) -> dict[str, Any]:
    """Get normalized information about a BuildProcure repository."""
    return service.workspace_tool.get_repo_info(repo_name)


@mcp.tool()
def get_repo_tree(repo_name: str, target_ref: str = "main") -> dict[str, Any]:
    """Get a repository file tree for a branch, tag, or commit ref."""
    return service.content_tool.get_repo_tree(repo_name, target_ref=target_ref)


@mcp.tool()
def get_repo_file(repo_name: str, path: str, target_ref: str = "main") -> dict[str, Any]:
    """Get one repository file by path and ref."""
    return service.content_tool.get_repo_file(repo_name, path, target_ref=target_ref)


@mcp.tool()
def get_repo_files_batch(repo_name: str, paths: list[str], target_ref: str = "main") -> dict[str, Any]:
    """Get multiple repository files by path and ref."""
    return service.content_tool.get_repo_files_batch(repo_name, paths, target_ref=target_ref)


@mcp.tool()
def get_repo_manifest_summary(repo_name: str, target_ref: str = "main") -> dict[str, Any]:
    """Detect repository manifests, stack hints, scripts, tests, and deployment hints."""
    return service.dep_tool.get_repo_manifest_summary(repo_name, target_ref=target_ref)


@mcp.tool()
def analyze_dependencies(repo_name: str, target_ref: str = "main") -> dict[str, Any]:
    """Alias for get_repo_manifest_summary."""
    return service.dep_tool.analyze_dependencies(repo_name, target_ref=target_ref)


@mcp.tool()
def search_across_repos(
    query: str,
    include_archived: bool = False,
    max_results: int = 50,
) -> dict[str, Any]:
    """Search across policy-matching repositories and return bounded snippets."""
    return service.search_tool.search_across_repos(
        query,
        include_archived=include_archived,
        max_results=max_results,
    )


@mcp.tool()
def list_available_configs() -> dict[str, Any]:
    """List available YAML configs and readable load errors."""
    return service.config_tool.list_available_configs()


@mcp.tool()
def get_config(config_name: str) -> dict[str, Any]:
    """Get one loaded config by name."""
    return service.config_tool.get_config(config_name)


@mcp.tool()
def build_agent_context(
    repo_name: str,
    target_ref: str = "main",
    paths: list[str] | None = None,
) -> dict[str, Any]:
    """Build generic reusable repository context for future agents."""
    return service.agent_context_tool.build_agent_context(
        repo_name,
        target_ref=target_ref,
        paths=paths,
    )


@mcp.tool()
def test_database_connection() -> dict[str, Any]:
    """Check whether the configured MySQL schema connection works."""
    return service.database_schema_tool.test_database_connection()


@mcp.tool()
def list_database_tables(schema_name: str | None = None) -> dict[str, Any]:
    """List tables and views from the configured MySQL database."""
    return service.database_schema_tool.list_database_tables(schema_name=schema_name)


@mcp.tool()
def describe_database_table(table_name: str, schema_name: str | None = None) -> dict[str, Any]:
    """Describe columns, indexes, and foreign keys for one MySQL table."""
    return service.database_schema_tool.describe_database_table(
        table_name,
        schema_name=schema_name,
    )


@mcp.tool()
def get_database_schema(
    schema_name: str | None = None,
    include_columns: bool = True,
    max_tables: int = 100,
) -> dict[str, Any]:
    """Get a bounded schema summary for the configured MySQL database."""
    return service.database_schema_tool.get_database_schema(
        schema_name=schema_name,
        include_columns=include_columns,
        max_tables=max_tables,
    )


@mcp.tool()
def build_architecture_analysis(
    repo_name: str,
    target_ref: str = "main",
    module_path: str | None = None,
    work_item_id: int | None = None,
    include_database_schema: bool = True,
) -> dict[str, Any]:
    """Collect architecture evidence for PHP-to-React migration planning."""
    return service.architecture_agent_tool.build_architecture_analysis(
        repo_name=repo_name,
        target_ref=target_ref,
        module_path=module_path,
        work_item_id=work_item_id,
        include_database_schema=include_database_schema,
    )


@mcp.tool()
def list_open_pull_requests(repo_name: str) -> dict[str, Any]:
    """List open pull requests for a repository."""
    return service.pr_review_tool.list_open_pull_requests(repo_name)


@mcp.tool()
def get_pull_request_details(repo_name: str, pr_number: int) -> dict[str, Any]:
    """Get pull request metadata and changed files."""
    return service.pr_review_tool.get_pull_request_details(repo_name, pr_number)


@mcp.tool()
def get_pr_review_context(
    repo_name: str,
    pr_number: int,
    include_database_schema: bool = True,
) -> dict[str, Any]:
    """Collect PR, repo, Azure, and database context for evidence-based review."""
    return service.pr_review_tool.get_pr_review_context(
        repo_name,
        pr_number,
        include_database_schema=include_database_schema,
    )


if __name__ == "__main__":
    logger.info("Starting %s v%s", service.name, service.version)
    mcp.run()
