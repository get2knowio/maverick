"""Tests for ASCII diagram generator.

This module tests the ASCIIGenerator class which produces terminal-friendly
workflow diagrams using box-drawing characters.

Test Coverage:
- T045c: ASCIIGenerator tests (TDD)
- T057-T063: ASCII generator implementation tests
"""

from __future__ import annotations

import pytest

from maverick.dsl.serialization.schema import (
    AgentStepRecord,
    BranchOptionRecord,
    BranchStepRecord,
    GenerateStepRecord,
    InputDefinition,
    InputType,
    LoopStepRecord,
    PythonStepRecord,
    ValidateStepRecord,
    WorkflowFile,
)
from maverick.dsl.types import StepType
from maverick.dsl.visualization.ascii import ASCIIGenerator


class TestASCIIGeneratorBasics:
    """Test basic ASCIIGenerator functionality (T057)."""

    def test_create_generator_default_width(self) -> None:
        """Test creating generator with default width."""
        generator = ASCIIGenerator()
        assert generator.width == 60  # Default from FR-021

    def test_create_generator_custom_width(self) -> None:
        """Test creating generator with custom width."""
        generator = ASCIIGenerator(width=80)
        assert generator.width == 80

    def test_generate_empty_workflow_fails(self) -> None:
        """Test that generating from empty workflow fails validation."""
        # WorkflowFile requires at least one step, so this is caught by Pydantic
        with pytest.raises(ValueError, match="at least 1 item"):
            WorkflowFile(
                version="1.0",
                name="empty",
                description="",
                inputs={},
                steps=[],  # Invalid - needs at least one step
            )


class TestASCIIHeaderGeneration:
    """Test workflow header and metadata rendering (T063)."""

    def test_header_with_name_only(self) -> None:
        """Test header generation with workflow name only."""
        workflow = WorkflowFile(
            version="1.0",
            name="simple-workflow",
            description="",
            inputs={},
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_action",
                )
            ],
        )

        generator = ASCIIGenerator(width=50)
        result = generator.generate(workflow)

        # Check header contains workflow name
        assert "┌" in result
        assert "Workflow: simple-workflow" in result
        assert "┐" in result

    def test_header_with_description(self) -> None:
        """Test header includes description when present."""
        workflow = WorkflowFile(
            version="1.0",
            name="documented-workflow",
            description="A workflow with documentation",
            inputs={},
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_action",
                )
            ],
        )

        generator = ASCIIGenerator(width=60)
        result = generator.generate(workflow)

        assert "Workflow: documented-workflow" in result
        assert "A workflow with documentation" in result

    def test_header_box_drawing_characters(self) -> None:
        """Test correct box-drawing characters in header."""
        workflow = WorkflowFile(
            version="1.0",
            name="test",
            description="Test workflow",
            inputs={},
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="action",
                )
            ],
        )

        generator = ASCIIGenerator(width=50)
        result = generator.generate(workflow)

        # Check box drawing characters
        assert "┌─" in result  # Top-left corner
        assert "─┐" in result  # Top-right corner
        assert "├─" in result  # Left T-junction
        assert "─┤" in result  # Right T-junction
        assert "└─" in result  # Bottom-left corner
        assert "─┘" in result  # Bottom-right corner
        assert "│" in result  # Vertical lines


