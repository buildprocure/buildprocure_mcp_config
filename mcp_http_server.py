#!/usr/bin/env python3
"""
BuildProcure MCP HTTP Server
Streamable HTTP entry point for reusable basic MCP tools.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from tools.agent_context_tools import AgentContextTool
from tools.architecture_agent_tools import ArchitectureAgentTool
from tools.backend_api_bridge_tools import BackendAPIBridgeTool
from tools.config_tools import ConfigTool
from tools.cross_repo_search_tools import CrossRepoSearchTool
from tools.database_model_context_tools import DatabaseModelContextTool
from tools.database_schema_tools import DatabaseSchemaTool
from tools.dependency_analyzer_tools import DependencyAnalyzerTool
from tools.legacy_php_analysis_tools import LegacyPHPAnalysisTool
from tools.migration_spec_tools import MigrationSpecTool
from tools.migration_orchestrator_tools import MigrationOrchestratorTool
from tools.pr_review_tools import PRReviewTool
from tools.react_code_writer_tools import ReactCodeWriterTool
from tools.react_conversion_tools import ReactConversionTool
from tools.repository_content_tools import RepositoryContentTool
from tools.unified_workspace_tools import UnifiedWorkspaceTool
from utils.config_manager import ConfigManager
from utils.github_helpers import GitHubHelper
from utils.llm_review_provider import LLMReviewProvider
from utils.repo_discovery import RepositoryDiscovery

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BuildProcureService:
    def __init__(self) -> None:
        self.name = os.getenv("MCP_SERVER_NAME", "buildprocure-mcp")
        self.version = os.getenv("MCP_SERVER_VERSION", "1.0.0")
        self.config = ConfigManager()
        self.github = GitHubHelper()
        self.discovery = RepositoryDiscovery(github=self.github, config=self.config)
        self.review_provider = LLMReviewProvider()

        logger.info("Initializing basic MCP tools...")

        self.workspace_tool = UnifiedWorkspaceTool(discovery=self.discovery)
        self.content_tool = RepositoryContentTool(github=self.github)
        self.search_tool = CrossRepoSearchTool(github=self.github, discovery=self.discovery)
        self.dep_tool = DependencyAnalyzerTool(github=self.github)
        self.config_tool = ConfigTool(config=self.config)
        self.database_schema_tool = DatabaseSchemaTool()
        self.database_model_context_tool = DatabaseModelContextTool(database_schema_tool=self.database_schema_tool)
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
        self.legacy_php_analysis_tool = LegacyPHPAnalysisTool(
            github=self.github,
            content_tool=self.content_tool,
            database_schema_tool=self.database_schema_tool,
        )
        self.migration_spec_tool = MigrationSpecTool(
            architecture_agent_tool=self.architecture_agent_tool,
            legacy_php_analysis_tool=self.legacy_php_analysis_tool,
            database_model_context_tool=self.database_model_context_tool,
        )
        self.react_conversion_tool = ReactConversionTool(migration_spec_tool=self.migration_spec_tool)
        self.react_code_writer_tool = ReactCodeWriterTool(
            github=self.github,
            react_conversion_tool=self.react_conversion_tool,
        )
        self.migration_orchestrator_tool = MigrationOrchestratorTool(
            react_code_writer_tool=self.react_code_writer_tool,
        )
        self.backend_api_bridge_tool = BackendAPIBridgeTool(migration_spec_tool=self.migration_spec_tool)
        self.pr_review_tool = PRReviewTool(
            github=self.github,
            agent_context_tool=self.agent_context_tool,
            database_schema_tool=self.database_schema_tool,
        )

        for tool_group in [
            self.workspace_tool,
            self.content_tool,
            self.search_tool,
            self.dep_tool,
            self.config_tool,
            self.database_schema_tool,
            self.database_model_context_tool,
            self.agent_context_tool,
            self.architecture_agent_tool,
            self.legacy_php_analysis_tool,
            self.migration_spec_tool,
            self.react_conversion_tool,
            self.react_code_writer_tool,
            self.migration_orchestrator_tool,
            self.backend_api_bridge_tool,
            self.pr_review_tool,
        ]:
            logger.info("Loaded %s tools from %s", len(tool_group.get_tools()), tool_group.__class__.__name__)


service = BuildProcureService()
mcp = FastMCP(service.name)


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
def build_database_model_context(
    schema_name: str | None = None,
    table_names: list[str] | None = None,
    focus_terms: list[str] | None = None,
    include_relationships: bool = True,
    max_tables: int = 40,
) -> dict[str, Any]:
    """Build read-only database model context for migration planning."""
    return service.database_model_context_tool.build_database_model_context(
        schema_name=schema_name,
        table_names=table_names,
        focus_terms=focus_terms,
        include_relationships=include_relationships,
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
def analyze_legacy_php_module(
    repo_name: str,
    target_ref: str = "main",
    module_path: str | None = None,
    related_paths: list[str] | None = None,
    focus_terms: list[str] | None = None,
    include_database_schema: bool = True,
) -> dict[str, Any]:
    """Analyze a focused legacy PHP module before PHP-to-React migration."""
    return service.legacy_php_analysis_tool.analyze_legacy_php_module(
        repo_name=repo_name,
        target_ref=target_ref,
        module_path=module_path,
        related_paths=related_paths,
        focus_terms=focus_terms,
        include_database_schema=include_database_schema,
    )


@mcp.tool()
def build_migration_spec(
    repo_name: str,
    module_name: str,
    target_ref: str = "main",
    module_path: str | None = None,
    related_paths: list[str] | None = None,
    focus_terms: list[str] | None = None,
    table_names: list[str] | None = None,
    schema_name: str | None = None,
    work_item_id: int | None = None,
    include_database_schema: bool = True,
) -> dict[str, Any]:
    """Build a structured PHP-to-React migration spec for one module slice."""
    return service.migration_spec_tool.build_migration_spec(
        repo_name=repo_name,
        module_name=module_name,
        target_ref=target_ref,
        module_path=module_path,
        related_paths=related_paths,
        focus_terms=focus_terms,
        table_names=table_names,
        schema_name=schema_name,
        work_item_id=work_item_id,
        include_database_schema=include_database_schema,
    )


@mcp.tool()
def build_react_conversion_plan(
    repo_name: str,
    module_name: str,
    target_ref: str = "main",
    module_path: str | None = None,
    related_paths: list[str] | None = None,
    focus_terms: list[str] | None = None,
    table_names: list[str] | None = None,
    schema_name: str | None = None,
    work_item_id: int | None = None,
    react_app_root: str = "frontend/src",
    include_database_schema: bool = True,
) -> dict[str, Any]:
    """Build a React implementation blueprint from a migration spec."""
    return service.react_conversion_tool.build_react_conversion_plan(
        repo_name=repo_name,
        module_name=module_name,
        target_ref=target_ref,
        module_path=module_path,
        related_paths=related_paths,
        focus_terms=focus_terms,
        table_names=table_names,
        schema_name=schema_name,
        work_item_id=work_item_id,
        react_app_root=react_app_root,
        include_database_schema=include_database_schema,
    )


@mcp.tool()
def write_react_conversion_files(
    source_repo_name: str,
    target_repo_name: str,
    module_name: str,
    target_ref: str = "main",
    module_path: str | None = None,
    related_paths: list[str] | None = None,
    focus_terms: list[str] | None = None,
    table_names: list[str] | None = None,
    schema_name: str | None = None,
    work_item_id: int | None = None,
    react_app_root: str = "src",
    target_branch: str | None = None,
    base_branch: str = "main",
    dry_run: bool = True,
    overwrite: bool = False,
    create_pull_request: bool = True,
) -> dict[str, Any]:
    """Generate React migration files for local application; remote GitHub writes are disabled."""
    return service.react_code_writer_tool.write_react_conversion_files(
        source_repo_name=source_repo_name,
        target_repo_name=target_repo_name,
        module_name=module_name,
        target_ref=target_ref,
        module_path=module_path,
        related_paths=related_paths,
        focus_terms=focus_terms,
        table_names=table_names,
        schema_name=schema_name,
        work_item_id=work_item_id,
        react_app_root=react_app_root,
        target_branch=target_branch,
        base_branch=base_branch,
        dry_run=dry_run,
        overwrite=overwrite,
        create_pull_request=create_pull_request,
    )


@mcp.tool()
def run_migration_request(
    request_text: str,
    source_repo_name: str,
    target_repo_name: str,
    target_ref: str = "main",
    module_name: str | None = None,
    module_path: str | None = None,
    related_paths: list[str] | None = None,
    focus_terms: list[str] | None = None,
    table_names: list[str] | None = None,
    schema_name: str | None = None,
    work_item_id: int | None = None,
    react_app_root: str = "src",
    target_branch: str | None = None,
    base_branch: str = "main",
    dry_run: bool = True,
    overwrite: bool = False,
    create_pull_request: bool = True,
) -> dict[str, Any]:
    """Run a natural-language PHP-to-React migration request through the agent chain."""
    return service.migration_orchestrator_tool.run_migration_request(
        request_text=request_text,
        source_repo_name=source_repo_name,
        target_repo_name=target_repo_name,
        target_ref=target_ref,
        module_name=module_name,
        module_path=module_path,
        related_paths=related_paths,
        focus_terms=focus_terms,
        table_names=table_names,
        schema_name=schema_name,
        work_item_id=work_item_id,
        react_app_root=react_app_root,
        target_branch=target_branch,
        base_branch=base_branch,
        dry_run=dry_run,
        overwrite=overwrite,
        create_pull_request=create_pull_request,
    )


@mcp.tool()
def generate_backend_api_bridge_files(
    repo_name: str,
    module_name: str,
    target_ref: str = "main",
    module_path: str | None = None,
    related_paths: list[str] | None = None,
    focus_terms: list[str] | None = None,
    table_names: list[str] | None = None,
    schema_name: str | None = None,
    work_item_id: int | None = None,
    api_root: str = "api",
    include_database_schema: bool = True,
) -> dict[str, Any]:
    """Generate local PHP API bridge files for a PHP-to-React migration slice."""
    return service.backend_api_bridge_tool.generate_backend_api_bridge_files(
        repo_name=repo_name,
        module_name=module_name,
        target_ref=target_ref,
        module_path=module_path,
        related_paths=related_paths,
        focus_terms=focus_terms,
        table_names=table_names,
        schema_name=schema_name,
        work_item_id=work_item_id,
        api_root=api_root,
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


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": service.name,
            "version": service.version,
            "tooling": "basic-foundation",
        }
    )


@mcp.custom_route("/agent-review", methods=["POST"])
async def agent_review_endpoint(request: Request) -> JSONResponse:
    started_at = time.time()
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400)

    repo_name = payload.get("repo_name")
    pr_number = payload.get("pr_number")
    include_database_schema = payload.get("include_database_schema", True)

    if not repo_name or pr_number is None:
        return JSONResponse(
            {"ok": False, "error": "repo_name and pr_number are required"},
            status_code=400,
        )

    try:
        pr_number = int(pr_number)
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "pr_number must be an integer"}, status_code=400)

    context = service.pr_review_tool.get_pr_review_context(
        repo_name=str(repo_name),
        pr_number=pr_number,
        include_database_schema=bool(include_database_schema),
    )
    if not context.get("ok"):
        return JSONResponse(
            {
                "ok": False,
                "repo_name": repo_name,
                "pr_number": pr_number,
                "error": context.get("error", "Unable to collect PR review context"),
                "context": context,
            },
            status_code=502,
        )

    try:
        review = service.review_provider.generate_pr_review(context)
    except Exception as exc:
        logger.exception("Agent review generation failed")
        return JSONResponse(
            {
                "ok": False,
                "repo_name": repo_name,
                "pr_number": pr_number,
                "error": str(exc),
                "context_used": _summarize_context_used(context),
            },
            status_code=502,
        )

    return JSONResponse(
        {
            "ok": True,
            "repo_name": repo_name,
            "pr_number": pr_number,
            "provider": review["provider"],
            "model": review["model"],
            "review_markdown": review["review_markdown"],
            "context_used": _summarize_context_used(context),
            "elapsed_seconds": round(time.time() - started_at, 2),
        }
    )


def _summarize_context_used(context: dict[str, Any]) -> dict[str, Any]:
    repository_context = context.get("repository_context", {})
    azure_context = context.get("azure_devops_context", {})
    database_context = context.get("database_schema_context", {})
    return {
        "selected_context_files": repository_context.get("selected_context_files", []),
        "azure_work_item_ids": azure_context.get("work_item_ids", []),
        "azure_wiki_page_count": len(azure_context.get("wiki_pages", [])),
        "database_schema_enabled": database_context.get("enabled", False),
        "database_matched_table_names": database_context.get("matched_table_names", []),
    }


if __name__ == "__main__":
    logger.info("Starting %s v%s", service.name, service.version)
    mcp.run(transport="streamable-http")
