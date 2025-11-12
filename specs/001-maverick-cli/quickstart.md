# Quickstart: Maverick CLI (Click-based)

This guide shows how to run the Maverick CLI (implemented with the Click framework) inside the devcontainer against your repository and view progress. Future enhancements may introduce Rich styling or a Textual TUI; current commands remain stable.

## Prerequisites
- Running in this repository's devcontainer (Linux)
- Temporal dev server reachable (per project setup)
- Git repository with `specs/*/tasks.md`
- Clean working tree (or use `--allow-dirty` explicitly)

## Discover and Run

Human-readable mode:

```bash
maverick run
```

Start one specific task file:

```bash
maverick run --task specs/001-some-feature/tasks.md
```

Dry-run (no workflow calls) and JSON output:

```bash
maverick run --dry-run --json
```

Example JSON (fields order stable):

```json
{
	"tasks": [
		{
			"descriptor": {
				"task_id": "001-some-feature-tasks",
				"task_file": "/workspace/specs/001-some-feature/tasks.md",
				"spec_root": "/workspace/specs/001-some-feature",
				"branch_name": null
			},
			"context": {
				"return_to_branch": "main",
				"repo_root": "/workspace",
				"interactive": false,
				"model_prefs": null
			}
		}
	],
	"task_count": 1,
	"discovery_ms": 42
}
```

Interactive pauses between tasks:

```bash
maverick run --interactive
```

Allow running with a dirty working tree:

```bash
maverick run --allow-dirty
```

Compact streaming output:

```bash
maverick run --compact
```

Use Rich styling for enhanced output (requires `pip install rich`):

```bash
maverick run --rich
```

## Check Status Later

```bash
maverick status <workflow-id>
```

> `maverick run` always prints the workflow identifier so you can pass it to `maverick status`. Capture the line `Workflow started: wf-123 (run: run-abc)` (or the JSON field when using `--json`) and reuse the `wf-123` portion in later status calls.

Machine-readable status:

```bash
maverick status <workflow-id> --json
```

Example status JSON:

```json
	{
		"workflow_id": "wf-123",
		"run_id": "run-abc",
		"state": "running",
		"current_task_id": "001-some-feature-tasks",
		"current_phase": "implement",
		"last_activity": "2025-11-10T12:05:00Z",
		"updated_at": "2025-11-10T12:00:00Z",
		"tasks": [
			{
				"task_id": "001-some-feature-tasks",
				"status": "running",
				"last_message": {
					"text": "phase_started",
					"level": "info",
					"timestamp": "2025-11-10T12:05:00Z"
				}
			}
		],
		"status_poll_latency_ms_p95": 180,
		"errors_count": 0
	}
```

## Notes
- The CLI does not switch or create branches. It passes a hint; the workflow performs branch checkout per task.
- Use `--json` for scriptable outputs; metrics are included as top-level fields.
- If interrupted (Ctrl+C), the workflow continues. Use `maverick status <id>` to resume observation.
- Framework: Click. Styling kept minimal first; Rich/Textual can layer on later without breaking contracts.
