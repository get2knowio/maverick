"""Tests for Mermaid diagram generator.

This module tests the MermaidGenerator class that converts WorkflowGraph
structures into Mermaid flowchart syntax.
"""

from __future__ import annotations

import pytest

from maverick.dsl.visualization import (
    EdgeType,
    GraphEdge,
    GraphNode,
    WorkflowGraph,
)
from maverick.dsl.visualization.mermaid import MermaidGenerator

# =============================================================================
# Test MermaidGenerator
# =============================================================================


class TestMermaidGenerator:
    """Test suite for MermaidGenerator."""

    def test_generate_simple_workflow(self) -> None:
        """Test generating Mermaid diagram for simple workflow."""
        node = GraphNode(id="step1", label="Process Data", step_type="python")
        graph = WorkflowGraph(
            name="simple",
            description="Simple workflow",
            nodes=(node,),
            edges=(
                GraphEdge(source="START", target="step1"),
                GraphEdge(source="step1", target="END"),
            ),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        assert "flowchart TD" in output
        assert "START((Start))" in output
        assert "END((End))" in output
        assert "step1[Process Data]" in output
        assert "START --> step1" in output
        assert "step1 --> END" in output

    def test_generate_with_direction_lr(self) -> None:
        """Test generating diagram with left-to-right direction."""
        node = GraphNode(id="step1", label="Test", step_type="python")
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(
                GraphEdge(source="START", target="step1"),
                GraphEdge(source="step1", target="END"),
            ),
        )

        generator = MermaidGenerator(direction="LR")
        output = generator.generate(graph)

        assert "flowchart LR" in output

    def test_generate_with_direction_td(self) -> None:
        """Test generating diagram with top-down direction (default)."""
        node = GraphNode(id="step1", label="Test", step_type="python")
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(GraphEdge(source="START", target="step1"),),
        )

        generator = MermaidGenerator(direction="TD")
        output = generator.generate(graph)

        assert "flowchart TD" in output

    def test_generate_python_step_uses_rectangle(self) -> None:
        """Test that Python steps use rectangle shape [label]."""
        node = GraphNode(id="process", label="Process Data", step_type="python")
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        assert "process[Process Data]" in output

    def test_generate_agent_step_uses_rectangle(self) -> None:
        """Test that Agent steps use rectangle shape [label]."""
        node = GraphNode(id="analyze", label="Analyze Code", step_type="agent")
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        assert "analyze[Analyze Code]" in output

    def test_generate_generate_step_uses_rectangle(self) -> None:
        """Test that Generate steps use rectangle shape [label]."""
        node = GraphNode(id="gen", label="Generate Docs", step_type="generate")
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        assert "gen[Generate Docs]" in output

    def test_generate_conditional_step_uses_diamond(self) -> None:
        """Test that conditional steps use diamond shape {label}."""
        node = GraphNode(
            id="check",
            label="Check Result",
            step_type="validate",
            is_conditional=True,
            condition="result.valid",
        )
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        assert "check{Check Result}" in output

    def test_generate_validate_step_uses_diamond(self) -> None:
        """Test that validate steps use diamond shape by default."""
        node = GraphNode(id="validate", label="Validate", step_type="validate")
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Validate steps are conditional by nature
        assert "validate{Validate}" in output or "validate[Validate]" in output

    def test_generate_loop_step_uses_subgraph(self) -> None:
        """Test that parallel steps generate a subgraph."""
        child1 = GraphNode(id="task1", label="Task 1", step_type="python")
        child2 = GraphNode(id="task2", label="Task 2", step_type="python")
        parallel_node = GraphNode(
            id="parallel",
            label="Run Parallel",
            step_type="parallel",
            children=(child1, child2),
        )
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(parallel_node, child1, child2),
            edges=(
                GraphEdge(source="START", target="parallel"),
                GraphEdge(source="parallel", target="END"),
            ),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        assert "subgraph" in output
        assert "task1[Task 1]" in output
        assert "task2[Task 2]" in output

    def test_generate_sequential_edges(self) -> None:
        """Test that sequential edges use simple arrow -->."""
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(
                GraphNode(id="step1", label="Step 1", step_type="python"),
                GraphNode(id="step2", label="Step 2", step_type="python"),
            ),
            edges=(
                GraphEdge(
                    source="step1", target="step2", edge_type=EdgeType.SEQUENTIAL
                ),
            ),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        assert "step1 --> step2" in output

    def test_generate_conditional_edges_with_label(self) -> None:
        """Test that conditional edges include labels with |label| syntax."""
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(
                GraphNode(
                    id="check", label="Check", step_type="validate", is_conditional=True
                ),
                GraphNode(id="success", label="Success", step_type="python"),
                GraphNode(id="fail", label="Fail", step_type="python"),
            ),
            edges=(
                GraphEdge(
                    source="check",
                    target="success",
                    label="pass",
                    edge_type=EdgeType.CONDITIONAL,
                ),
                GraphEdge(
                    source="check",
                    target="fail",
                    label="fail",
                    edge_type=EdgeType.CONDITIONAL,
                ),
            ),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        assert "check -->|pass| success" in output
        assert "check -->|fail| fail" in output

    def test_generate_retry_edge(self) -> None:
        """Test that retry edges create a loop back to the node."""
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(
                GraphNode(id="validate", label="Validate", step_type="validate"),
                GraphNode(id="fix", label="Fix Issues", step_type="python"),
            ),
            edges=(
                GraphEdge(
                    source="validate",
                    target="fix",
                    label="fail",
                    edge_type=EdgeType.RETRY,
                ),
                GraphEdge(source="fix", target="validate", edge_type=EdgeType.RETRY),
            ),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Retry loop should be present
        assert "validate" in output
        assert "fix" in output
        # Should have edges forming a loop
        assert "-->" in output

    def test_generate_branch_edges(self) -> None:
        """Test that branch edges are properly labeled."""
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(
                GraphNode(id="decide", label="Decide", step_type="branch"),
                GraphNode(id="option1", label="Option 1", step_type="python"),
                GraphNode(id="option2", label="Option 2", step_type="python"),
            ),
            edges=(
                GraphEdge(
                    source="decide",
                    target="option1",
                    label="env == prod",
                    edge_type=EdgeType.BRANCH,
                ),
                GraphEdge(
                    source="decide",
                    target="option2",
                    label="env == dev",
                    edge_type=EdgeType.BRANCH,
                ),
            ),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        assert "decide -->|env == prod| option1" in output
        assert "decide -->|env == dev| option2" in output

    def test_generate_subworkflow_step(self) -> None:
        """Test that subworkflow steps are properly rendered."""
        node = GraphNode(id="sub", label="Sub Workflow", step_type="subworkflow")
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(
                GraphEdge(source="START", target="sub"),
                GraphEdge(source="sub", target="END"),
            ),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Subworkflow could use rectangle or special shape
        assert "sub" in output
        assert "Sub Workflow" in output

    def test_generate_escapes_special_characters(self) -> None:
        """Test that special characters in labels are properly escaped."""
        node = GraphNode(
            id="step1",
            label="Process [Data] & Validate",
            step_type="python",
        )
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Special characters should be escaped or handled
        assert "step1" in output

    def test_generate_complex_workflow(self) -> None:
        """Test generating diagram for complex workflow with multiple step types."""
        nodes = (
            GraphNode(id="setup", label="Setup", step_type="python"),
            GraphNode(
                id="parallel",
                label="Parallel Tasks",
                step_type="parallel",
                children=(
                    GraphNode(id="task1", label="Task 1", step_type="agent"),
                    GraphNode(id="task2", label="Task 2", step_type="generate"),
                ),
            ),
            GraphNode(id="task1", label="Task 1", step_type="agent"),
            GraphNode(id="task2", label="Task 2", step_type="generate"),
            GraphNode(
                id="validate",
                label="Validate",
                step_type="validate",
                is_conditional=True,
            ),
            GraphNode(id="deploy", label="Deploy", step_type="python"),
        )
        edges = (
            GraphEdge(source="START", target="setup"),
            GraphEdge(source="setup", target="parallel"),
            GraphEdge(source="parallel", target="validate"),
            GraphEdge(
                source="validate",
                target="deploy",
                label="pass",
                edge_type=EdgeType.CONDITIONAL,
            ),
            GraphEdge(source="deploy", target="END"),
        )
        graph = WorkflowGraph(
            name="complex",
            description="Complex workflow",
            nodes=nodes,
            edges=edges,
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Verify structure
        assert "flowchart TD" in output
        assert "START((Start))" in output
        assert "END((End))" in output
        assert "setup[Setup]" in output
        assert "validate{Validate}" in output or "validate[Validate]" in output
        assert "deploy[Deploy]" in output
        assert "subgraph" in output  # For parallel

    def test_generate_empty_graph(self) -> None:
        """Test generating diagram for empty graph."""
        graph = WorkflowGraph(
            name="empty",
            description="",
            nodes=(),
            edges=(),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Should still have basic structure
        assert "flowchart TD" in output
        assert "START((Start))" in output
        assert "END((End))" in output

    def test_generate_with_comments(self) -> None:
        """Test that generated output includes helpful comments."""
        node = GraphNode(id="step1", label="Test", step_type="python")
        graph = WorkflowGraph(
            name="test-workflow",
            description="A test workflow",
            nodes=(node,),
            edges=(),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Should include workflow name/description as comment
        assert "test-workflow" in output or "A test workflow" in output

    def test_generate_handles_long_labels(self) -> None:
        """Test that long labels are properly handled."""
        node = GraphNode(
            id="step1",
            label="This is a very long step label that should be handled properly",
            step_type="python",
        )
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Should handle long labels without breaking syntax
        assert "step1" in output

    def test_generate_preserves_node_order(self) -> None:
        """Test that node order in graph is preserved in output."""
        nodes = (
            GraphNode(id="first", label="First", step_type="python"),
            GraphNode(id="second", label="Second", step_type="python"),
            GraphNode(id="third", label="Third", step_type="python"),
        )
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=nodes,
            edges=(),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Find positions of node definitions in output
        first_pos = output.index("first[")
        second_pos = output.index("second[")
        third_pos = output.index("third[")

        assert first_pos < second_pos < third_pos

    def test_generate_multiple_times_same_result(self) -> None:
        """Test that generating same graph multiple times produces same result."""
        node = GraphNode(id="step1", label="Test", step_type="python")
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(
                GraphEdge(source="START", target="step1"),
                GraphEdge(source="step1", target="END"),
            ),
        )

        generator = MermaidGenerator()
        output1 = generator.generate(graph)
        output2 = generator.generate(graph)

        assert output1 == output2

    def test_invalid_direction_raises_error(self) -> None:
        """Test that invalid direction raises ValueError."""
        with pytest.raises(ValueError):
            MermaidGenerator(direction="INVALID")

    def test_supported_directions(self) -> None:
        """Test that all supported directions work."""
        node = GraphNode(id="step1", label="Test", step_type="python")
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(),
        )

        # Test TD
        gen_td = MermaidGenerator(direction="TD")
        output_td = gen_td.generate(graph)
        assert "flowchart TD" in output_td

        # Test LR
        gen_lr = MermaidGenerator(direction="LR")
        output_lr = gen_lr.generate(graph)
        assert "flowchart LR" in output_lr

    def test_node_id_sanitization(self) -> None:
        """Test that node IDs with special characters are sanitized."""
        # Node IDs should already be valid, but test defensive handling
        node = GraphNode(
            id="step-with-dashes",
            label="Step With Dashes",
            step_type="python",
        )
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(node,),
            edges=(),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Should handle dashes in IDs
        assert "step-with-dashes" in output or "step_with_dashes" in output

    def test_edge_without_label(self) -> None:
        """Test that edges without labels use simple arrow."""
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=(
                GraphNode(id="step1", label="Step 1", step_type="python"),
                GraphNode(id="step2", label="Step 2", step_type="python"),
            ),
            edges=(GraphEdge(source="step1", target="step2", label=""),),
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Should use simple arrow without label
        assert "step1 --> step2" in output
        assert "step1 -->||" not in output

    def test_all_edge_types_render(self) -> None:
        """Test that all EdgeType enum values can be rendered."""
        nodes = (
            GraphNode(id="n1", label="N1", step_type="python"),
            GraphNode(id="n2", label="N2", step_type="python"),
            GraphNode(id="n3", label="N3", step_type="python"),
            GraphNode(id="n4", label="N4", step_type="python"),
        )
        edges = (
            GraphEdge(source="n1", target="n2", edge_type=EdgeType.SEQUENTIAL),
            GraphEdge(
                source="n2", target="n3", edge_type=EdgeType.CONDITIONAL, label="cond"
            ),
            GraphEdge(
                source="n3", target="n4", edge_type=EdgeType.BRANCH, label="branch"
            ),
            GraphEdge(
                source="n4", target="n3", edge_type=EdgeType.RETRY, label="retry"
            ),
        )
        graph = WorkflowGraph(
            name="test",
            description="",
            nodes=nodes,
            edges=edges,
        )

        generator = MermaidGenerator()
        output = generator.generate(graph)

        # Should successfully generate without errors
        assert "flowchart" in output
        assert "n1" in output
        assert "n2" in output
        assert "n3" in output
        assert "n4" in output