class TestASCIIInputDisplay:
    """Test input parameter display (T063)."""

    def test_no_inputs_section_omitted(self) -> None:
        """Test that inputs section is omitted when no inputs."""
        workflow = WorkflowFile(
            version="1.0",
            name="no-inputs",
            inputs={},
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="action",
                )
            ],
        )

        generator = ASCIIGenerator(width=50)
        result = generator.generate(workflow)

        # Should not have an Inputs section
        assert "Inputs:" not in result

    def test_single_required_input(self) -> None:
        """Test display of single required input."""
        workflow = WorkflowFile(
            version="1.0",
            name="with-input",
            inputs={
                "target": InputDefinition(
                    type=InputType.STRING,
                    required=True,
                    description="Target environment",
                )
            },
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="action",
                )
            ],
        )

        generator = ASCIIGenerator(width=60)
        result = generator.generate(workflow)

        assert "Inputs:" in result
        assert "target (string, required)" in result

    def test_input_with_default_value(self) -> None:
        """Test display of input with default value."""
        workflow = WorkflowFile(
            version="1.0",
            name="with-default",
            inputs={
                "verbose": InputDefinition(
                    type=InputType.BOOLEAN,
                    required=False,
                    default=False,
                )
            },
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="action",
                )
            ],
        )

        generator = ASCIIGenerator(width=60)
        result = generator.generate(workflow)

        assert "Inputs:" in result
        assert "verbose (boolean, default: False)" in result

    def test_multiple_inputs(self) -> None:
        """Test display of multiple inputs."""
        workflow = WorkflowFile(
            version="1.0",
            name="multi-input",
            inputs={
                "target": InputDefinition(
                    type=InputType.STRING,
                    required=True,
                ),
                "verbose": InputDefinition(
                    type=InputType.BOOLEAN,
                    required=False,
                    default=False,
                ),
                "retries": InputDefinition(
                    type=InputType.INTEGER,
                    required=False,
                    default=3,
                ),
            },
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="action",
                )
            ],
        )

        generator = ASCIIGenerator(width=70)
        result = generator.generate(workflow)

        assert "target (string, required)" in result
        assert "verbose (boolean, default: False)" in result
        assert "retries (integer, default: 3)" in result


class TestASCIIStepRendering:
    """Test step rendering with type annotations (T059)."""

    def test_python_step_rendering(self) -> None:
        """Test rendering of Python step."""
        workflow = WorkflowFile(
            version="1.0",
            name="python-step",
            steps=[
                PythonStepRecord(
                    name="process_data",
                    type=StepType.PYTHON,
                    action="process",
                )
            ],
        )

        generator = ASCIIGenerator(width=50)
        result = generator.generate(workflow)

        assert "1. [python] process_data" in result

    def test_agent_step_rendering(self) -> None:
        """Test rendering of Agent step."""
        workflow = WorkflowFile(
            version="1.0",
            name="agent-step",
            steps=[
                AgentStepRecord(
                    name="code_review",
                    type=StepType.AGENT,
                    agent="reviewer",
                )
            ],
        )

        generator = ASCIIGenerator(width=50)
        result = generator.generate(workflow)

        assert "1. [agent] code_review" in result

    def test_generate_step_rendering(self) -> None:
        """Test rendering of Generate step."""
        workflow = WorkflowFile(
            version="1.0",
            name="generate-step",
            steps=[
                GenerateStepRecord(
                    name="create_pr_body",
                    type=StepType.GENERATE,
                    generator="pr_generator",
                )
            ],
        )

        generator = ASCIIGenerator(width=50)
        result = generator.generate(workflow)

        assert "1. [generate] create_pr_body" in result

    def test_validate_step_rendering(self) -> None:
        """Test rendering of Validate step."""
        workflow = WorkflowFile(
            version="1.0",
            name="validate-step",
            steps=[
                ValidateStepRecord(
                    name="check_format",
                    type=StepType.VALIDATE,
                    stages=["format", "lint"],
                )
            ],
        )

        generator = ASCIIGenerator(width=50)
        result = generator.generate(workflow)

        assert "1. [validate] check_format" in result


class TestASCIIArrowRendering:
    """Test arrow and connector rendering (T060)."""

    def test_sequential_arrows(self) -> None:
        """Test sequential step arrows."""
        workflow = WorkflowFile(
            version="1.0",
            name="sequential",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="action1",
                ),
                PythonStepRecord(
                    name="step2",
                    type=StepType.PYTHON,
                    action="action2",
                ),
                PythonStepRecord(
                    name="step3",
                    type=StepType.PYTHON,
                    action="action3",
                ),
            ],
        )

        generator = ASCIIGenerator(width=50)
        result = generator.generate(workflow)

        # Should have downward arrows between steps
        assert "↓" in result
        # Should have numbered steps
        assert "1. [python] step1" in result
        assert "2. [python] step2" in result
        assert "3. [python] step3" in result


