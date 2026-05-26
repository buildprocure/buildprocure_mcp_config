"""
React Code Writer Agent Tools
Generate and write React migration files into a target GitHub repository.
"""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

import requests

from tools.react_conversion_tools import ReactConversionTool
from utils.github_helpers import GitHubHelper

MAX_WRITTEN_FILES = 80


class ReactCodeWriterTool:
    """Write generated React conversion files to a target repository branch."""

    def __init__(
        self,
        github: GitHubHelper | None = None,
        react_conversion_tool: ReactConversionTool | None = None,
    ) -> None:
        self.github = github or GitHubHelper()
        self.react_conversion_tool = react_conversion_tool or ReactConversionTool()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "write_react_conversion_files",
                "description": "Generate React migration files and write them to a target GitHub repository branch",
            }
        ]

    def write_react_conversion_files(
        self,
        source_repo_name: str,
        target_repo_name: str,
        module_name: str,
        target_ref: str = "main",
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
        conversion_result = self.react_conversion_tool.build_react_conversion_plan(
            repo_name=source_repo_name,
            module_name=module_name,
            target_ref=target_ref,
            module_path=module_path,
            related_paths=related_paths,
            focus_terms=focus_terms,
            table_names=table_names,
            schema_name=schema_name,
            work_item_id=work_item_id,
            react_app_root=react_app_root,
            include_database_schema=True,
        )
        if not conversion_result.get("ok"):
            return {
                "ok": False,
                "agent": "react_code_writer_agent",
                "error": "React conversion plan failed",
                "conversion_plan_context": conversion_result,
            }

        plan = conversion_result["react_conversion_plan"]
        generated_files = self._generate_files(module_name, plan)
        branch_name = target_branch or self._branch_name(module_name, work_item_id)

        result = {
            "ok": True,
            "agent": "react_code_writer_agent",
            "source_repo_name": source_repo_name,
            "target_repo_name": target_repo_name,
            "base_branch": base_branch,
            "target_branch": branch_name,
            "dry_run": dry_run,
            "overwrite": overwrite,
            "file_count": len(generated_files),
            "generated_files": generated_files,
            "conversion_plan_context": conversion_result,
            "write_results": [],
            "pull_request": None,
            "expected_agent_output": self._expected_agent_output(),
        }

        if dry_run:
            return result

        branch_result = self._ensure_branch(target_repo_name, branch_name, base_branch)
        if not branch_result.get("ok"):
            return result | {"ok": False, "error": branch_result.get("error"), "branch_result": branch_result}

        write_results = []
        for file_data in generated_files[:MAX_WRITTEN_FILES]:
            write_results.append(
                self._upsert_file(
                    repo_name=target_repo_name,
                    branch_name=branch_name,
                    path=file_data["path"],
                    content=file_data["content"],
                    message=self._commit_message(module_name, work_item_id, file_data["path"]),
                    overwrite=overwrite,
                )
            )

        result["write_results"] = write_results
        result["ok"] = all(item.get("ok") or item.get("skipped") for item in write_results)

        if result["ok"] and create_pull_request:
            result["pull_request"] = self._create_pull_request(
                repo_name=target_repo_name,
                branch_name=branch_name,
                base_branch=base_branch,
                module_name=module_name,
                work_item_id=work_item_id,
            )

        return result

    def _generate_files(self, module_name: str, plan: dict[str, Any]) -> list[dict[str, str]]:
        file_plan = plan.get("file_plan", {})
        files = [
            {"path": file_plan.get("types"), "content": self._types_content(plan)},
            {"path": file_plan.get("api_client"), "content": self._api_client_content(plan)},
            {"path": file_plan.get("index"), "content": self._index_content(plan)},
            {"path": plan.get("route_plan", {}).get("route_file"), "content": self._routes_content(plan)},
            {"path": f"{plan.get('feature_dir')}/README.md", "content": self._readme_content(module_name, plan)},
        ]

        for component in file_plan.get("components", []):
            files.append({"path": component.get("path"), "content": self._component_content(component, plan)})
        for hook in file_plan.get("hooks", []):
            files.append({"path": hook.get("path"), "content": self._hook_content(hook, plan)})
        for test_path in file_plan.get("tests", []):
            component_name = test_path.rsplit("/", 1)[-1].removesuffix(".test.tsx")
            files.append({"path": test_path, "content": self._test_content(component_name)})

        return [file_data for file_data in files if file_data.get("path") and file_data.get("content")]

    def _types_content(self, plan: dict[str, Any]) -> str:
        contracts = plan.get("form_plan", [])
        field_names = sorted({field for contract in contracts for field in contract.get("create_fields", [])})
        fields = "\n".join(f"  {self._safe_identifier(field)}?: string | number | boolean | null;" for field in field_names)
        if not fields:
            fields = "  id?: string | number;"
        return f"""export interface ApiResult<T> {{
  data: T;
  error?: string;
}}

export interface FeatureRecord {{
{fields}
}}

export interface FeatureFormValues extends FeatureRecord {{}}
"""

    def _api_client_content(self, plan: dict[str, Any]) -> str:
        functions = []
        for item in plan.get("data_fetching_plan", []):
            fn = item.get("client_function")
            route = item.get("route")
            method = (item.get("methods") or ["GET"])[0]
            body_arg = ", payload?: unknown" if method != "GET" else ""
            body = "\n    body: JSON.stringify(payload)," if method != "GET" else ""
            functions.append(
                f"""export async function {fn}({body_arg.lstrip(', ')}): Promise<unknown> {{
  const response = await fetch("{route}", {{
    method: "{method}",
    headers: {{ "Content-Type": "application/json" }},{body}
  }});
  if (!response.ok) {{
    throw new Error(`Request failed: ${{response.status}}`);
  }}
  return response.json();
}}"""
            )
        return "\n\n".join(functions) + "\n"

    def _hook_content(self, hook: dict[str, Any], plan: dict[str, Any]) -> str:
        api_client = plan.get("file_plan", {}).get("api_client", "")
        api_module = "../api/" + api_client.rsplit("/", 1)[-1].removesuffix(".ts")
        fn_name = self._client_function_for_hook(hook)
        hook_name = hook.get("hook_name")
        methods = hook.get("methods", [])
        if "POST" in methods:
            return f"""import {{ useMutation }} from "@tanstack/react-query";
import {{ {fn_name} }} from "{api_module}";

export function {hook_name}() {{
  return useMutation({{
    mutationFn: (payload: unknown) => {fn_name}(payload),
  }});
}}
"""
        return f"""import {{ useQuery }} from "@tanstack/react-query";
import {{ {fn_name} }} from "{api_module}";

export function {hook_name}() {{
  return useQuery({{
    queryKey: ["{hook.get('api_route')}"],
    queryFn: () => {fn_name}(),
  }});
}}
"""

    def _component_content(self, component: dict[str, Any], plan: dict[str, Any]) -> str:
        name = component.get("component_name")
        role = component.get("role_hint")
        source_path = component.get("source_path")
        return f"""import type {{ FeatureRecord }} from "../types";

type {name}Props = {{
  records?: FeatureRecord[];
}};

export function {name}({{ records = [] }}: {name}Props) {{
  return (
    <section className="container py-3">
      <div className="d-flex align-items-center justify-content-between mb-3">
        <h1 className="h4 mb-0">{name}</h1>
      </div>
      <div className="card">
        <div className="card-body">
          <p className="text-muted mb-3">Migrated from <code>{source_path}</code>.</p>
          <p className="mb-0">Role: {role or "feature screen"}</p>
          {{records.length > 0 && (
            <pre className="mt-3 mb-0">{{JSON.stringify(records, null, 2)}}</pre>
          )}}
        </div>
      </div>
    </section>
  );
}}
"""

    def _routes_content(self, plan: dict[str, Any]) -> str:
        imports = []
        routes = []
        for route in plan.get("route_plan", {}).get("screen_routes", []):
            component = route.get("component_name")
            imports.append(f'import {{ {component} }} from "./components/{component}";')
            routes.append(f'  {{ path: "{route.get("path")}", element: <{component} /> }},')
        return "\n".join(imports) + "\n\nexport const featureRoutes = [\n" + "\n".join(routes) + "\n];\n"

    def _index_content(self, plan: dict[str, Any]) -> str:
        exports = ['export * from "./routes";', 'export * from "./types";']
        for component in plan.get("file_plan", {}).get("components", []):
            name = component.get("component_name")
            exports.append(f'export * from "./components/{name}";')
        return "\n".join(exports) + "\n"

    def _test_content(self, component_name: str) -> str:
        return f"""import {{ render, screen }} from "@testing-library/react";
import {{ {component_name} }} from "../components/{component_name}";

describe("{component_name}", () => {{
  it("renders the migrated screen", () => {{
    render(<{component_name} />);
    expect(screen.getByText("{component_name}")).toBeInTheDocument();
  }});
}});
"""

    def _readme_content(self, module_name: str, plan: dict[str, Any]) -> str:
        steps = "\n".join(f"- {step}" for step in plan.get("implementation_steps", []))
        risks = "\n".join(f"- {risk}" for risk in plan.get("risks", []))
        return f"""# {module_name}

Generated React migration scaffold.

## Implementation Steps
{steps}

## Risks
{risks or "- None captured."}
"""

    def _ensure_branch(self, repo_name: str, branch_name: str, base_branch: str) -> dict[str, Any]:
        existing = self._get_branch(repo_name, branch_name)
        if existing.get("ok"):
            return existing | {"created": False}

        base = self._get_branch(repo_name, base_branch)
        if not base.get("ok"):
            return base

        url = f"{self.github.api_url}/repos/{self.github.github_org}/{repo_name}/git/refs"
        response = self.github._request(
            "POST",
            url,
            json={"ref": f"refs/heads/{branch_name}", "sha": base["sha"]},
        )
        if response.status_code not in {200, 201}:
            return self.github._error(response.text, response.status_code)
        return {"ok": True, "branch": branch_name, "sha": base["sha"], "created": True}

    def _get_branch(self, repo_name: str, branch_name: str) -> dict[str, Any]:
        url = f"{self.github.api_url}/repos/{self.github.github_org}/{repo_name}/branches/{quote(branch_name, safe='')}"
        response = self.github._request("GET", url)
        if response.status_code != 200:
            return self.github._error(response.text, response.status_code)
        data = response.json()
        return {"ok": True, "branch": branch_name, "sha": data["commit"]["sha"]}

    def _upsert_file(
        self,
        repo_name: str,
        branch_name: str,
        path: str,
        content: str,
        message: str,
        overwrite: bool,
    ) -> dict[str, Any]:
        existing = self.github.get_repo_file_safe(repo_name, path, ref=branch_name)
        if existing.get("ok") and not overwrite:
            return {"ok": True, "skipped": True, "path": path, "reason": "file exists and overwrite=false"}

        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch_name,
        }
        if existing.get("ok"):
            payload["sha"] = existing["file"].get("sha")

        url = f"{self.github.api_url}/repos/{self.github.github_org}/{repo_name}/contents/{quote(path)}"
        response = self.github._request("PUT", url, json=payload)
        if response.status_code not in {200, 201}:
            return {"ok": False, "path": path, "error": response.text, "status_code": response.status_code}
        return {"ok": True, "path": path, "status_code": response.status_code, "html_url": response.json().get("content", {}).get("html_url")}

    def _create_pull_request(
        self,
        repo_name: str,
        branch_name: str,
        base_branch: str,
        module_name: str,
        work_item_id: int | None,
    ) -> dict[str, Any]:
        title = self._commit_prefix(work_item_id) + f" Add {module_name} React scaffold"
        body = "Generated React migration scaffold from the React Code Writer Agent."
        url = f"{self.github.api_url}/repos/{self.github.github_org}/{repo_name}/pulls"
        response = self.github._request(
            "POST",
            url,
            json={"title": title, "head": branch_name, "base": base_branch, "body": body},
        )
        if response.status_code not in {200, 201, 422}:
            return {"ok": False, "error": response.text, "status_code": response.status_code}
        if response.status_code == 422:
            return {"ok": False, "error": "Pull request may already exist", "status_code": response.status_code}
        data = response.json()
        return {"ok": True, "number": data.get("number"), "url": data.get("html_url")}

    def _branch_name(self, module_name: str, work_item_id: int | None) -> str:
        prefix = f"ab-{work_item_id}-" if work_item_id else ""
        return f"{prefix}{self._slug(module_name)}-react-scaffold"

    def _commit_message(self, module_name: str, work_item_id: int | None, path: str) -> str:
        return self._commit_prefix(work_item_id) + f" Add {module_name} React scaffold file {path}"

    def _commit_prefix(self, work_item_id: int | None) -> str:
        return f"AB#{work_item_id}" if work_item_id else "React migration"

    def _client_function_for_hook(self, hook: dict[str, Any]) -> str:
        hook_name = hook.get("hook_name", "useData")
        stem = hook_name[3:] if hook_name.startswith("use") else hook_name
        if "POST" in hook.get("methods", []):
            return f"submit{stem}"
        return f"fetch{stem}"

    def _safe_identifier(self, value: str) -> str:
        cleaned = "".join(char if char.isalnum() or char == "_" else "_" for char in value)
        return cleaned if cleaned and not cleaned[0].isdigit() else f"field_{cleaned}"

    def _slug(self, value: str) -> str:
        normalized = value.replace("_", "-").replace("/", "-").replace(" ", "-").lower()
        return "-".join(part for part in normalized.split("-") if part)

    def _expected_agent_output(self) -> dict[str, Any]:
        return {
            "generated_files": ["Files generated from the React conversion plan."],
            "write_results": ["GitHub write results for each file when dry_run=false."],
            "pull_request": "Target repository PR metadata when create_pull_request=true.",
            "next_steps": ["Review generated scaffold, fill business behavior, and run frontend tests."],
        }
