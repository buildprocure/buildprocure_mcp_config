"""
GitHub Helper Functions
Utilities for interacting with GitHub API
"""

import os
import logging
import requests
import base64

logger = logging.getLogger(__name__)

class GitHubHelper:
    """Helper class for GitHub API interactions"""
    
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        self.user = os.getenv("GITHUB_USER", "buildprocure")
        self.base_url = os.getenv("GITHUB_API_URL", "https://api.github.com")
        self.api_url = self.base_url
        self.github_org = self.user
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    def get_user_repos(self):
        """Fetch all repositories for the user"""
        url = f"{self.base_url}/users/{self.user}/repos?per_page=100&type=all"
        try:
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                repos = response.json()
                logger.info(f"Fetched {len(repos)} repositories for {self.user}")
                return repos
            elif response.status_code == 401:
                logger.error("Authentication failed - check your GitHub token")
                return []
            else:
                logger.error(f"Failed to fetch repos: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching repos: {e}")
            return []
    
    def get_repo_details(self, repo_name):
        """Get detailed information about a repository"""
        url = f"{self.base_url}/repos/{self.user}/{repo_name}"
        try:
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                logger.info(f"Fetched details for {repo_name}")
                return response.json()
            else:
                logger.error(f"Failed to fetch {repo_name}: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching {repo_name}: {e}")
            return None
    
    def list_open_pull_requests(self, repo_name: str) -> list[dict]:
        url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/pulls"
        response = requests.get(url, headers=self.headers, params={"state": "open"}, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_pull_request(self, repo_name: str, pr_number: int) -> dict:
        url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/pulls/{pr_number}"
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_pull_request_files(self, repo_name: str, pr_number: int) -> list[dict]:
        url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/pulls/{pr_number}/files"
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_pull_request_diff(self, repo_name: str, pr_number: int) -> str:
        url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/pulls/{pr_number}"
        headers = dict(self.headers)
        headers["Accept"] = "application/vnd.github.v3.diff"
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    
    def get_repo_file(self, repo_name: str, path: str, ref: str = "main") -> dict | None:
        url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/contents/{path}"

        response = requests.get(
            url,
            headers=self.headers,
            params={"ref": ref},
            timeout=30,
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()
        data = response.json()

        content = ""
        if data.get("content"):
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")

        return {
            "path": path,
            "exists": True,
            "content": content,
            "sha": data.get("sha"),
            "html_url": data.get("html_url"),
        }


    def get_repo_tree(self, repo_name: str, ref: str = "main") -> list[str]:
        branch_url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/branches/{ref}"

        branch_response = requests.get(
            branch_url,
            headers=self.headers,
            timeout=30,
        )
        branch_response.raise_for_status()
        branch = branch_response.json()

        tree_sha = branch["commit"]["commit"]["tree"]["sha"]

        tree_url = f"{self.api_url}/repos/{self.github_org}/{repo_name}/git/trees/{tree_sha}"

        tree_response = requests.get(
            tree_url,
            headers=self.headers,
            params={"recursive": "1"},
            timeout=30,
        )
        tree_response.raise_for_status()
        tree = tree_response.json()

        return [
            item["path"]
            for item in tree.get("tree", [])
            if item.get("type") == "blob"
        ]