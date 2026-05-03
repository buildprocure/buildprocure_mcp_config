from __future__ import annotations

import base64
import logging
import os
import re
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


class AzureDevOpsHelper:
    def __init__(self) -> None:
        self.org = os.getenv("AZURE_DEVOPS_ORG")
        self.project = os.getenv("AZURE_DEVOPS_PROJECT")
        self.pat = os.getenv("AZURE_DEVOPS_PAT")
        self.api_version = os.getenv("AZURE_DEVOPS_API_VERSION", "7.1")
        self.wiki_identifier = os.getenv("AZURE_DEVOPS_WIKI_IDENTIFIER")

        if not self.org or not self.project or not self.pat:
            logger.warning("Azure DevOps env vars are not fully configured")

        token = base64.b64encode(f":{self.pat}".encode("utf-8")).decode("utf-8")
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        self.base_url = f"https://dev.azure.com/{self.org}/{self.project}"

    def extract_work_item_ids(self, text: str | None) -> list[int]:
        if not text:
            return []

        patterns = [
            r"\bAB#(\d+)\b",
            r"\bADO#(\d+)\b",
            r"\bAZ#(\d+)\b",
            r"\bWI#(\d+)\b",
            r"\bwork item[:\s#]+(\d+)\b",
            r"\bticket[:\s#]+(\d+)\b",
        ]

        ids: list[int] = []
        for pattern in patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                try:
                    ids.append(int(match))
                except ValueError:
                    pass

        return sorted(set(ids))

    def get_work_item(self, work_item_id: int) -> dict[str, Any]:
        url = (
            f"{self.base_url}/_apis/wit/workitems/{work_item_id}"
            f"?$expand=relations&api-version={self.api_version}"
        )

        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        fields = data.get("fields", {})

        return {
            "id": data.get("id"),
            "url": data.get("_links", {}).get("html", {}).get("href"),
            "type": fields.get("System.WorkItemType"),
            "title": fields.get("System.Title"),
            "state": fields.get("System.State"),
            "assigned_to": self._person_name(fields.get("System.AssignedTo")),
            "created_by": self._person_name(fields.get("System.CreatedBy")),
            "area_path": fields.get("System.AreaPath"),
            "iteration_path": fields.get("System.IterationPath"),
            "description": self._clean_html(fields.get("System.Description")),
            "acceptance_criteria": self._clean_html(
                fields.get("Microsoft.VSTS.Common.AcceptanceCriteria")
            ),
            "priority": fields.get("Microsoft.VSTS.Common.Priority"),
            "severity": fields.get("Microsoft.VSTS.Common.Severity"),
            "tags": fields.get("System.Tags"),
            "relations": self._summarize_relations(data.get("relations", [])),
        }

    def query_work_items(self, wiql: str) -> list[int]:
        url = f"{self.base_url}/_apis/wit/wiql?api-version={self.api_version}"

        response = requests.post(
            url,
            headers=self.headers,
            json={"query": wiql},
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        return [item["id"] for item in data.get("workItems", [])]

    def get_wiki_page(self, path: str) -> dict[str, Any] | None:
        if not self.wiki_identifier:
            return None

        encoded_path = quote(path, safe="")
        url = (
            f"{self.base_url}/_apis/wiki/wikis/{self.wiki_identifier}/pages"
            f"?path={encoded_path}&includeContent=true&api-version={self.api_version}"
        )

        response = requests.get(
            url,
            headers={**self.headers, "Accept": "application/json"},
            timeout=30,
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()
        data = response.json()

        return {
            "path": path,
            "id": data.get("id"),
            "url": data.get("remoteUrl"),
            "content": data.get("content", ""),
        }

    def get_default_wiki_context(self) -> list[dict[str, Any]]:
        raw_pages = os.getenv("AZURE_DEVOPS_DEFAULT_WIKI_PAGES", "")
        pages = [p.strip() for p in raw_pages.split(",") if p.strip()]

        result = []
        for page in pages:
            wiki_page = self.get_wiki_page(page)
            if wiki_page:
                result.append(wiki_page)

        return result

    def get_context_for_text(self, text: str) -> dict[str, Any]:
        work_item_ids = self.extract_work_item_ids(text)

        work_items = []
        for work_item_id in work_item_ids[:10]:
            try:
                work_items.append(self.get_work_item(work_item_id))
            except Exception as exc:
                logger.warning("Failed to fetch Azure work item %s: %s", work_item_id, exc)
                work_items.append(
                    {
                        "id": work_item_id,
                        "error": str(exc),
                    }
                )

        wiki_pages = self.get_default_wiki_context()

        return {
            "work_item_ids": work_item_ids,
            "work_items": work_items,
            "wiki_pages": wiki_pages,
        }

    def _person_name(self, value: Any) -> str | None:
        if isinstance(value, dict):
            return value.get("displayName") or value.get("uniqueName")
        if isinstance(value, str):
            return value
        return None

    def _summarize_relations(self, relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summarized = []
        for relation in relations[:20]:
            summarized.append(
                {
                    "rel": relation.get("rel"),
                    "url": relation.get("url"),
                    "attributes": relation.get("attributes", {}),
                }
            )
        return summarized

    def _clean_html(self, value: str | None) -> str:
        if not value:
            return ""

        text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
        text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        return text.strip()