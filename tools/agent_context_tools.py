"""
Agent Context Tools
Generic reusable context bundles for future agents.
"""

from __future__ import annotations

from typing import Any

from tools.dependency_analyzer_tools import DependencyAnalyzerTool
from tools.repository_content_tools import RepositoryContentTool
from utils.config_manager import ConfigManager
from utils.github_helpers import GitHubHelper

DEFAULT_CONTEXT_FILES = {
    "README.md",
    "README.txt",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "composer.json",
    "Dockerfile",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
    "azure-pipelines.yml",
    "azure-pipelines.yaml",
}
MAX_SELECTED_FILES = 40


class AgentContextTool:
    """Build generic repository context without agent-specific assumptions."""

    def __init__(
        self,
        github: GitHubHelper | None = None,
        config: ConfigManager | None = None,
        content_tool: RepositoryContentTool | None = None,
        dependency_tool: DependencyAnalyzerTool | None = None,
    ) -> None:
        self.github = github or GitHubHelper()
        self.config = config or ConfigManager()
        self.content_tool = content_tool or RepositoryContentTool(github=self.github)
        self.dependency_tool = dependency_tool or DependencyAnalyzerTool(github=self.github)

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "build_agent_context",
                "description": "Build generic reusable repository context for future agents",
            }
        ]

    def build_agent_context(
        self,
        repo_name: str,
        target_ref: str = "main",
        paths: list[str] | None = None,
    ) -> dict[str, Any]:
        repo_result = self.github.get_repo_details_safe(repo_name)
        tree_result = self.content_tool.get_repo_tree(repo_name, target_ref=target_ref)
        manifest_summary = self.dependency_tool.get_repo_manifest_summary(repo_name, target_ref=target_ref)

        selected_paths = paths or self._select_default_paths(tree_result.get("tree", []), manifest_summary)
        files_result = self.content_tool.get_repo_files_batch(
            repo_name,
            selected_paths,
            target_ref=target_ref,
        )

        return {
            "ok": bool(repo_result.get("ok") and tree_result.get("ok")),
            "repo_name": repo_name,
            "target_ref": target_ref,
            "repository": repo_result.get("repository"),
            "tree": {
                "file_count": tree_result.get("file_count", 0),
                "files": tree_result.get("tree", []),
                "error": tree_result.get("error"),
            },
            "selected_paths": selected_paths,
            "selected_files": files_result.get("files", []),
            "file_errors": files_result.get("errors", []),
            "manifest_summary": manifest_summary,
            "config_summary": {
                "available_configs": self.config.list_available_configs(),
                "configs": self.config.configs,
            },
            "errors": [
                item
                for item in [repo_result if not repo_result.get("ok") else None, tree_result if not tree_result.get("ok") else None]
                if item
            ],
        }

    def _select_default_paths(
        self,
        tree: list[str],
        manifest_summary: dict[str, Any],
    ) -> list[str]:
        selected = []
        tree_set = set(tree)

        for path in tree:
            if path in DEFAULT_CONTEXT_FILES or path.startswith(".github/workflows/"):
                selected.append(path)

        for path in manifest_summary.get("manifest_paths", []):
            if path in tree_set:
                selected.append(path)

        return list(dict.fromkeys(selected))[:MAX_SELECTED_FILES]
