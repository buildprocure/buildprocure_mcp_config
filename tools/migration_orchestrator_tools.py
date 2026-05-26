"""
Migration Orchestrator Agent Tools
Top-level migration request orchestration for PHP-to-React conversion.
"""

from __future__ import annotations

import re
from typing import Any

from tools.react_code_writer_tools import ReactCodeWriterTool


class MigrationOrchestratorTool:
    """Parse a migration request and run the full React conversion chain."""

    def __init__(self, react_code_writer_tool: ReactCodeWriterTool | None = None) -> None:
        self.react_code_writer_tool = react_code_writer_tool or ReactCodeWriterTool()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "run_migration_request",
                "description": "Run a natural-language PHP-to-React migration request through the agent chain",
            }
        ]

    def run_migration_request(
        self,
        request_text: str,
        source_repo_name: str,
        target_repo_name: str,
        target_ref: str = "main",
        module_name: str | None = None,
        module_path: str | None = None,
        related_paths: list[str] | None = None,
        focus_terms: list[str] | None = None,
        table_names: list[str] | None = None,
        schema_name: str | None = None,
        work_item_id: int | None = None,
        react_app_root: str = "src",
        target_branch: str | None = None,
        base_branch: str = "main",
        dry_run: bool = True,
        overwrite: bool = False,
        create_pull_request: bool = True,
    ) -> dict[str, Any]:
        inferred = self._infer_request(
            request_text=request_text,
            module_name=module_name,
            module_path=module_path,
            related_paths=related_paths or [],
            focus_terms=focus_terms or [],
            table_names=table_names or [],
            target_branch=target_branch,
            work_item_id=work_item_id,
        )
        missing = self._missing_required(inferred)
        if missing:
            return {
                "ok": False,
                "agent": "migration_orchestrator_agent",
                "request_text": request_text,
                "source_repo_name": source_repo_name,
                "target_repo_name": target_repo_name,
                "dry_run": dry_run,
                "inferred_inputs": inferred,
                "missing_inputs": missing,
                "error": "Unable to infer required migration inputs. Provide overrides for missing fields.",
                "expected_agent_output": self._expected_agent_output(),
            }

        writer_result = self.react_code_writer_tool.write_react_conversion_files(
            source_repo_name=source_repo_name,
            target_repo_name=target_repo_name,
            module_name=inferred["module_name"],
            target_ref=target_ref,
            module_path=inferred["module_path"],
            related_paths=inferred["related_paths"],
            focus_terms=inferred["focus_terms"],
            table_names=inferred["table_names"],
            schema_name=schema_name,
            work_item_id=work_item_id,
            react_app_root=react_app_root,
            target_branch=inferred["target_branch"],
            base_branch=base_branch,
            dry_run=dry_run,
            overwrite=overwrite,
            create_pull_request=create_pull_request,
        )

        return {
            "ok": bool(writer_result.get("ok")),
            "agent": "migration_orchestrator_agent",
            "request_text": request_text,
            "source_repo_name": source_repo_name,
            "target_repo_name": target_repo_name,
            "target_ref": target_ref,
            "base_branch": base_branch,
            "dry_run": dry_run,
            "overwrite": overwrite,
            "create_pull_request": create_pull_request,
            "inferred_inputs": inferred,
            "orchestration_steps": [
                "Infer module, path, focus terms, related paths, tables, and target branch.",
                "Run React Code Writer Agent.",
                "React Code Writer Agent runs React Conversion Agent.",
                "React Conversion Agent runs Migration Spec Agent.",
                "Migration Spec Agent composes Architecture, Legacy PHP, and Database Model Context agents.",
            ],
            "writer_result": writer_result,
            "expected_agent_output": self._expected_agent_output(),
        }

    def _infer_request(
        self,
        request_text: str,
        module_name: str | None,
        module_path: str | None,
        related_paths: list[str],
        focus_terms: list[str],
        table_names: list[str],
        target_branch: str | None,
        work_item_id: int | None,
    ) -> dict[str, Any]:
        text = request_text.lower()
        domain = self._infer_domain(text)
        parent_module = self._infer_parent_module(text)

        resolved_module_name = module_name or self._module_name(parent_module, domain)
        resolved_module_path = module_path or parent_module
        resolved_focus_terms = focus_terms or ([domain.lower()] if domain else [])
        resolved_related_paths = related_paths or self._related_paths(parent_module, domain)
        resolved_table_names = table_names or self._table_names(domain)
        resolved_target_branch = target_branch or self._branch_name(resolved_module_name, work_item_id)

        return {
            "module_name": resolved_module_name,
            "module_path": resolved_module_path,
            "related_paths": resolved_related_paths,
            "focus_terms": resolved_focus_terms,
            "table_names": resolved_table_names,
            "target_branch": resolved_target_branch,
            "inference": {
                "domain": domain,
                "parent_module": parent_module,
                "confidence": "high" if domain and parent_module else "medium" if domain or parent_module else "low",
            },
        }

    def _infer_domain(self, text: str) -> str | None:
        known = {
            "boq": "BOQ",
            "purchase order": "Purchase Order",
            "po": "PO",
            "invoice": "Invoice",
            "timesheet": "Timesheet",
            "rfq": "RFQ",
        }
        for needle, domain in known.items():
            if re.search(rf"\b{re.escape(needle)}\b", text):
                return domain
        match = re.search(r"convert\s+([a-z0-9 _-]+?)\s+(?:of|in|from)\s+", text)
        if match:
            return match.group(1).strip().title()
        return None

    def _infer_parent_module(self, text: str) -> str | None:
        for module in ["Buyer", "Supplier", "Admin"]:
            if re.search(rf"\b{module.lower()}\b", text):
                return module
        match = re.search(r"of\s+([a-z0-9 _-]+?)\s+module", text)
        if match:
            return match.group(1).strip().title()
        return None

    def _module_name(self, parent_module: str | None, domain: str | None) -> str | None:
        if parent_module and domain:
            return f"{parent_module} {domain}"
        return domain or parent_module

    def _related_paths(self, parent_module: str | None, domain: str | None) -> list[str]:
        if parent_module and domain:
            return [f"app/Modules/{parent_module}/{domain.replace(' ', '')}"]
        return []

    def _table_names(self, domain: str | None) -> list[str]:
        if not domain:
            return []
        mapping = {
            "BOQ": ["boqs", "boq_items"],
            "Purchase Order": ["purchase_orders", "purchase_order_items"],
            "PO": ["purchase_orders", "purchase_order_items"],
            "Invoice": ["Invoice", "Invoice_Files"],
            "Timesheet": ["Timesheet", "TS_Files"],
            "RFQ": ["rfqs", "rfq_items", "rfq_suppliers"],
        }
        return mapping.get(domain, [domain.lower().replace(" ", "_")])

    def _branch_name(self, module_name: str | None, work_item_id: int | None) -> str | None:
        if not module_name:
            return None
        prefix = f"ab-{work_item_id}-" if work_item_id else ""
        return f"{prefix}{self._slug(module_name)}-react-scaffold"

    def _missing_required(self, inferred: dict[str, Any]) -> list[str]:
        missing = []
        for key in ["module_name", "module_path", "focus_terms", "target_branch"]:
            value = inferred.get(key)
            if value is None or value == []:
                missing.append(key)
        return missing

    def _slug(self, value: str) -> str:
        normalized = value.replace("_", "-").replace("/", "-").replace(" ", "-").lower()
        return "-".join(part for part in normalized.split("-") if part)

    def _expected_agent_output(self) -> dict[str, Any]:
        return {
            "inferred_inputs": "Inputs inferred from request text and caller overrides.",
            "orchestration_steps": ["Agent chain executed for the migration request."],
            "writer_result": "Dry-run or write result from React Code Writer Agent.",
            "next_steps": ["Confirm dry-run output, then rerun with dry_run=false to write files."],
        }
