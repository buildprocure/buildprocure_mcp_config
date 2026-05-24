"""
GitHub Helper Functions
Utilities for interacting with GitHub API.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


class GitHubHelper:
    """Helper class for GitHub API interactions."""

    def __init__(self) -> None:
        self.token = os.getenv("GITHUB_TOKEN")
        self.user = os.getenv("GITHUB_USER", "buildprocure")
        self.base_url = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
        self.api_url = self.base_url
        self.github_org = self.user
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", 30)
        response = requests.request(method, url, headers=kwargs.pop("headers", self.headers), **kwargs)
        return response

    def _error(self, message: str, status_code: int | None = None) -> dict[str, Any]:
        return {"ok": False, "error": message, "status_code": status_code}

    def normalize_repo(self, repo: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": repo.get("name"),
            "full_name": repo.get("full_name"),
            "owner": repo.get("owner", {}).get("login"),
            "url": repo.get("html_url"),
            "description": repo.get("description") or "",
            "topics": repo.get("topics", []),
            "archived": repo.get("archived", False),
            "fork": repo.get("fork", False),
            "private": repo.get("private", False),
            "visibility": repo.get("visibility"),
            "default_branch": repo.get("default_branch") or "main",
            "language": repo.get("language"),
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "size": repo.get("size", 0),
            "updated_at": repo.get("updated_at"),
        }

    def get_user_repos(self) -> list[dict[str, Any]]:
        """Fetch all repositories visible to the configured token/user."""
        if self.token:
            url = f"{self.base_url}/user/repos"
            params = {"per_page": 100, "type": "all", "sort": "updated"}
        else:
            url = f"{self.base_url}/users/{self.user}/repos"
            params = {"per_page": 100, "type": "all", "sort": "updated"}

        repos: list[dict[str, Any]] = []
        page = 1
        while True:
            response = self._request("GET", url, params={**params, "page": page})
            if response.status_code != 200:
                logger.error("Failed to fetch repos: %s %s", response.status_code, response.text)
                return repos

            batch = response.json()
            repos.extend(batch)
            if len(batch) < params["per_page"]:
                break
            page += 1

        logger.info("Fetched %s repositories for %s", len(repos), self.user)
        return repos

    def get_repo_details(self, repo_name: str) -> dict[str, Any] | None:
        """Get detailed information about a repository."""
        url = f"{self.base_url}/repos/{self.github_org}/{repo_name}"
        try:
            response = self._request("GET", url)
            if response.status_code == 200:
                logger.info("Fetched details for %s", repo_name)
                return response.json()
            logger.error("Failed to fetch %s: %s", repo_name, response.status_code)
            return None
        except Exception as exc:
            logger.error("Error fetching %s: %s", repo_name, exc)
            return None

    def get_repo_details_safe(self, repo_name: str) -> dict[str, Any]:
        repo = self.get_repo_details(repo_name)
        if not repo:
            return self._error(f"Repository not found or unavailable: {repo_name}", 404)
        return {"ok": True, "repository": self.normalize_repo(repo)}

    def list_open_pull_requests(self, repo_name: str) -> list[dict[str, Any]]:
        url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/pulls"
        response = self._request("GET", url, params={"state": "open"})
        response.raise_for_status()
        return response.json()

    def get_pull_request(self, repo_name: str, pr_number: int) -> dict[str, Any]:
        url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/pulls/{pr_number}"
        response = self._request("GET", url)
        response.raise_for_status()
        return response.json()

    def get_pull_request_files(self, repo_name: str, pr_number: int) -> list[dict[str, Any]]:
        url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/pulls/{pr_number}/files"
        response = self._request("GET", url)
        response.raise_for_status()
        return response.json()

    def get_pull_request_diff(self, repo_name: str, pr_number: int) -> str:
        url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/pulls/{pr_number}"
        headers = dict(self.headers)
        headers["Accept"] = "application/vnd.github.v3.diff"
        response = self._request("GET", url, headers=headers)
        response.raise_for_status()
        return response.text

    def get_repo_file(self, repo_name: str, path: str, ref: str = "main") -> dict[str, Any] | None:
        url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/contents/{quote(path)}"
        response = self._request("GET", url, params={"ref": ref})

        if response.status_code == 404:
            return None

        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            return {
                "path": path,
                "exists": True,
                "type": "directory",
                "content": "",
                "entries": [item.get("path") for item in data],
                "html_url": data[0].get("html_url") if data else None,
            }

        content = ""
        if data.get("content"):
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")

        return {
            "path": path,
            "exists": True,
            "type": data.get("type", "file"),
            "content": content,
            "sha": data.get("sha"),
            "size": data.get("size", 0),
            "encoding": data.get("encoding"),
            "html_url": data.get("html_url"),
            "download_url": data.get("download_url"),
        }

    def get_repo_file_safe(self, repo_name: str, path: str, ref: str = "main") -> dict[str, Any]:
        try:
            file_data = self.get_repo_file(repo_name, path, ref=ref)
            if not file_data:
                return {
                    "ok": False,
                    "exists": False,
                    "repo_name": repo_name,
                    "path": path,
                    "target_ref": ref,
                    "error": f"File not found: {path}",
                    "status_code": 404,
                }
            return {"ok": True, "repo_name": repo_name, "target_ref": ref, "file": file_data}
        except requests.HTTPError as exc:
            response = exc.response
            return self._error(str(exc), response.status_code if response else None) | {
                "repo_name": repo_name,
                "path": path,
                "target_ref": ref,
            }
        except Exception as exc:
            return self._error(str(exc)) | {"repo_name": repo_name, "path": path, "target_ref": ref}

    def get_repo_files_batch_safe(
        self,
        repo_name: str,
        paths: list[str],
        ref: str = "main",
        max_files: int = 50,
    ) -> dict[str, Any]:
        files = []
        errors = []
        for path in paths[:max_files]:
            result = self.get_repo_file_safe(repo_name, path, ref=ref)
            if result.get("ok"):
                files.append(result["file"])
            else:
                errors.append(result)

        return {
            "ok": True,
            "repo_name": repo_name,
            "target_ref": ref,
            "requested_count": len(paths),
            "returned_count": len(files),
            "truncated": len(paths) > max_files,
            "files": files,
            "errors": errors,
        }

    def _resolve_tree_sha(self, repo_name: str, ref: str) -> str:
        branch_url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/branches/{quote(ref, safe='')}"
        branch_response = self._request("GET", branch_url)
        if branch_response.status_code == 200:
            branch = branch_response.json()
            return branch["commit"]["commit"]["tree"]["sha"]

        commit_url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/commits/{quote(ref, safe='')}"
        commit_response = self._request("GET", commit_url)
        commit_response.raise_for_status()
        commit = commit_response.json()
        return commit["commit"]["tree"]["sha"]

    def get_repo_tree(self, repo_name: str, ref: str = "main") -> list[str]:
        tree_sha = self._resolve_tree_sha(repo_name, ref)
        tree_url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/git/trees/{tree_sha}"
        tree_response = self._request("GET", tree_url, params={"recursive": "1"})
        tree_response.raise_for_status()
        tree = tree_response.json()
        return [item["path"] for item in tree.get("tree", []) if item.get("type") == "blob"]

    def get_repo_tree_safe(self, repo_name: str, ref: str = "main") -> dict[str, Any]:
        try:
            tree = self.get_repo_tree(repo_name, ref=ref)
            return {
                "ok": True,
                "repo_name": repo_name,
                "target_ref": ref,
                "file_count": len(tree),
                "tree": tree,
            }
        except requests.HTTPError as exc:
            response = exc.response
            return self._error(str(exc), response.status_code if response else None) | {
                "repo_name": repo_name,
                "target_ref": ref,
                "tree": [],
            }
        except Exception as exc:
            return self._error(str(exc)) | {"repo_name": repo_name, "target_ref": ref, "tree": []}