class TestASCIIConditionalAnnotations:
    """Test conditional and retry annotation rendering (T061)."""

    def test_conditional_step_annotation(self) -> None:
        """Test when clause annotation."""
        workflow = WorkflowFile(
            version="1.0",
            name="conditional",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="action1",
                ),
                AgentStepRecord(
                    name="optional_review",
                    type=StepType.AGENT,
                    agent="reviewer",
                    when="inputs.enable_review",
                ),
            ],
        )

        generator = ASCIIGenerator(width=60)
        result = generator.generate(workflow)

        # Should show when clause
        assert "when: inputs.enable_review" in result

    def test_validate_with_retry(self) -> None:
        """Test validate step with retry count."""
        workflow = WorkflowFile(
            version="1.0",
            name="validate-retry",
            steps=[
                ValidateStepRecord(
                    name="check_tests",
                    type=StepType.VALIDATE,
                    stages=["test"],
                    retry=3,
                )
            ],
        )

        generator = ASCIIGenerator(width=60)
        result = generator.generate(workflow)

        # Should show retry count
        assert "retry: 3" in result or "retry=3" in result

    def test_validate_with_on_failure_step(self) -> None:
        """Test validate step with on_failure substep."""
        workflow = WorkflowFile(
            version="1.0",
            name="validate-fix",
            steps=[
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=["format", "lint"],
                    retry=3,
                    on_failure=AgentStepRecord(
                        name="fix_issues",
                        type=StepType.AGENT,
                        agent="fixer",
                    ),
                )
            ],
        )

        generator = ASCIIGenerator(width=70)
        result = generator.generate(workflow)

        # Should show on_failure step
        assert "fix_issues" in result
        # Should indicate retry loop
        assert "retry" in result.lower()


class TestASCIIBranchRendering:
    """Test branch step rendering (T062)."""

    def test_branch_step_with_options(self) -> None:
        """Test branch step with multiple options."""
        workflow = WorkflowFile(
            version="1.0",
            name="branching",
            steps=[
                BranchStepRecord(
                    name="deploy_branch",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="inputs.env == 'prod'",
                            step=PythonStepRecord(
                                name="deploy_prod",
                                type=StepType.PYTHON,
                                action="deploy_production",
                            ),
                        ),
                        BranchOptionRecord(
                            when="inputs.env == 'staging'",
                            step=PythonStepRecord(
                                name="deploy_staging",
                                type=StepType.PYTHON,
                                action="deploy_staging",
                            ),
                        ),
                    ],
                )
            ],
        )

        generator = ASCIIGenerator(width=80)
        result = generator.generate(workflow)

        # Should show branch step
        assert "[branch] deploy_branch" in result
        # Should show options with conditions
        assert "inputs.env == 'prod'" in result
        assert "inputs.env == 'staging'" in result


class TestASCIIParallelRendering:
    """Test parallel step rendering (T062)."""

    def test_loop_step_indentation(self) -> None:
        """Test parallel step with substeps."""
        workflow = WorkflowFile(
            version="1.0",
            name="parallel",
            steps=[
                LoopStepRecord(
                    name="parallel_review",
                    type=StepType.LOOP,
                    steps=[
                        AgentStepRecord(
                            name="arch_review",
                            type=StepType.AGENT,
                            agent="arch_reviewer",
                        ),
                        PythonStepRecord(
                            name="lint_review",
                            type=StepType.PYTHON,
                            action="run_linter",
                        ),
                    ],
                )
            ],
        )

        generator = ASCIIGenerator(width=70)
        result = generator.generate(workflow)

        # Should show loop step
        assert "[loop] parallel_review" in result
        # Should show substeps (may be indented or marked)
        assert "arch_review" in result
        assert "lint_review" in result


