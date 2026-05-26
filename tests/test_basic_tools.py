from __future__ import annotations

from pathlib import Path

from tools.agent_context_tools import AgentContextTool
from tools.architecture_agent_tools import ArchitectureAgentTool
from tools.config_tools import ConfigTool
from tools.cross_repo_search_tools import CrossRepoSearchTool
from tools.database_schema_tools import DatabaseSchemaTool
from tools.dependency_analyzer_tools import DependencyAnalyzerTool
from tools.legacy_php_analysis_tools import LegacyPHPAnalysisTool
from tools.repository_content_tools import RepositoryContentTool
from tools.unified_workspace_tools import UnifiedWorkspaceTool
from utils.config_manager import ConfigManager
from utils.github_helpers import GitHubHelper
from utils.repo_discovery import RepositoryDiscovery


def _repo(name: str, archived: bool = False, fork: bool = False) -> dict:
    return {
        "name": name,
        "full_name": f"buildprocure/{name}",
        "owner": {"login": "buildprocure"},
        "html_url": f"https://github.com/buildprocure/{name}",
        "description": "",
        "topics": [],
        "archived": archived,
        "fork": fork,
        "private": False,
        "visibility": "public",
        "default_branch": "main",
        "language": "Python",
        "stargazers_count": 0,
        "forks_count": 0,
        "size": 1,
        "updated_at": "2026-01-01T00:00:00Z",
    }


class FakeGitHub:
    def __init__(self) -> None:
        self.normalizer = GitHubHelper()
        self.repos = [
            _repo("bp-base"),
            _repo("procurex"),
            _repo("buildprocure_mcp_config"),
            _repo("random-repo"),
            _repo("bp-archived", archived=True),
            _repo("bp-fork", fork=True),
        ]
        self.tree = [
            "README.md",
            "package.json",
            "requirements.txt",
            "Dockerfile",
            ".github/workflows/test.yml",
            "src/app.py",
            "tests/test_app.py",
        ]
        self.files = {
            "README.md": "# Example\nSearchable docs",
            "package.json": '{"name":"demo","scripts":{"test":"vitest"},"dependencies":{"react":"latest"}}',
            "requirements.txt": "requests==2.31.0\npytest==8.0.0",
            "Dockerfile": "FROM python:3.12-slim",
            ".github/workflows/test.yml": "name: test",
            "src/app.py": "print('searchable code')",
            "tests/test_app.py": "def test_app(): pass",
        }

    def normalize_repo(self, repo: dict) -> dict:
        return self.normalizer.normalize_repo(repo)

    def get_user_repos(self) -> list[dict]:
        return self.repos

    def get_repo_details(self, repo_name: str) -> dict | None:
        return next((repo for repo in self.repos if repo["name"] == repo_name), None)

    def get_repo_details_safe(self, repo_name: str) -> dict:
        repo = self.get_repo_details(repo_name)
        if not repo:
            return {"ok": False, "error": "missing"}
        return {"ok": True, "repository": self.normalize_repo(repo)}

    def get_repo_tree_safe(self, repo_name: str, ref: str = "main") -> dict:
        return {"ok": True, "repo_name": repo_name, "target_ref": ref, "file_count": len(self.tree), "tree": self.tree}

    def get_repo_file_safe(self, repo_name: str, path: str, ref: str = "main") -> dict:
        if path not in self.files:
            return {"ok": False, "exists": False, "path": path, "target_ref": ref, "error": "not found"}
        return {
            "ok": True,
            "repo_name": repo_name,
            "target_ref": ref,
            "file": {
                "path": path,
                "exists": True,
                "content": self.files[path],
                "size": len(self.files[path]),
                "html_url": f"https://example.test/{path}",
            },
        }

    def get_repo_files_batch_safe(self, repo_name: str, paths: list[str], ref: str = "main", max_files: int = 50) -> dict:
        files = []
        errors = []
        for path in paths[:max_files]:
            result = self.get_repo_file_safe(repo_name, path, ref=ref)
            if result["ok"]:
                files.append(result["file"])
            else:
                errors.append(result)
        return {"ok": True, "files": files, "errors": errors, "target_ref": ref}


class EmptyPackageGitHub(FakeGitHub):
    def __init__(self) -> None:
        super().__init__()
        self.files["package.json"] = ""


