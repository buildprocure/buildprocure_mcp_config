from __future__ import annotations

import logging
from typing import Any

from tools.agent_context_tools import AgentContextTool
from tools.database_schema_tools import DatabaseSchemaTool
from utils.azure_devops_helper import AzureDevOpsHelper
from utils.github_helpers import GitHubHelper
from utils.pr_review_helpers import PRReviewHelper

logger = logging.getLogger(__name__)


class PRReviewTool:
    """Collect evidence for senior PR review without generating the review itself."""

    def __init__(
        self,
        github: GitHubHelper | None = None,
        helper: PRReviewHelper | None = None,
        azure: AzureDevOpsHelper | None = None,
        agent_context_tool: AgentContextTool | None = None,
        database_schema_tool: DatabaseSchemaTool | None = None,
    ) -> None:
        self.github = github or GitHubHelper()
        self.helper = helper or PRReviewHelper()
        self.azure = azure or AzureDevOpsHelper()
        self.agent_context_tool = agent_context_tool or AgentContextTool(github=self.github)
        self.database_schema_tool = database_schema_tool or DatabaseSchemaTool()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "list_open_pull_requests",
                "description": "List open pull requests for a repository",
            },
            {
                "name": "get_pull_request_details",
                "description": "Get pull request metadata and changed files",
            },
            {
                "name": "get_pr_review_context",
                "description": "Collect PR, repo, Azure, and database context for evidence-based review",
            },
        ]

    def list_open_pull_requests(self, repo_name: str) -> dict[str, Any]:
        try:
            prs = self.github.list_open_pull_requests(repo_name)
        except Exception as exc:
            logger.warning("Failed to list PRs for %s: %s", repo_name, exc)
            return {"ok": False, "repo_name": repo_name, "error": str(exc), "pull_requests": []}

        return {
            "ok": True,
            "repo_name": repo_name,
            "count": len(prs),
            "pull_requests": [self.helper.summarize_pull_request(pr) for pr in prs],
        }

    def get_pull_request_details(self, repo_name: str, pr_number: int) -> dict[str, Any]:
        try:
            pr = self.github.get_pull_request(repo_name, pr_number)
            files = self.github.get_pull_request_files(repo_name, pr_number)
        except Exception as exc:
            logger.warning("Failed to fetch %s PR #%s: %s", repo_name, pr_number, exc)
            return {
                "ok": False,
                "repo_name": repo_name,
                "pr_number": pr_number,
                "error": str(exc),
            }

        return {
            "ok": True,
            "repo_name": repo_name,
            "pull_request": self.helper.summarize_pull_request(pr),
            "changed_files": self.helper.summarize_changed_files(files),
        }

    def get_pr_review_context(
        self,
        repo_name: str,
        pr_number: int,
        include_database_schema: bool = True,
    ) -> dict[str, Any]:
        """
        Returns review evidence only.
        The AI client should use this context to generate the final reviewer response.
        """
        try:
            pr = self.github.get_pull_request(repo_name, pr_number)
            files = self.github.get_pull_request_files(repo_name, pr_number)
            diff_text = self.github.get_pull_request_diff(repo_name, pr_number)
        except Exception as exc:
            logger.warning("Failed to build PR review context for %s PR #%s: %s", repo_name, pr_number, exc)
            return {
                "ok": False,
                "repo_name": repo_name,
                "pr_number": pr_number,
                "error": str(exc),
            }

        pr_type = self.helper.detect_pr_type(files)
        pr_context = self.helper.summarize_pr_context(pr, files, diff_text)

        base_branch = pr.get("base", {}).get("ref") or "main"
        changed_file_names = [f.get("filename", "") for f in files]

        repo_tree_result = self.github.get_repo_tree_safe(repo_name, ref=base_branch)
        repo_tree = repo_tree_result.get("tree", [])
        context_file_paths = self.helper.select_context_files(repo_tree, changed_file_names)

        agent_context = self.agent_context_tool.build_agent_context(
            repo_name,
            target_ref=base_branch,
            paths=context_file_paths,
        )

        azure_lookup_text = self.helper.build_lookup_text(pr, files)
        azure_context = self._get_azure_context(azure_lookup_text)
        database_context = self._get_database_context(azure_lookup_text, include_database_schema)

        logger.info(
            "Prepared PR review context for %s PR #%s with %s context files",
            repo_name,
            pr_number,
            len(agent_context.get("selected_files", [])),
        )

        return {
            "ok": True,
            "review_mode": "senior_software_engineer",
            "important_instruction": (
                "Use this as evidence for an intelligent PR review. "
                "Do not make generic comments. Base every finding on the diff, repository context, "
                "Azure context, or database schema context."
            ),
            "review_instructions": self.helper.build_review_instructions(pr_type["type"]),
            "repo_name": repo_name,
            "pr_number": pr_number,
            "pr_type": pr_type,
            "pull_request": pr_context,
            "repository_context": {
                "base_branch": base_branch,
                "repo_file_count": len(repo_tree),
                "tree_error": repo_tree_result.get("error"),
                "selected_context_files": agent_context.get("selected_paths", []),
                "files": {
                    file_data.get("path"): {
                        "path": file_data.get("path"),
                        "html_url": file_data.get("html_url"),
                        "content": self.helper.trim_file_content(file_data.get("content", "")),
                        "content_truncated": file_data.get("content_truncated", False),
                    }
                    for file_data in agent_context.get("selected_files", [])
                },
                "manifest_summary": agent_context.get("manifest_summary", {}),
                "config_summary": agent_context.get("config_summary", {}),
                "file_errors": agent_context.get("file_errors", []),
            },
            "azure_devops_context": azure_context,
            "database_schema_context": database_context,
            "expected_review_output_format": self.helper.expected_review_output_format(),
        }

    def _get_azure_context(self, lookup_text: str) -> dict[str, Any]:
        try:
            return self.azure.get_context_for_text(lookup_text)
        except Exception as exc:
            logger.warning("Failed to fetch Azure context: %s", exc)
            return {
                "work_item_ids": self.azure.extract_work_item_ids(lookup_text),
                "work_items": [],
                "wiki_pages": [],
                "error": str(exc),
            }

    def _get_database_context(self, lookup_text: str, include_database_schema: bool) -> dict[str, Any]:
        if not include_database_schema:
            return {"enabled": False}

        tables_result = self.database_schema_tool.list_database_tables()
        if not tables_result.get("ok"):
            return {
                "enabled": True,
                "ok": False,
                "error": tables_result.get("error"),
                "tables": [],
                "matched_tables": [],
            }

        tables = tables_result.get("tables", [])
        matched_table_names = self.helper.match_database_tables(lookup_text, tables)
        matched_tables = []
        for table_name in matched_table_names[:10]:
            matched_tables.append(self.database_schema_tool.describe_database_table(table_name))

        return {
            "enabled": True,
            "ok": True,
            "schema_name": tables_result.get("schema_name"),
            "table_count": len(tables),
            "tables": tables[:100],
            "matched_table_names": matched_table_names,
            "matched_tables": matched_tables,
        }
