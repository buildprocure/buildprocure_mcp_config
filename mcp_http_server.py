#!/usr/bin/env python3
"""
BuildProcure MCP HTTP Server

Runs the MCP server over Streamable HTTP for remote use behind Apache.
Designed for container deployment where Apache proxies:
- /health -> this app
- /mcp    -> MCP endpoint
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from tools.unified_workspace_tools import UnifiedWorkspaceTool
from tools.cross_repo_search_tools import CrossRepoSearchTool
from tools.dependency_analyzer_tools import DependencyAnalyzerTool
from utils.config_manager import ConfigManager
from tools.pr_review_tools import PRReviewTool

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BuildProcureService:
    def __init__(self) -> None:
        self.name = "buildprocure-mcp"
        self.version = "1.0.0"
        self.config = ConfigManager()

        logger.info("Initializing MCP tools...")

        self.workspace_tool = UnifiedWorkspaceTool()
        self.search_tool = CrossRepoSearchTool()
        self.dep_tool = DependencyAnalyzerTool()

        self.pr_review_tool = PRReviewTool()
        logger.info("Loaded %s PR review tools", len(self.pr_review_tool.get_tools()))

        logger.info(
            "Loaded %s workspace tools",
            len(self.workspace_tool.get_tools()),
        )
        logger.info(
            "Loaded %s search tools",
            len(self.search_tool.get_tools()),
        )
        logger.info(
            "Loaded %s dependency tools",
            len(self.dep_tool.get_tools()),
        )


service = BuildProcureService()
mcp = FastMCP(service.name)


@mcp.tool()
def list_all_repos() -> dict[str, Any]:
    """List all active BuildProcure repositories."""
    return service.workspace_tool.list_all_repos()


@mcp.tool()
def get_repo_info(repo_name: str) -> dict[str, Any]:
    """Get detailed information about a BuildProcure repository."""
    return service.workspace_tool.get_repo_info(repo_name)


# Add these only if the methods already exist in your tool classes.
# If the method names differ, adjust them to match your files.

@mcp.tool()
def search_across_repos(query: str) -> dict[str, Any]:
    """Search across BuildProcure repositories for a query or pattern."""
    return service.search_tool.search_across_repos(query)


@mcp.tool()
def analyze_dependencies(repo_name: str) -> dict[str, Any]:
    """Analyze dependencies for a specific BuildProcure repository."""
    return service.dep_tool.analyze_dependencies(repo_name)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request) -> tuple[dict[str, Any], int]:
    """Simple health check endpoint for Apache/container probes."""
    return {
        "status": "ok",
        "service": service.name,
        "version": service.version,
    }, 200

# Add PR review tools as MCP endpoints
@mcp.tool()
def list_open_pull_requests(repo_name: str) -> dict:
    """List open pull requests for a repository."""
    return service.pr_review_tool.list_open_pull_requests(repo_name)


@mcp.tool()
def get_pull_request_details(repo_name: str, pr_number: int) -> dict:
    """Get pull request metadata, changed files, and summary context."""
    return service.pr_review_tool.get_pull_request_details(repo_name, pr_number)


@mcp.tool()
def get_pr_review_context(repo_name: str, pr_number: int) -> dict:
    """Collect PR diff and repository context for senior software engineer review.."""
    return service.pr_review_tool.get_pr_review_context(repo_name, pr_number)

if __name__ == "__main__":
    logger.info("Starting %s v%s", service.name, service.version)
    mcp.run(transport="streamable-http")

# if __name__ == "__main__":
#     host = os.getenv("MCP_HOST", "127.0.0.1")
#     port = int(os.getenv("MCP_PORT", "8000"))

#     logger.info("Starting %s v%s on %s:%s", service.name, service.version, host, port)

#     # Official SDK supports streamable-http transport for remote MCP servers.
#     mcp.run(
#         transport="streamable-http",
#         host=host,
#         port=port,
#         path="/mcp",
#     )