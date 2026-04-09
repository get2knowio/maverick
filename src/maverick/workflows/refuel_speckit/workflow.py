"""RefuelSpeckitWorkflow — spec-to-beads pipeline."""

from __future__ import annotations

from typing import Any

from maverick.agents.generators.dependency_extractor import DependencyExtractor
from maverick.exceptions import WorkflowError
from maverick.library.actions.beads import (
    create_beads,
    enrich_bead_descriptions,
    parse_speckit,
    wire_dependencies,
)
from maverick.library.actions.git import create_git_branch, git_commit, git_merge
from maverick.logging import get_logger
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.refuel_speckit.constants import (
    CHECKOUT,
    CHECKOUT_MAIN,
    COMMIT,
    CREATE_BEADS,
    ENRICH_BEADS,
    EXTRACT_DEPS,
    MERGE,
    PARSE_SPEC,
    WIRE_DEPS,
    WORKFLOW_NAME,
)
from maverick.workflows.refuel_speckit.models import RefuelSpeckitResult

logger = get_logger(__name__)


class RefuelSpeckitWorkflow(PythonWorkflow):
    """Workflow that creates beads from a SpecKit specification directory.

    Follows a linear pipeline:
    1. checkout  - create/switch to the spec branch
    2. parse_spec - parse specs/<spec>/tasks.md into bead definitions
    3. extract_deps - extract inter-story dependencies (via step_executor or empty)
    4. enrich_beads - enrich bead descriptions with acceptance criteria
    5. create_beads - create epic and work beads via bd CLI
    6. wire_deps - wire dependencies between beads
    7. commit (skipped on dry_run) - commit bead data on spec branch
    8. checkout_main + merge (skipped on dry_run) - merge spec branch into main

    Args:
        config: Project configuration (MaverickConfig).
        registry: Component registry for action/agent dispatch.
        checkpoint_store: Optional checkpoint persistence backend.
        step_executor: Optional agent step executor (for dependency extraction).
        workflow_name: Identifier for this workflow instance.
    """

    def __init__(self, **kwargs: Any) -> None:
        if "workflow_name" not in kwargs:
            kwargs["workflow_name"] = WORKFLOW_NAME
        super().__init__(**kwargs)

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the refuel-speckit pipeline.

        Args:
            inputs: Workflow inputs. Required: ``spec`` (str). Optional:
                ``dry_run`` (bool, default False).

        Returns:
            Output dict with epic, work_beads, dependencies, errors,
            commit, and merge keys.

        Raises:
            WorkflowError: If ``spec`` is not provided in inputs.
            RuntimeError: If spec directory or tasks.md is invalid.
        """
        spec: str = inputs.get("spec", "")
        if not spec:
            raise WorkflowError("'spec' input is required")
        dry_run: bool = bool(inputs.get("dry_run", False))

        # ------------------------------------------------------------------
        # Step 1: Checkout spec branch
        # ------------------------------------------------------------------
        await self.emit_step_started(CHECKOUT)
        try:
            checkout_result = await create_git_branch(branch_name=spec)
        except Exception as exc:
            await self.emit_step_failed(CHECKOUT, str(exc))
            raise
        await self.emit_step_completed(CHECKOUT, output=checkout_result)

        # ------------------------------------------------------------------
        # Step 2: Parse spec directory
        # ------------------------------------------------------------------
        await self.emit_step_started(PARSE_SPEC)
        try:
            parse_result = await parse_speckit(spec_dir=f"specs/{spec}")
        except Exception as exc:
            await self.emit_step_failed(PARSE_SPEC, str(exc))
            raise
        await self.emit_step_completed(PARSE_SPEC, output=parse_result)

        # ------------------------------------------------------------------
        # Step 3: Extract dependencies (via step_executor or empty fallback)
        # ------------------------------------------------------------------
        await self.emit_step_started(EXTRACT_DEPS)
        extracted_deps: str = ""
        if parse_result.dependency_section:
            try:
                from maverick.executor import create_default_executor

                extractor = DependencyExtractor()
                dep_executor = create_default_executor()
                try:
                    dep_result = await dep_executor.execute(
                        step_name="extract_deps",
                        agent_name=extractor.name,
                        prompt={"dependency_section": parse_result.dependency_section},
                    )
                    extracted_deps = str(dep_result.output) if dep_result.output else ""
                finally:
                    await dep_executor.cleanup()
            except Exception as exc:
                logger.warning("dep_extraction_failed", error=str(exc))
                extracted_deps = ""
        await self.emit_step_completed(EXTRACT_DEPS, output=extracted_deps)

        # ------------------------------------------------------------------
        # Step 4: Enrich bead descriptions
        # ------------------------------------------------------------------
        await self.emit_step_started(ENRICH_BEADS)
        try:
            enriched_definitions = await enrich_bead_descriptions(
                work_definitions=list(parse_result.work_definitions),
                spec_dir=f"specs/{spec}",
                dependency_section=parse_result.dependency_section,
            )
        except Exception as exc:
            await self.emit_step_failed(ENRICH_BEADS, str(exc))
            raise
        await self.emit_step_completed(ENRICH_BEADS, output=enriched_definitions)

        # ------------------------------------------------------------------
        # Step 5: Create beads
        # ------------------------------------------------------------------
        await self.emit_step_started(CREATE_BEADS)
        try:
            bead_result = await create_beads(
                epic_definition=parse_result.epic_definition,
                work_definitions=enriched_definitions,
                dry_run=dry_run,
            )
        except Exception as exc:
            await self.emit_step_failed(CREATE_BEADS, str(exc))
            raise
        await self.emit_step_completed(CREATE_BEADS, output=bead_result)

        # ------------------------------------------------------------------
        # Step 6: Wire dependencies (only if epic was created)
        # ------------------------------------------------------------------
        wire_result = None
        if bead_result.epic is not None:
            await self.emit_step_started(WIRE_DEPS)
            try:
                wire_result = await wire_dependencies(
                    work_definitions=enriched_definitions,
                    created_map=bead_result.created_map,
                    tasks_content=parse_result.tasks_content,
                    extracted_deps=extracted_deps,
                    dry_run=dry_run,
                )
            except Exception as exc:
                await self.emit_step_failed(WIRE_DEPS, str(exc))
                raise
            await self.emit_step_completed(WIRE_DEPS, output=wire_result)

        # ------------------------------------------------------------------
        # Steps 7-9: Commit and merge (skipped in dry_run mode)
        # ------------------------------------------------------------------
        commit_sha: str | None = None
        merge_sha: str | None = None

        if not dry_run:
            # Step 7: Commit bead data on spec branch
            await self.emit_step_started(COMMIT)
            try:
                commit_result = await git_commit(
                    message=f"refuel(speckit): create beads for {spec}"
                )
            except Exception as exc:
                await self.emit_step_failed(COMMIT, str(exc))
                raise
            commit_sha = commit_result.get("commit_sha")
            await self.emit_step_completed(COMMIT, output=commit_result)

            # Step 8: Checkout main
            await self.emit_step_started(CHECKOUT_MAIN)
            try:
                await create_git_branch(branch_name="main")
            except Exception as exc:
                await self.emit_step_failed(CHECKOUT_MAIN, str(exc))
                raise
            await self.emit_step_completed(CHECKOUT_MAIN, output={"branch_name": "main"})

            # Step 9: Merge spec branch into main
            await self.emit_step_started(MERGE)
            try:
                merge_result = await git_merge(branch=spec)
            except Exception as exc:
                await self.emit_step_failed(MERGE, str(exc))
                raise
            merge_sha = merge_result.get("merge_commit")
            await self.emit_step_completed(MERGE, output=merge_result)

        # ------------------------------------------------------------------
        # Return final output
        # ------------------------------------------------------------------
        result = RefuelSpeckitResult(
            epic=bead_result.epic,
            work_beads=tuple(bead_result.work_beads),
            dependencies=tuple(wire_result.dependencies) if wire_result else (),
            errors=tuple(bead_result.errors),
            commit=commit_sha,
            merge=merge_sha,
        )
        return result.to_dict()
