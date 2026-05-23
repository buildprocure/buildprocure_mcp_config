"""
Dependency Analyzer Tool
Detects repository manifests, stack hints, scripts, tests, and deployment hints.
"""

from __future__ import annotations

import json
import logging
from pathlib import PurePosixPath
from typing import Any

from utils.github_helpers import GitHubHelper

logger = logging.getLogger(__name__)

MANIFEST_NAMES = {
    "package.json": "node_package",
    "requirements.txt": "python_requirements",
    "pyproject.toml": "python_project",
    "poetry.lock": "python_lock",
    "Pipfile": "python_pipfile",
    "composer.json": "php_composer",
    "composer.lock": "php_lock",
    "Dockerfile": "dockerfile",
    "dockerfile": "dockerfile",
    "docker-compose.yml": "docker_compose",
    "docker-compose.yaml": "docker_compose",
    "azure-pipelines.yml": "azure_pipeline",
    "azure-pipelines.yaml": "azure_pipeline",
    ".env.example": "env_example",
}

WORKFLOW_PREFIX = ".github/workflows/"


class DependencyAnalyzerTool:
    """Tool for generic manifest and stack analysis."""

    def __init__(self, github: GitHubHelper | None = None) -> None:
        self.github = github or GitHubHelper()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "get_repo_manifest_summary",
                "description": "Detect repository manifests, stack hints, scripts, tests, and deployment hints",
            },
            {
                "name": "analyze_dependencies",
                "description": "Alias for get_repo_manifest_summary",
            },
        ]

    def analyze_dependencies(self, repo_name: str, target_ref: str = "main") -> dict[str, Any]:
        return self.get_repo_manifest_summary(repo_name, target_ref=target_ref)

    def get_repo_manifest_summary(self, repo_name: str, target_ref: str = "main") -> dict[str, Any]:
        logger.info("Analyzing manifests for %s at %s", repo_name, target_ref)
        tree_result = self.github.get_repo_tree_safe(repo_name, ref=target_ref)
        if not tree_result.get("ok"):
            return tree_result | {"manifests": [], "stack_summary": {}}

        tree = tree_result.get("tree", [])
        manifest_paths = self._select_manifest_paths(tree)
        files_result = self.github.get_repo_files_batch_safe(repo_name, manifest_paths, ref=target_ref)
        manifests = [self._summarize_manifest(file_data) for file_data in files_result.get("files", [])]

        return {
            "ok": True,
            "repo_name": repo_name,
            "target_ref": target_ref,
            "manifest_paths": manifest_paths,
            "manifests": manifests,
            "stack_summary": self._build_stack_summary(manifests, tree),
            "errors": files_result.get("errors", []),
        }

    def _select_manifest_paths(self, tree: list[str]) -> list[str]:
        selected = []
        for path in tree:
            name = PurePosixPath(path).name
            lower_path = path.lower()
            if name in MANIFEST_NAMES or lower_path.startswith(WORKFLOW_PREFIX):
                selected.append(path)
            elif name.lower().startswith("dockerfile"):
                selected.append(path)
            elif name.endswith((".env.example", ".env.sample")):
                selected.append(path)
        return list(dict.fromkeys(selected))[:100]

    def _manifest_type(self, path: str) -> str:
        name = PurePosixPath(path).name
        if path.lower().startswith(WORKFLOW_PREFIX):
            return "github_actions_workflow"
        if name.lower().startswith("dockerfile"):
            return "dockerfile"
        return MANIFEST_NAMES.get(name, "manifest")

    def _summarize_manifest(self, file_data: dict[str, Any]) -> dict[str, Any]:
        path = file_data.get("path", "")
        manifest_type = self._manifest_type(path)
        content = file_data.get("content", "")
        summary: dict[str, Any] = {
            "path": path,
            "type": manifest_type,
            "size": file_data.get("size", 0),
            "url": file_data.get("html_url"),
        }

        if path.endswith("package.json"):
            summary.update(self._summarize_package_json(content))
        elif path.endswith("requirements.txt"):
            deps = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
            summary["dependencies"] = deps[:100]
        elif path.endswith("composer.json"):
            summary.update(self._summarize_composer_json(content))
        elif manifest_type == "dockerfile":
            summary["base_images"] = [line.split(None, 1)[1] for line in content.splitlines() if line.upper().startswith("FROM ")]
        elif manifest_type in {"docker_compose", "github_actions_workflow", "azure_pipeline"}:
            summary["line_count"] = len(content.splitlines())

        return summary

    def _summarize_package_json(self, content: str) -> dict[str, Any]:
        try:
            data = json.loads(content or "{}")
        except json.JSONDecodeError as exc:
            return {"parse_error": f"Invalid package.json: {exc}"}

        return {
            "package_name": data.get("name"),
            "package_manager": data.get("packageManager"),
            "scripts": data.get("scripts", {}),
            "dependencies": sorted((data.get("dependencies") or {}).keys()),
            "dev_dependencies": sorted((data.get("devDependencies") or {}).keys()),
        }

    def _summarize_composer_json(self, content: str) -> dict[str, Any]:
        try:
            data = json.loads(content or "{}")
        except json.JSONDecodeError as exc:
            return {"parse_error": f"Invalid composer.json: {exc}"}

        return {
            "package_name": data.get("name"),
            "scripts": data.get("scripts", {}),
            "dependencies": sorted((data.get("require") or {}).keys()),
            "dev_dependencies": sorted((data.get("require-dev") or {}).keys()),
        }

    def _build_stack_summary(self, manifests: list[dict[str, Any]], tree: list[str]) -> dict[str, Any]:
        manifest_types = {manifest.get("type") for manifest in manifests}
        paths = {manifest.get("path") for manifest in manifests}
        runtime_hints = []
        package_managers = []
        deployment_hints = []
        test_hints = []

        if "node_package" in manifest_types:
            runtime_hints.append("node")
            package_managers.append(self._detect_node_package_manager(paths, tree))
        if any(item in manifest_types for item in {"python_requirements", "python_project", "python_pipfile"}):
            runtime_hints.append("python")
            package_managers.append("pip_or_poetry")
        if "php_composer" in manifest_types:
            runtime_hints.append("php")
            package_managers.append("composer")
        if any(item in manifest_types for item in {"dockerfile", "docker_compose"}):
            deployment_hints.append("docker")
        if "github_actions_workflow" in manifest_types:
            deployment_hints.append("github_actions")
        if "azure_pipeline" in manifest_types:
            deployment_hints.append("azure_pipelines")

        for manifest in manifests:
            scripts = manifest.get("scripts") or {}
            for name, command in scripts.items():
                if "test" in name.lower() or "pytest" in str(command).lower():
                    test_hints.append({"source": manifest.get("path"), "script": name, "command": command})

        if any(path.startswith("tests/") or "/tests/" in path for path in tree):
            test_hints.append({"source": "tree", "hint": "tests directory present"})

        return {
            "runtime_hints": sorted(set(runtime_hints)),
            "package_managers": sorted(set(filter(None, package_managers))),
            "deployment_hints": sorted(set(deployment_hints)),
            "test_hints": test_hints,
            "manifest_count": len(manifests),
        }

    def _detect_node_package_manager(self, paths: set[str], tree: list[str]) -> str:
        if "pnpm-lock.yaml" in tree:
            return "pnpm"
        if "yarn.lock" in tree:
            return "yarn"
        if "package-lock.json" in tree:
            return "npm"
        for path in paths:
            if path.endswith("package.json"):
                return "npm"
        return "node_package_manager_unknown"
