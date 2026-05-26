# Backend API Bridge Agent

Use `generate_backend_api_bridge_files` when a React migration slice needs local PHP API bridge files in the source PHP application.

## Intent

- Generate PHP bridge endpoint scaffolds from the migration spec.
- Return `local_files` only.
- Keep remote writes disabled. Do not push branches, commit, or open pull requests.
- Apply generated files into the user's local source repo after review.

## Typical Input

```json
{
  "repo_name": "procurex",
  "module_name": "Buyer BOQ",
  "target_ref": "main",
  "module_path": "Buyer",
  "related_paths": ["app/Modules/Buyer/BOQ"],
  "focus_terms": ["boq"],
  "table_names": ["boqs", "boq_items"],
  "schema_name": "ilife",
  "work_item_id": 56,
  "api_root": "api",
  "include_database_schema": true
}
```

## Output Handling

1. Inspect the returned `local_files`.
2. Write the files into the local PHP source repo, such as `procurex`.
3. Configure the React app or Vite proxy to call the generated API routes.
4. Test locally before committing.

Generated mutation endpoints are scaffolds. Review legacy PHP behavior and complete create/update/delete/file-upload logic before production use.
