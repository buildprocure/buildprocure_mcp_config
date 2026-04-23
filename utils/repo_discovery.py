"""
Repository Discovery
Auto-discover and manage BuildProcure repositories
"""

import logging
from utils.github_helpers import GitHubHelper

logger = logging.getLogger(__name__)

class RepositoryDiscovery:
    """Handles repository discovery and management"""
    
    def __init__(self):
        self.github = GitHubHelper()
        self.repos = []
        self.all_repos = []
        self._discover_repos()
    
    def _discover_repos(self):
        """Discover all repositories"""
        try:
            all_repos = self.github.get_user_repos()
            self.all_repos = all_repos
            
            # Filter to active repos (non-archived, non-fork)
            self.repos = [r for r in all_repos if not r.get('archived') and not r.get('fork')]
            
            logger.info(f"Total repos: {len(all_repos)}, Active repos: {len(self.repos)}")
            
            # Log details
            archived = [r['name'] for r in all_repos if r.get('archived')]
            forks = [r['name'] for r in all_repos if r.get('fork')]
            
            if archived:
                logger.info(f"Archived repos: {archived}")
            if forks:
                logger.info(f"Fork repos: {forks}")
                
        except Exception as e:
            logger.error(f"Error discovering repositories: {e}")
            self.repos = []
            self.all_repos = []
    
    def get_active_repos(self):
        """Get list of active repositories"""
        return [
            {
                "name": r["name"],
                "url": r["html_url"],
                "description": r.get("description", ""),
                "topics": r.get("topics", []),
                "archived": r.get("archived", False)
            }
            for r in self.repos
        ]
    
    def get_all_repos(self):
        """Get all repositories including archived"""
        return [
            {
                "name": r["name"],
                "url": r["html_url"],
                "description": r.get("description", ""),
                "topics": r.get("topics", []),
                "archived": r.get("archived", False)
            }
            for r in self.all_repos
        ]
    
    def get_repo_info(self, repo_name):
        """Get information about a specific repository"""
        try:
            repo = self.github.get_repo_details(repo_name)
            if repo:
                return {
                    "name": repo["name"],
                    "url": repo["html_url"],
                    "description": repo.get("description"),
                    "topics": repo.get("topics", []),
                    "archived": repo["archived"],
                    "language": repo.get("language"),
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0)
                }
            return None
        except Exception as e:
            logger.error(f"Error getting repo info for {repo_name}: {e}")
            return None