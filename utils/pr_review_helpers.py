from __future__ import annotations

from typing import Any


DOC_EXTENSIONS = (".md", ".txt", ".rst", ".adoc")
CODE_EXTENSIONS = (".php", ".js", ".ts", ".tsx", ".jsx", ".py", ".java", ".sql")
MAX_DIFF_CHARS = 140_000
MAX_FILE_CONTENT_CHARS = 25_000


class PRReviewHelper:
    def detect_pr_type(self, files: list[dict[str, Any]]) -> dict[str, Any]:
        names = [f["filename"].lower() for f in files]

        docs_only = all(
            name.endswith(DOC_EXTENSIONS)
            or name.startswith("docs/")
            or "readme" in name
            or "changelog" in name
            for name in names
        )

        has_code = any(name.endswith(CODE_EXTENSIONS) for name in names)
        has_tests = any("test" in name or "spec" in name for name in names)
        has_ci = any(".github/workflows" in name or "azure-pipelines" in name for name in names)
        has_docker = any("docker" in name or "compose" in name for name in names)
        has_config = any(
            name.endswith((".yml", ".yaml", ".json", ".env", ".ini", ".conf"))
            for name in names
        )

        if docs_only:
            pr_type = "documentation"
        elif has_ci:
            pr_type = "ci_cd"
        elif has_docker:
            pr_type = "docker_deployment"
        elif has_config:
            pr_type = "configuration"
        elif has_code:
            pr_type = "code"
        else:
            pr_type = "mixed"

        return {
            "type": pr_type,
            "docs_only": docs_only,
            "has_code": has_code,
            "has_tests": has_tests,
            "has_ci": has_ci,
            "has_docker": has_docker,
            "has_config": has_config,
            "changed_files": names,
        }

    def summarize_pr_context(
        self,
        pr: dict[str, Any],
        files: list[dict[str, Any]],
        diff_text: str,
    ) -> dict[str, Any]:
        return {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "body": pr.get("body"),
            "state": pr.get("state"),
            "author": pr.get("user", {}).get("login"),
            "url": pr.get("html_url"),
            "base_branch": pr.get("base", {}).get("ref"),
            "head_branch": pr.get("head", {}).get("ref"),
            "changed_files_count": len(files),
            "additions": sum(f.get("additions", 0) for f in files),
            "deletions": sum(f.get("deletions", 0) for f in files),
            "changed_files": [
                {
                    "filename": f.get("filename"),
                    "status": f.get("status"),
                    "additions": f.get("additions"),
                    "deletions": f.get("deletions"),
                    "changes": f.get("changes"),
                    "patch": f.get("patch", "")[:20_000],
                }
                for f in files
            ],
            "diff": self.trim_text(diff_text, MAX_DIFF_CHARS),
            "diff_truncated": len(diff_text) > MAX_DIFF_CHARS,
        }

    def select_context_files(self, repo_tree: list[str], changed_files: list[str]) -> list[str]:
        important_names = {
            "readme.md",
            "readme.txt",
            "dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            "composer.json",
            "package.json",
            "requirements.txt",
            "pyproject.toml",
            ".env.example",
            ".github/workflows/deploy.yml",
            ".github/workflows/deploy.yaml",
            "azure-pipelines.yml",
        }

        selected: list[str] = []
        lower_to_actual = {p.lower(): p for p in repo_tree}

        for name in important_names:
            if name in lower_to_actual:
                selected.append(lower_to_actual[name])

        for changed in changed_files:
            changed_lower = changed.lower()

            if changed in repo_tree:
                selected.append(changed)

            # Include nearby README/docs for changed docs.
            if changed_lower.startswith("docs/"):
                folder = "/".join(changed.split("/")[:-1])
                for path in repo_tree:
                    if path.startswith(folder) and path.lower().endswith(DOC_EXTENSIONS):
                        selected.append(path)

        return list(dict.fromkeys(selected))[:30]

    def trim_text(self, text: str, max_chars: int) -> str:
        if not text:
            return ""

        if len(text) <= max_chars:
            return text

        return (
            text[:max_chars]
            + "\n\n...[TRUNCATED: content was too large for MCP response]..."
        )

    def trim_file_content(self, content: str) -> str:
        return self.trim_text(content, MAX_FILE_CONTENT_CHARS)

    def build_review_instructions(self, pr_type: str) -> str:
        base = """
You are reviewing this PR as a senior software engineer.

Use only evidence from:
1. PR metadata
2. changed files
3. diff
4. repository context files

Do not give generic comments.
Do not invent issues.
Call out uncertainty clearly.
Focus on correctness, regressions, maintainability, security, deployment impact, and test coverage when relevant.
"""

        if pr_type == "documentation":
            return base + """
This appears to be a documentation PR.
Review it for:
- accuracy against actual repository files
- outdated setup or deployment instructions
- misleading claims about tech stack
- missing prerequisites
- unclear onboarding steps

Do not ask for tests unless the documentation changes executable examples or commands that should be validated.
"""

        if pr_type in {"ci_cd", "docker_deployment", "configuration"}:
            return base + """
This PR touches deployment/configuration areas.
Review it for:
- broken deployment assumptions
- wrong image names/tags
- secret exposure
- environment mismatch
- rollback risk
- port/network conflicts
- production safety
"""

        return base + """
This PR touches code or mixed files.
Review it for:
- correctness
- edge cases
- error handling
- security concerns
- performance impact
- missing or weak tests
- backward compatibility
"""