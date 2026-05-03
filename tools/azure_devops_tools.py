from __future__ import annotations

from typing import Any

from utils.azure_devops_helper import AzureDevOpsHelper


class AzureDevOpsTool:
    def __init__(self) -> None:
        self.azure = AzureDevOpsHelper()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "get_azure_work_item",
                "description": "Get Azure Boards work item details by ticket ID",
            },
            {
                "name": "get_azure_context_for_text",
                "description": "Extract Azure ticket IDs from text and fetch ticket/wiki context",
            },
            {
                "name": "get_azure_wiki_page",
                "description": "Get Azure DevOps wiki page content by path",
            },
        ]

    def get_azure_work_item(self, work_item_id: int) -> dict[str, Any]:
        return self.azure.get_work_item(work_item_id)

    def get_azure_context_for_text(self, text: str) -> dict[str, Any]:
        return self.azure.get_context_for_text(text)

    def get_azure_wiki_page(self, path: str) -> dict[str, Any] | None:
        return self.azure.get_wiki_page(path)