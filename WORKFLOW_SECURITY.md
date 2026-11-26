# LUMO Workflow Security (Phase 27)

- **No Arbitrary Execution**: Uploaded files (`guardian_file`) and datasets (`data_intelligence`) are capped at `2 MB`, processed in auto-cleaned temporary directories, and never executed.
- **URL Safety**: `guardian_url` validates URLs statically via `validate_guardian_url(..., resolve_dns=False)` without fetching arbitrary remote pages.
- **Data Isolation**: Workflows are scoped by `owner_id` (`X-LUMO-Owner`, defaulting to `"local"`).
- **Permissions**: API keys enforce `workflows:read` for reads/exports and `workflows:execute` for planning, execution, cancellation, retry, and deletion.
- **Bounded Execution**: Topological wave loop is strictly bounded by step count; no uncontrolled autonomous agent loops.
