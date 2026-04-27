#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from tools.unified_workspace_tools import UnifiedWorkspaceTool
from tools.cross_repo_search_tools import CrossRepoSearchTool
from tools.dependency_analyzer_tools import DependencyAnalyzerTool
from tools.pr_review_tools import PRReviewTool
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
        self.name = os.getenv("MCP_SERVER_NAME", "buildprocure-mcp")
        self.version = os.getenv("MCP_SERVER_VERSION", "1.0.0")
        self.config = ConfigManager()

        logger.info("Initializing MCP tools...")

        self.workspace_tool = UnifiedWorkspaceTool()
        self.search_tool = CrossRepoSearchTool()
        self.dep_tool = DependencyAnalyzerTool()
        self.pr_review_tool = PRReviewTool()

        logger.info("Loaded %s workspace tools", len(self.workspace_tool.get_tools()))
        logger.info("Loaded %s search tools", len(self.search_tool.get_tools()))
        logger.info("Loaded %s dependency tools", len(self.dep_tool.get_tools()))
        logger.info("Loaded %s PR review tools", len(self.pr_review_tool.get_tools()))


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


@mcp.tool()
def search_across_repos(query: str) -> dict[str, Any]:
    """Search across BuildProcure repositories for a query or pattern."""
    return service.search_tool.search_across_repos(query)


@mcp.tool()
def analyze_dependencies(repo_name: str) -> dict[str, Any]:
    """Analyze dependencies for a specific BuildProcure repository."""
    return service.dep_tool.analyze_dependencies(repo_name)


@mcp.tool()
def list_open_pull_requests(repo_name: str) -> dict[str, Any]:
    """List open pull requests for a BuildProcure repository."""
    return service.pr_review_tool.list_open_pull_requests(repo_name)


@mcp.tool()
def get_pull_request_details(repo_name: str, pr_number: int) -> dict[str, Any]:
    """Get pull request metadata and changed files."""
    return service.pr_review_tool.get_pull_request_details(repo_name, pr_number)


@mcp.tool()
def get_pr_review_context(repo_name: str, pr_number: int) -> dict[str, Any]:
    """Collect PR diff and repository context for senior software engineer review."""
    return service.pr_review_tool.get_pr_review_context(repo_name, pr_number)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": service.name,
            "version": service.version,
        }
    )


@mcp.custom_route("/agent-review", methods=["POST"])
async def agent_review_endpoint(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    repo_name = payload.get("repo_name")
    pr_number = payload.get("pr_number")

    if not repo_name or not pr_number:
        return JSONResponse(
            {"error": "repo_name and pr_number are required"},
            status_code=400,
        )

    try:
        context = service.pr_review_tool.get_pr_review_context(
            repo_name=str(repo_name),
            pr_number=int(pr_number),
        )

        review_markdown = build_agent_review_markdown(context)

        return JSONResponse(
            {
                "repo_name": repo_name,
                "pr_number": int(pr_number),
                "review_markdown": review_markdown,
                "context_used": context.get("repository_context", {}).get(
                    "selected_context_files", []
                ),
            }
        )

    except Exception as exc:
        logger.exception("Agent review failed")
        return JSONResponse({"error": str(exc)}, status_code=500)


def build_agent_review_markdown(context: dict[str, Any]) -> str:
    pr = context.get("pull_request", {})
    repo_context = context.get("repository_context", {})
    pr_type = context.get("pr_type", {})

    changed_files = pr.get("changed_files", [])
    selected_context_files = repo_context.get("selected_context_files", [])
    context_files = repo_context.get("files", {})

    changed_files_text = "\n".join(
        f"- `{f.get('filename')}` ({f.get('status')}, +{f.get('additions')}/-{f.get('deletions')})"
        for f in changed_files
    ) or "- None"

    context_files_text = "\n".join(f"- `{path}`" for path in selected_context_files) or "- None"

    context_summary = build_context_summary(context_files)

    reviewer_prompt = f"""
### Senior Engineer Review Prompt

Please review this PR as a senior software engineer using the MCP-collected context below.

Focus on:
- correctness and regression risk
- security concerns
- maintainability/readability
- edge cases
- test impact only when relevant
- deployment/config impact only when relevant
- documentation accuracy if docs changed

Rules:
- Do not give generic comments.
- Base findings only on PR diff and repository context.
- If context is insufficient, say exactly what could not be verified.
"""

    return f"""
## 🤖 BuildProcure Agent Review Context

### Summary
PR #{context.get("pr_number")} in `{context.get("repo_name")}` was analyzed by the BuildProcure MCP server.

**Detected PR type:** `{pr_type.get("type")}`

### Changed Files
{changed_files_text}

### Repository Context Used
{context_files_text}

{context_summary}

{reviewer_prompt}

### Next Step
Use this MCP context to complete the final review. If this is running from GitHub Actions without an LLM, this comment is the review context package. If using Copilot/ChatGPT, ask it to produce the final senior-engineer review from this context.

---
Triggered by `/agent-review`.
""".strip()


def build_context_summary(context_files: dict[str, Any]) -> str:
    if not context_files:
        return "### Repository Context Summary\nNo additional repository context files were loaded."

    lines = ["### Repository Context Summary"]

    for path, file_data in context_files.items():
        content = file_data.get("content", "") or ""
        preview = content.strip().replace("\n", " ")[:500]

        lines.append(f"- `{path}`: {len(content)} chars loaded")
        if preview:
            lines.append(f"  - Preview: {preview}")

    return "\n".join(lines)


if __name__ == "__main__":
    logger.info("Starting %s v%s", service.name, service.version)
    mcp.run(transport="streamable-http")