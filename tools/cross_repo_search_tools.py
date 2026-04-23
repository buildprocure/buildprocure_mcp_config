"""
Cross Repository Search Tool
Search across all BuildProcure repositories
"""

import logging

logger = logging.getLogger(__name__)

class CrossRepoSearchTool:
    """Tool for searching across repositories"""
    
    def get_tools(self):
        """Return list of tools"""
        return [
            {
                "name": "search_across_repos",
                "description": "Search for patterns across all repositories",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]
    
    def search_across_repos(self, query):
        """Search across repositories"""
        logger.info(f"Searching for: {query}")
        return {
            "query": query,
            "results": [],
            "message": f"Search for '{query}' across repositories would be performed"
        }