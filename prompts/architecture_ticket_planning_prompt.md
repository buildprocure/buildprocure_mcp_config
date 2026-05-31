# Architecture Ticket Planning

Use `create_architecture_child_tickets` when a migration epic or parent story needs child Azure Boards tickets.

## Ownership

- The Architecture Agent recommends sequencing and creates child tickets.
- The Migration Orchestrator executes a selected implementation ticket.
- Assignment is optional. Leave tickets unassigned unless the user passes `assigned_to`.

## Safe Workflow

Start with `dry_run: true` to review suggested tickets.

```json
{
  "parent_work_item_id": 55,
  "repo_name": "procurex",
  "migration_goal": "Migrate Buyer BOQ to React",
  "target_ref": "main",
  "module_name": "Buyer BOQ",
  "module_path": "Buyer",
  "dry_run": true,
  "include_database_schema": true
}
```

After the user confirms, call the same tool with `dry_run: false`.

## Output Expectations

- Return suggested tickets first.
- If tickets are created, return created work item IDs and URLs.
- Do not run implementation agents from this tool.
- Do not assign tickets unless `assigned_to` is explicitly provided.
