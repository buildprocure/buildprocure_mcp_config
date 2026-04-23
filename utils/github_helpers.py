"""
GitHub Helper Functions
Utilities for interacting with GitHub API
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

class GitHubHelper:
    """Helper class for GitHub API interactions"""
    
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        self.user = os.getenv("GITHUB_USER", "buildprocure")
        self.base_url = os.getenv("GITHUB_API_URL", "https://api.github.com")
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