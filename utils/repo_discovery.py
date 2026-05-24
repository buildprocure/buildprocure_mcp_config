"""
Repository Discovery
Auto-discover and manage BuildProcure repositories.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any

from utils.config_manager import ConfigManager
from utils.github_helpers import GitHubHelper

logger = logging.getLogger(__name__)


class RepositoryDiscovery:
    """Handles policy-aware repository discovery and filtering."""

    def __init__(
        self,
        github: GitHubHelper | None = None,
        config: ConfigManager | None = None,
    ) -> None:
        self.github = github or GitHubHelper()
        self.config = config or ConfigManager()
        self.policy = self.config.get_config_value("repo_discovery_policy")
        self.repos: list[dict[str, Any]] = []
        self.all_repos: list[dict[str, Any]] = []
        self._discover_repos()

    def _discover_repos(self) -> None:
        """Discover all repositories visible to the configured GitHub identity."""
        try:
            all_repos = [self.github.normalize_repo(repo) for repo in self.github.get_user_repos()]
            self.all_repos = [repo for repo in all_repos if self._matches_naming_policy(repo)]
            self.repos = self._filter_repos(self.all_repos, include_archived=False)

            logger.info("Total repos: %s, Active repos: %s", len(self.all_repos), len(self.repos))
        except Exception as exc:
            logger.error("Error discovering repositories: %s", exc)
            self.repos = []
            self.all_repos = []

    def _matches_naming_policy(self, repo: dict[str, Any]) -> bool:
        patterns = self.policy.get("naming_patterns") or []
        if not patterns:
            return True

        name = repo.get("name") or ""
        return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)

    def _filter_repos(
        self,
        repos: list[dict[str, Any]],
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        filters = self.policy.get("filters", {})
        exclude_forks = filters.get("exclude_forks", True)
        exclude_archived = filters.get("exclude_archived", True) and not include_archived

        filtered = []
        for repo in repos:
            if exclude_archived and repo.get("archived"):
                continue
            if exclude_forks and repo.get("fork"):
                continue
            filtered.append(repo)
        return filtered

    def get_active_repos(self) -> list[dict[str, Any]]:
        """Get active repositories after policy filters."""
        return list(self.repos)

    def get_all_repos(self, include_archived: bool = True) -> list[dict[str, Any]]:
        """Get discovered repositories, optionally including archived repositories."""
        return self._filter_repos(self.all_repos, include_archived=include_archived)

    def list_repos(self, include_archived: bool = False) -> dict[str, Any]:
        repos = self.get_all_repos(include_archived=include_archived)
        return {
            "repositories": repos,
            "count": len(repos),
            "include_archived": include_archived,
            "policy": {
                "filters": self.policy.get("filters", {}),
                "naming_patterns": self.policy.get("naming_patterns", []),
            },
        }

    def get_repo_info(self, repo_name: str) -> dict[str, Any] | None:
        """Get normalized information about a specific repository."""
        repo = self.github.get_repo_details(repo_name)
        if not repo:
            return None

        normalized = self.github.normalize_repo(repo)
        if not self._matches_naming_policy(normalized):
            return None
        return normalized
