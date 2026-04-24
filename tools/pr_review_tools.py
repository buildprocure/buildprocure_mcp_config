from __future__ import annotations

import logging
from typing import Any

from utils.github_helpers import GitHubHelper
from utils.pr_review_helpers import PRReviewHelper

logger = logging.getLogger(__name__)


class PRReviewTool:
    def __init__(self):
        self.github = GitHubHelper()
        self.helper = PRReviewHelper()

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
                "description": "Collect PR diff and repository context for senior engineer review",
            },
        ]

    def list_open_pull_requests(self, repo_name: str) -> dict[str, Any]:
        prs = self.github.list_open_pull_requests(repo_name)

        return {
            "repo_name": repo_name,
            "count": len(prs),
            "pull_requests": [
                {
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "author": pr.get("user", {}).get("login"),
                    "state": pr.get("state"),
                    "url": pr.get("html_url"),
                    "created_at": pr.get("created_at"),
                    "updated_at": pr.get("updated_at"),
                }
                for pr in prs
            ],
        }

    def get_pull_request_details(self, repo_name: str, pr_number: int) -> dict[str, Any]:
        pr = self.github.get_pull_request(repo_name, pr_number)
        files = self.github.get_pull_request_files(repo_name, pr_number)

        return {
            "repo_name": repo_name,
            "pull_request": {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "body": pr.get("body"),
                "author": pr.get("user", {}).get("login"),
                "state": pr.get("state"),
                "url": pr.get("html_url"),
                "base_branch": pr.get("base", {}).get("ref"),
                "head_branch": pr.get("head", {}).get("ref"),
            },
            "changed_files": [
                {
                    "filename": f.get("filename"),
                    "status": f.get("status"),
                    "additions": f.get("additions"),
                    "deletions": f.get("deletions"),
                    "changes": f.get("changes"),
                }
                for f in files
            ],
        }

    def get_pr_review_context(self, repo_name: str, pr_number: int) -> dict[str, Any]:
        """
        Returns evidence/context only.
        The AI client should use this context to generate the actual senior-engineer review.
        """

        pr = self.github.get_pull_request(repo_name, pr_number)
        files = self.github.get_pull_request_files(repo_name, pr_number)
        diff_text = self.github.get_pull_request_diff(repo_name, pr_number)

        pr_type = self.helper.detect_pr_type(files)
        pr_context = self.helper.summarize_pr_context(pr, files, diff_text)

        base_branch = pr.get("base", {}).get("ref") or "main"
        changed_file_names = [f.get("filename", "") for f in files]

        repo_tree = self.github.get_repo_tree(repo_name, ref=base_branch)
        context_file_paths = self.helper.select_context_files(repo_tree, changed_file_names)

        context_files: dict[str, Any] = {}
        for path in context_file_paths:
            file_data = self.github.get_repo_file(repo_name, path, ref=base_branch)

            if not file_data or not file_data.get("exists"):
                continue

            context_files[path] = {
                "path": path,
                "html_url": file_data.get("html_url"),
                "content": self.helper.trim_file_content(file_data.get("content", "")),
            }

        logger.info(
            "Prepared PR review context for %s PR #%s with %s context files",
            repo_name,
            pr_number,
            len(context_files),
        )

        return {
            "review_mode": "senior_software_engineer",
            "important_instruction": (
                "Use this as evidence for an intelligent PR review. "
                "Do not make generic comments. Base every finding on the diff or repository context."
            ),
            "review_instructions": self.helper.build_review_instructions(pr_type["type"]),
            "repo_name": repo_name,
            "pr_number": pr_number,
            "pr_type": pr_type,
            "pull_request": pr_context,
            "repository_context": {
                "base_branch": base_branch,
                "repo_file_count": len(repo_tree),
                "selected_context_files": list(context_files.keys()),
                "files": context_files,
            },
            "expected_review_output_format": {
                "summary": "Short summary of what changed and intent.",
                "senior_engineer_assessment": "Concise engineering judgment.",
                "blockers": ["Only issues that should block merge."],
                "warnings": ["Risks or concerns that should be addressed or confirmed."],
                "suggestions": ["Non-blocking improvements."],
                "test_review": "Whether tests are needed based on actual change type.",
                "documentation_review": "Only if docs are changed or impacted.",
                "deployment_or_config_impact": "Only if relevant.",
                "recommended_reviewer_comments": [
                    {
                        "file": "path if applicable",
                        "comment": "Specific comment grounded in evidence",
                    }
                ],
                "approval_recommendation": "approve | approve_with_comments | request_changes",
            },
        }