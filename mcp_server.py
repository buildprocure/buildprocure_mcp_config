#!/usr/bin/env python3
"""
BuildProcure MCP Server
Main entry point for the Model Context Protocol server
"""

import logging
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from tools.unified_workspace_tools import UnifiedWorkspaceTool
from tools.cross_repo_search_tools import CrossRepoSearchTool
from tools.dependency_analyzer_tools import DependencyAnalyzerTool
from utils.config_manager import ConfigManager

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

mcp = FastMCP("buildprocure-mcp")


class BuildProcureService:
    def __init__(self):
        self.name = "buildprocure-mcp"
        self.version = "1.0.0"
        self.config = ConfigManager()

        self.workspace_tool = UnifiedWorkspaceTool()
        self.search_tool = CrossRepoSearchTool()
        self.dep_tool = DependencyAnalyzerTool()

        logger.info("Initializing MCP tools...")
        logger.info(f"Loaded {len(self.workspace_tool.get_tools())} workspace tools")
        logger.info(f"Loaded {len(self.search_tool.get_tools())} search tools")
        logger.info(f"Loaded {len(self.dep_tool.get_tools())} dependency tools")


service = BuildProcureService()


@mcp.tool()
def list_all_repos() -> dict:
    """List all active BuildProcure repositories."""
    return service.workspace_tool.list_all_repos()


@mcp.tool()
def get_repo_info(repo_name: str) -> dict:
    """Get detailed information about a BuildProcure repository."""
    return service.workspace_tool.get_repo_info(repo_name)

@mcp.tool()
def search_across_repos(query: str) -> dict:
    """Search for patterns across all BuildProcure repositories."""
    return service.search_tool.search_across_repos(query)

@mcp.tool()
def analyze_dependencies(repo_name: str) -> dict:
    """Analyze dependencies for a BuildProcure repository."""
    return service.dep_tool.analyze_dependencies(repo_name)

if __name__ == "__main__":
    logger.info(f"Starting {service.name} v{service.version}")
    mcp.run()