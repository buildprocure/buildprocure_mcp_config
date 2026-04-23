"""
Unified Workspace Tool
Lists and manages all BuildProcure repositories
"""

import logging
from utils.github_helpers import GitHubHelper
from utils.repo_discovery import RepositoryDiscovery

logger = logging.getLogger(__name__)

class UnifiedWorkspaceTool:
    """Tool for unified workspace operations"""
    
    def __init__(self):
        self.github = GitHubHelper()
        self.discovery = RepositoryDiscovery()
    
    def get_tools(self):
        """Return list of tools"""
        return [
            {
                "name": "list_all_repos",
                "description": "List all BuildProcure repositories",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                }
            },
            {
                "name": "get_repo_info",
                "description": "Get detailed information about a repository",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name"
                        }
                    },
                    "required": ["repo_name"]
                }
            }
        ]
    
    def list_all_repos(self):
        """List all repositories"""
        repos = self.discovery.get_active_repos()
        logger.info(f"Listed {len(repos)} active repositories")
        return {"repositories": repos, "count": len(repos)}
    
    def get_repo_info(self, repo_name):
        """Get information about a specific repository"""
        repo = self.discovery.get_repo_info(repo_name)
        if not repo:
            logger.warning(f"Repository {repo_name} not found")
            return {"error": f"Repository {repo_name} not found"}
        logger.info(f"Retrieved info for {repo_name}")
        return repo