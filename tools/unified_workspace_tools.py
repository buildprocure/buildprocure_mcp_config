"""
Unified Workspace Tool
Lists and describes BuildProcure repositories.
"""

from __future__ import annotations

import logging
from typing import Any

from utils.github_helpers import GitHubHelper
from utils.repo_discovery import RepositoryDiscovery

logger = logging.getLogger(__name__)


class UnifiedWorkspaceTool:
    """Tool for unified read-only workspace operations."""

    def __init__(self, discovery: RepositoryDiscovery | None = None) -> None:
        self.github = GitHubHelper()
        self.discovery = discovery or RepositoryDiscovery(github=self.github)

    def get_tools(self) -> list[dict[str, Any]]:
        """Return tool metadata."""
        return [
            {
                "name": "list_all_repos",
                "description": "List BuildProcure repositories that match discovery policy",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "include_archived": {
                            "type": "boolean",
                            "description": "Include archived repositories",
                            "default": False,
                        }
                    },
                },
            },
            {
                "name": "get_repo_info",
                "description": "Get normalized information about a repository",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name without owner",
                        }
                    },
                    "required": ["repo_name"],
                },
            },
        ]

    def list_all_repos(self, include_archived: bool = False) -> dict[str, Any]:
        """List policy-matching repositories."""
        result = self.discovery.list_repos(include_archived=include_archived)
        logger.info("Listed %s repositories", result.get("count", 0))
        return result

    def get_repo_info(self, repo_name: str) -> dict[str, Any]:
        """Get information about a specific repository."""
        repo = self.discovery.get_repo_info(repo_name)
        if not repo:
            logger.warning("Repository %s not found", repo_name)
            return {
                "ok": False,
                "repo_name": repo_name,
                "error": f"Repository not found or excluded by policy: {repo_name}",
            }

        logger.info("Retrieved info for %s", repo_name)
        return {"ok": True, "repository": repo}
