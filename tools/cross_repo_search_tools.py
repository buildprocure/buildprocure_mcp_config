"""
Cross Repository Search Tool
Bounded read-only search across BuildProcure repositories.
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath
from typing import Any

from utils.github_helpers import GitHubHelper
from utils.repo_discovery import RepositoryDiscovery

logger = logging.getLogger(__name__)

SEARCHABLE_EXTENSIONS = {
    ".md",
    ".txt",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".php",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".conf",
    ".css",
    ".scss",
    ".html",
    ".sql",
}

MAX_FILES_PER_REPO = 200
MAX_FILE_CHARS = 80_000
SNIPPET_RADIUS = 120


class CrossRepoSearchTool:
    """Tool for bounded searching across repositories."""

    def __init__(
        self,
        github: GitHubHelper | None = None,
        discovery: RepositoryDiscovery | None = None,
    ) -> None:
        self.github = github or GitHubHelper()
        self.discovery = discovery or RepositoryDiscovery(github=self.github)

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "search_across_repos",
                "description": "Search across policy-matching repositories and return bounded snippets",
            }
        ]

    def search_across_repos(
        self,
        query: str,
        include_archived: bool = False,
        max_results: int = 50,
    ) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            return {"ok": False, "query": query, "error": "query is required", "results": []}

        max_results = max(1, min(max_results, 100))
        repos = self.discovery.get_all_repos(include_archived=include_archived)
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for repo in repos:
            if len(results) >= max_results:
                break

            repo_name = repo["name"]
            target_ref = repo.get("default_branch") or "main"
            tree_result = self.github.get_repo_tree_safe(repo_name, ref=target_ref)
            if not tree_result.get("ok"):
                errors.append(tree_result)
                continue

            candidate_paths = self._candidate_paths(tree_result.get("tree", []), query)
            for path in candidate_paths[:MAX_FILES_PER_REPO]:
                if len(results) >= max_results:
                    break
                file_result = self.github.get_repo_file_safe(repo_name, path, ref=target_ref)
                if not file_result.get("ok"):
                    continue

                file_data = file_result["file"]
                content = (file_data.get("content") or "")[:MAX_FILE_CHARS]
                match = self._match(query, path, content)
                if match:
                    results.append(
                        {
                            "repo_name": repo_name,
                            "path": path,
                            "target_ref": target_ref,
                            "url": file_data.get("html_url"),
                            "match_type": match["match_type"],
                            "snippet": match["snippet"],
                        }
                    )

        return {
            "ok": True,
            "query": query,
            "include_archived": include_archived,
            "max_results": max_results,
            "result_count": len(results),
            "truncated": len(results) >= max_results,
            "results": results,
            "errors": errors,
        }

    def _candidate_paths(self, tree: list[str], query: str) -> list[str]:
        query_lower = query.lower()
        path_matches = [path for path in tree if query_lower in path.lower()]
        content_candidates = [
            path
            for path in tree
            if self._is_searchable(path) and path not in path_matches
        ]
        return path_matches + content_candidates

    def _is_searchable(self, path: str) -> bool:
        suffix = PurePosixPath(path).suffix.lower()
        name = PurePosixPath(path).name.lower()
        return suffix in SEARCHABLE_EXTENSIONS or name in {"dockerfile", ".env.example"}

    def _match(self, query: str, path: str, content: str) -> dict[str, str] | None:
        query_lower = query.lower()
        if query_lower in path.lower():
            return {"match_type": "path", "snippet": path}

        content_lower = content.lower()
        index = content_lower.find(query_lower)
        if index == -1:
            return None

        start = max(0, index - SNIPPET_RADIUS)
        end = min(len(content), index + len(query) + SNIPPET_RADIUS)
        snippet = content[start:end].replace("\r", "").strip()
        return {"match_type": "content", "snippet": snippet}