class TestASCIIBoxDrawing:
    """Test box drawing with configurable width (T058)."""

    def test_respects_width_constraint(self) -> None:
        """Test that output respects width constraint."""
        workflow = WorkflowFile(
            version="1.0",
            name="width-test",
            description="Test width constraint handling",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="action",
                )
            ],
        )

        generator = ASCIIGenerator(width=40)
        result = generator.generate(workflow)

        # Check that lines don't exceed width
        for line in result.split("\n"):
            # Allow some tolerance for box drawing characters
            assert len(line) <= 42, f"Line exceeds width: {line}"

    def test_minimum_width_handling(self) -> None:
        """Test handling of very small width."""
        workflow = WorkflowFile(
            version="1.0",
            name="x",
            steps=[
                PythonStepRecord(
                    name="s",
                    type=StepType.PYTHON,
                    action="a",
                )
            ],
        )

        # Should not crash with small width
        generator = ASCIIGenerator(width=20)
        result = generator.generate(workflow)
        assert len(result) > 0

    def test_large_width_handling(self) -> None:
        """Test handling of large width."""
        workflow = WorkflowFile(
            version="1.0",
            name="test",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="action",
                )
            ],
        )

        generator = ASCIIGenerator(width=120)
        result = generator.generate(workflow)
        assert len(result) > 0
        assert "Workflow: test" in result


class TestASCIIComplexWorkflows:
    """Test complex workflow rendering."""

    def test_full_workflow_example(self) -> None:
        """Test rendering of complete workflow from spec."""
        workflow = WorkflowFile(
            version="1.0",
            name="feature-implementation",
            description="Implement a feature from tasks.md",
            inputs={
                "spec_dir": InputDefinition(
                    type=InputType.STRING,
                    required=True,
                ),
                "dry_run": InputDefinition(
                    type=InputType.BOOLEAN,
                    required=False,
                    default=False,
                ),
            },
            steps=[
                PythonStepRecord(
                    name="load_tasks",
                    type=StepType.PYTHON,
                    action="load_task_file",
                ),
                AgentStepRecord(
                    name="implement",
                    type=StepType.AGENT,
                    agent="implementer",
                    when="not inputs.dry_run",
                ),
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=["format", "lint", "test"],
                    retry=3,
                    on_failure=AgentStepRecord(
                        name="fixer",
                        type=StepType.AGENT,
                        agent="fixer_agent",
                    ),
                ),
                LoopStepRecord(
                    name="review",
                    type=StepType.LOOP,
                    steps=[
                        AgentStepRecord(
                            name="architecture_review",
                            type=StepType.AGENT,
                            agent="arch_reviewer",
                        ),
                        PythonStepRecord(
                            name="lint_review",
                            type=StepType.PYTHON,
                            action="run_lint_review",
                        ),
                    ],
                ),
                PythonStepRecord(
                    name="deploy",
                    type=StepType.PYTHON,
                    action="deploy_changes",
                ),
            ],
        )

        generator = ASCIIGenerator(width=60)
        result = generator.generate(workflow)

        # Verify all major sections are present
        assert "Workflow: feature-implementation" in result
        assert "Implement a feature from tasks.md" in result
        assert "Inputs:" in result
        assert "spec_dir (string, required)" in result
        assert "dry_run (boolean, default: False)" in result

        # Verify all steps are present
        assert "[python] load_tasks" in result
        assert "[agent] implement" in result
        assert "[validate] validate" in result
        assert "[loop] review" in result
        assert "[python] deploy" in result

        # Verify conditions
        assert "when: not inputs.dry_run" in result

        # Verify on_failure
        assert "fixer" in result

    def test_nested_structures(self) -> None:
        """Test deeply nested workflow structures."""
        workflow = WorkflowFile(
            version="1.0",
            name="nested",
            steps=[
                BranchStepRecord(
                    name="branch1",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="inputs.option == 'a'",
                            step=LoopStepRecord(
                                name="parallel_a",
                                type=StepType.LOOP,
                                steps=[
                                    PythonStepRecord(
                                        name="a1",
                                        type=StepType.PYTHON,
                                        action="action_a1",
                                    ),
                                    PythonStepRecord(
                                        name="a2",
                                        type=StepType.PYTHON,
                                        action="action_a2",
                                    ),
                                ],
                            ),
                        ),
                    ],
                )
            ],
        )

        generator = ASCIIGenerator(width=80)
        result = generator.generate(workflow)

        # Should handle nested structures without crashing
        assert len(result) > 0
        assert "[branch] branch1" in result
        assert "[loop] parallel_a" in result or "a1" in result
