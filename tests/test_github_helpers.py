from __future__ import annotations

from typing import Any

from utils.github_helpers import GitHubHelper


def _repo(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "full_name": f"buildprocure/{name}",
        "owner": {"login": "buildprocure"},
        "html_url": f"https://github.com/buildprocure/{name}",
    }


class FakeResponse:
    def __init__(self, status_code: int, payload: list[dict[str, Any]] | dict[str, Any]) -> None:
        self.status_code = status_code
        self.payload = payload
        self.text = str(payload)

    def json(self) -> list[dict[str, Any]] | dict[str, Any]:
        return self.payload


class FakeGitHubHelper(GitHubHelper):
    def __init__(self) -> None:
        super().__init__()
        self.token = "token"
        self.user = "buildprocure"
        self.base_url = "https://api.github.test"
        self.calls: list[str] = []

    def _request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(url)
        if url.endswith("/user/repos"):
            return FakeResponse(200, [])
        if url.endswith("/orgs/buildprocure/repos"):
            return FakeResponse(200, [_repo("procurex"), _repo("buildprocure_mcp_config")])
        return FakeResponse(404, {"message": "not found"})


class DuplicateGitHubHelper(FakeGitHubHelper):
    def _request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(url)
        if url.endswith("/user/repos"):
            return FakeResponse(200, [_repo("procurex")])
        if url.endswith("/orgs/buildprocure/repos"):
            return FakeResponse(200, [_repo("procurex"), _repo("bp-base")])
        return FakeResponse(404, {"message": "not found"})


def test_get_user_repos_falls_back_to_configured_org_repos():
    helper = FakeGitHubHelper()

    repos = helper.get_user_repos()

    assert [repo["name"] for repo in repos] == ["procurex", "buildprocure_mcp_config"]
    assert "https://api.github.test/user/repos" in helper.calls
    assert "https://api.github.test/orgs/buildprocure/repos" in helper.calls


def test_get_user_repos_deduplicates_user_and_org_sources():
    helper = DuplicateGitHubHelper()

    repos = helper.get_user_repos()

    assert [repo["name"] for repo in repos] == ["procurex", "bp-base"]
