#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import json
import requests
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

        review_markdown = call_openai_pr_reviewer(context)

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

#call OpenAI LLM to produce final Senior Engineer review from MCP context. 
def call_openai_pr_reviewer(context: dict[str, Any]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing on MCP server")

    prompt = f"""
You are the BuildProcure Senior PR Review Agent.

Review this pull request like a senior software engineer.

Use only the evidence provided below:
- PR metadata
- changed files
- diff patches
- repository context files collected by MCP

Rules:
1. Do not give generic comments.
2. Do not invent issues.
3. Every warning/blocker must be grounded in the diff or repo context.
4. For documentation-only PRs, check accuracy against repo files. Do not request tests unless executable commands/examples changed.
5. For code PRs, focus on correctness, regressions, edge cases, security, maintainability, and test impact.
6. For deployment/config PRs, check ports, image names, env files, secrets, networks, rollback impact.
7. If context is insufficient, say exactly what could not be verified.

Return markdown in this exact format:

## 🤖 BuildProcure Agent Review

### Summary
...

### Senior Engineer Assessment
...

### Blockers
- None, or specific blockers

### Warnings
- None, or specific warnings

### Suggestions
- None, or specific suggestions

### Test Review
...

### Documentation Review
...

### Deployment / Config Impact
...

### Suggested Reviewer Comments
- ...

### Approval Recommendation
Approve | Approve with comments | Request changes

MCP review context:
{json.dumps(context, indent=2)}
"""

    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": prompt,
        },
        timeout=120,
    )

    if response.status_code >= 400:
        logger.error("OpenAI error: %s", response.text)

    response.raise_for_status()
    data = response.json()

    text_parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text_parts.append(content.get("text", ""))

    review = "\n".join(text_parts).strip()

    if not review:
        raise RuntimeError(f"No review text returned from OpenAI: {data}")

    return review

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

    reviewer_prompt = fprompt = f"""
You are a senior software engineer reviewing a BuildProcure pull request.

Your review must be polite, practical, and human-sounding.
Do not sound like a bot.
Do not give generic comments.
Only comment when you have a specific, evidence-based improvement.

Use only this MCP context:
{json.dumps(context, indent=2)}

Review rules:
1. Every finding must reference a file name.
2. Include the line number when available from the diff/patch.
3. For each requested change, provide:
   - File name and line number
   - Code to remove
   - Code to add
   - Reason for the change
4. Do not invent line numbers.
5. If exact line number is unavailable, say "line: from diff context".
6. Do not request changes for style preferences unless it affects maintainability, correctness, security, or readability.
7. For documentation-only PRs, focus on accuracy and clarity.
8. For code PRs, focus on bugs, regressions, edge cases, security, tests, and maintainability.
9. If the PR looks fine, say so briefly and do not force comments.

Return markdown in this exact format:

## Review Summary
Short human summary of what changed.

## Suggested Changes

### 1. <Short title>
**File:** `<file path>`  
**Line:** `<line number or "from diff context">`

**Code to remove:**
```<language>
<exact code to remove>```
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