def _config_manager(tmp_path: Path) -> ConfigManager:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "repo_discovery_policy.yaml").write_text(
        "filters:\n  exclude_archived: true\n  exclude_forks: true\nnaming_patterns:\n  - 'bp-*'\n  - 'procurex'\n  - 'buildprocure_*'\n",
        encoding="utf-8",
    )
    (config_dir / "organization_rules.yaml").write_text("rules: []\n", encoding="utf-8")
    return ConfigManager(config_dir=config_dir)


def test_basic_tool_metadata(tmp_path: Path):
    github = FakeGitHub()
    config = _config_manager(tmp_path)
    discovery = RepositoryDiscovery(github=github, config=config)

    tool_names = set()
    for tool in [
        UnifiedWorkspaceTool(discovery=discovery),
        ArchitectureAgentTool(github=github),
        RepositoryContentTool(github=github),
        CrossRepoSearchTool(github=github, discovery=discovery),
        DatabaseSchemaTool(),
        DependencyAnalyzerTool(github=github),
        LegacyPHPAnalysisTool(github=github),
        ConfigTool(config=config),
        AgentContextTool(github=github, config=config),
    ]:
        tool_names.update(item["name"] for item in tool.get_tools())

    assert "build_agent_context" in tool_names
    assert "get_repo_tree" in tool_names
    assert "get_repo_file" in tool_names
    assert "get_repo_files_batch" in tool_names
    assert "get_repo_manifest_summary" in tool_names
    assert "list_available_configs" in tool_names
    assert "get_database_schema" in tool_names
    assert "build_architecture_analysis" in tool_names
    assert "analyze_legacy_php_module" in tool_names


def test_repo_discovery_respects_policy(tmp_path: Path):
    discovery = RepositoryDiscovery(github=FakeGitHub(), config=_config_manager(tmp_path))

    repos = discovery.get_active_repos()
    names = [repo["name"] for repo in repos]

    assert names == ["bp-base", "procurex", "buildprocure_mcp_config"]

    all_names = [repo["name"] for repo in discovery.get_all_repos(include_archived=True)]
    assert "bp-archived" in all_names
    assert "bp-fork" not in all_names
    assert "random-repo" not in all_names


def test_manifest_detection_for_common_stacks():
    summary = DependencyAnalyzerTool(github=FakeGitHub()).get_repo_manifest_summary("bp-base")

    assert summary["ok"] is True
    manifest_types = {manifest["type"] for manifest in summary["manifests"]}
    assert "node_package" in manifest_types
    assert "python_requirements" in manifest_types
    assert "dockerfile" in manifest_types
    assert "github_actions_workflow" in manifest_types
    assert "node" in summary["stack_summary"]["runtime_hints"]
    assert "python" in summary["stack_summary"]["runtime_hints"]
    assert "docker" in summary["stack_summary"]["deployment_hints"]


def test_empty_package_json_does_not_imply_node_stack():
    summary = DependencyAnalyzerTool(github=EmptyPackageGitHub()).get_repo_manifest_summary("buildprocure_mcp_config")

    package_manifest = next(manifest for manifest in summary["manifests"] if manifest["path"] == "package.json")
    assert package_manifest["has_node_signals"] is False
    assert "node" not in summary["stack_summary"]["runtime_hints"]
    assert "npm" not in summary["stack_summary"]["package_managers"]
    assert "python" in summary["stack_summary"]["runtime_hints"]


def test_search_across_repos_returns_snippets(tmp_path: Path):
    github = FakeGitHub()
    discovery = RepositoryDiscovery(github=github, config=_config_manager(tmp_path))

    result = CrossRepoSearchTool(github=github, discovery=discovery).search_across_repos("searchable", max_results=5)

    assert result["ok"] is True
    assert result["result_count"] > 0
    assert all("snippet" in item for item in result["results"])


def test_build_agent_context_default_and_explicit_paths(tmp_path: Path):
    github = FakeGitHub()
    config = _config_manager(tmp_path)
    context_tool = AgentContextTool(github=github, config=config)

    default_context = context_tool.build_agent_context("bp-base")
    assert default_context["ok"] is True
    assert "package.json" in default_context["selected_paths"]
    assert default_context["manifest_summary"]["ok"] is True
    assert "organization_rules.yaml" in default_context["config_summary"]["available_configs"]["configs"]

    explicit_context = context_tool.build_agent_context("bp-base", target_ref="develop", paths=["README.md", "missing.txt"])
    assert explicit_context["target_ref"] == "develop"
    assert explicit_context["selected_paths"] == ["README.md", "missing.txt"]
    assert len(explicit_context["file_errors"]) == 1
