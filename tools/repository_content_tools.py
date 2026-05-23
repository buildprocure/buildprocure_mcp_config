"""
Repository Content Tools
Safe read-only access to repository trees and files.
"""

from __future__ import annotations

from typing import Any

from utils.github_helpers import GitHubHelper

MAX_FILE_CONTENT_CHARS = 50_000
MAX_BATCH_FILES = 50


class RepositoryContentTool:
    """Read repository tree and file contents with normalized responses."""

    def __init__(self, github: GitHubHelper | None = None) -> None:
        self.github = github or GitHubHelper()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "get_repo_tree",
                "description": "Get a repository file tree for a branch, tag, or commit ref",
            },
            {
                "name": "get_repo_file",
                "description": "Get one repository file by path and ref",
            },
            {
                "name": "get_repo_files_batch",
                "description": "Get multiple repository files by path and ref",
            },
        ]

    def get_repo_tree(self, repo_name: str, target_ref: str = "main") -> dict[str, Any]:
        return self.github.get_repo_tree_safe(repo_name, ref=target_ref)

    def get_repo_file(self, repo_name: str, path: str, target_ref: str = "main") -> dict[str, Any]:
        result = self.github.get_repo_file_safe(repo_name, path, ref=target_ref)
        if result.get("ok"):
            result["file"] = self._trim_file(result["file"])
        return result

    def get_repo_files_batch(
        self,
        repo_name: str,
        paths: list[str],
        target_ref: str = "main",
    ) -> dict[str, Any]:
        result = self.github.get_repo_files_batch_safe(
            repo_name,
            paths,
            ref=target_ref,
            max_files=MAX_BATCH_FILES,
        )
        result["files"] = [self._trim_file(file_data) for file_data in result.get("files", [])]
        return result

    def _trim_file(self, file_data: dict[str, Any]) -> dict[str, Any]:
        content = file_data.get("content", "")
        trimmed = len(content) > MAX_FILE_CONTENT_CHARS
        return {
            **file_data,
            "content": content[:MAX_FILE_CONTENT_CHARS],
            "content_truncated": trimmed,
        }
