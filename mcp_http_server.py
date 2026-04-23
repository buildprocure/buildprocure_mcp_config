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