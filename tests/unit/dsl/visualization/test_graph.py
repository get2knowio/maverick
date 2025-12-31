"""Tests for WorkflowGraphBuilder.

This module tests the graph building functionality that converts WorkflowFile
models into GraphNode/GraphEdge structures for visualization.
"""

from __future__ import annotations

import pytest

from maverick.dsl.serialization.schema import (
    AgentStepRecord,
    BranchOptionRecord,
    BranchStepRecord,
    GenerateStepRecord,
    ParallelStepRecord,
    PythonStepRecord,
    SubWorkflowStepRecord,
    ValidateStepRecord,
    WorkflowFile,
)
from maverick.dsl.types import StepType
from maverick.dsl.visualization import (
    EdgeType,
    GraphEdge,
    GraphNode,
    WorkflowGraph,
    WorkflowGraphBuilder,
)

# =============================================================================
# Test Data Structures
# =============================================================================


class TestEdgeType:
    """Test suite for EdgeType enum."""

    def test_all_enum_values_exist(self) -> None:
        """Test that all expected enum values are defined."""
        assert hasattr(EdgeType, "SEQUENTIAL")
        assert hasattr(EdgeType, "CONDITIONAL")
        assert hasattr(EdgeType, "RETRY")
        assert hasattr(EdgeType, "BRANCH")

    def test_enum_values_are_strings(self) -> None:
        """Test that enum values are strings with expected values."""
        assert EdgeType.SEQUENTIAL == "sequential"
        assert EdgeType.CONDITIONAL == "conditional"
        assert EdgeType.RETRY == "retry"
        assert EdgeType.BRANCH == "branch"


class TestGraphNode:
    """Test suite for GraphNode dataclass."""

    def test_create_minimal_node(self) -> None:
        """Test creating a node with minimal required fields."""
        node = GraphNode(id="step1", label="Process Data", step_type="python")
        assert node.id == "step1"
        assert node.label == "Process Data"
        assert node.step_type == "python"
        assert node.is_conditional is False
        assert node.condition is None
        assert node.children == ()

    def test_create_conditional_node(self) -> None:
        """Test creating a conditional node with condition."""
        node = GraphNode(
            id="step2",
            label="Validate",
            step_type="validate",
            is_conditional=True,
            condition="result.success",
        )
        assert node.is_conditional is True
        assert node.condition == "result.success"

    def test_create_node_with_children(self) -> None:
        """Test creating a node with child nodes."""
        child1 = GraphNode(id="child1", label="Child 1", step_type="python")
        child2 = GraphNode(id="child2", label="Child 2", step_type="agent")
        parent = GraphNode(
            id="parent",
            label="Parent",
            step_type="branch",
            children=(child1, child2),
        )
        assert len(parent.children) == 2
        assert parent.children[0].id == "child1"
        assert parent.children[1].id == "child2"

    def test_node_is_frozen(self) -> None:
        """Test that GraphNode is immutable (frozen dataclass)."""
        node = GraphNode(id="step1", label="Test", step_type="python")
        with pytest.raises(AttributeError):
            node.id = "step2"  # type: ignore


class TestGraphEdge:
    """Test suite for GraphEdge dataclass."""

    def test_create_minimal_edge(self) -> None:
        """Test creating an edge with minimal required fields."""
        edge = GraphEdge(source="step1", target="step2")
        assert edge.source == "step1"
        assert edge.target == "step2"
        assert edge.label == ""
        assert edge.edge_type == EdgeType.SEQUENTIAL

    def test_create_edge_with_label(self) -> None:
        """Test creating an edge with label."""
        edge = GraphEdge(source="step1", target="step2", label="success")
        assert edge.label == "success"

    def test_create_conditional_edge(self) -> None:
        """Test creating a conditional edge."""
        edge = GraphEdge(
            source="step1",
            target="step2",
            label="if valid",
            edge_type=EdgeType.CONDITIONAL,
        )
        assert edge.edge_type == EdgeType.CONDITIONAL
        assert edge.label == "if valid"

    def test_edge_is_frozen(self) -> None:
        """Test that GraphEdge is immutable (frozen dataclass)."""
        edge = GraphEdge(source="step1", target="step2")
        with pytest.raises(AttributeError):
            edge.source = "step3"  # type: ignore


class TestWorkflowGraph:
    """Test suite for WorkflowGraph dataclass."""

    def test_create_minimal_graph(self) -> None:
        """Test creating a graph with minimal required fields."""
        node = GraphNode(id="step1", label="Test", step_type="python")
        edge = GraphEdge(source="START", target="step1")
        graph = WorkflowGraph(
            name="test-workflow",
            description="Test workflow",
            nodes=(node,),
            edges=(edge,),
        )
        assert graph.name == "test-workflow"
        assert graph.description == "Test workflow"
        assert len(graph.nodes) == 1
        assert len(graph.edges) == 1

    def test_create_empty_graph(self) -> None:
        """Test creating a graph with no nodes or edges."""
        graph = WorkflowGraph(
            name="empty",
            description="",
            nodes=(),
            edges=(),
        )
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_graph_is_frozen(self) -> None:
        """Test that WorkflowGraph is immutable (frozen dataclass)."""
        graph = WorkflowGraph(name="test", description="", nodes=(), edges=())
        with pytest.raises(AttributeError):
            graph.name = "new-name"  # type: ignore


# =============================================================================
# Test WorkflowGraphBuilder
# =============================================================================


class TestWorkflowGraphBuilder:
    """Test suite for WorkflowGraphBuilder."""

    def test_build_simple_python_step(self) -> None:
        """Test building graph from workflow with single Python step."""
        workflow = WorkflowFile(
            version="1.0",
            name="simple-workflow",
            description="Simple test workflow",
            steps=[
                PythonStepRecord(
                    name="process_data",
                    type=StepType.PYTHON,
                    action="process_data_fn",
                ),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        assert graph.name == "simple-workflow"
        assert graph.description == "Simple test workflow"
        assert len(graph.nodes) == 1
        assert graph.nodes[0].id == "process_data"
        assert graph.nodes[0].label == "process_data"
        assert graph.nodes[0].step_type == "python"
        assert len(graph.edges) == 2  # START -> step, step -> END

    def test_build_sequential_steps(self) -> None:
        """Test building graph from workflow with sequential steps."""
        workflow = WorkflowFile(
            version="1.0",
            name="sequential",
            steps=[
                PythonStepRecord(name="step1", type=StepType.PYTHON, action="fn1"),
                AgentStepRecord(name="step2", type=StepType.AGENT, agent="agent1"),
                GenerateStepRecord(
                    name="step3", type=StepType.GENERATE, generator="gen1"
                ),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        assert len(graph.nodes) == 3
        # Verify sequential edges: START -> step1 -> step2 -> step3 -> END
        assert len(graph.edges) == 4
        edge_pairs = [(e.source, e.target) for e in graph.edges]
        assert ("START", "step1") in edge_pairs
        assert ("step1", "step2") in edge_pairs
        assert ("step2", "step3") in edge_pairs
        assert ("step3", "END") in edge_pairs

    def test_build_conditional_step(self) -> None:
        """Test building graph from workflow with conditional step (when clause)."""
        workflow = WorkflowFile(
            version="1.0",
            name="conditional",
            steps=[
                PythonStepRecord(name="step1", type=StepType.PYTHON, action="fn1"),
                PythonStepRecord(
                    name="step2",
                    type=StepType.PYTHON,
                    action="fn2",
                    when="result.success",
                ),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        # Find step2 node
        step2_node = next(n for n in graph.nodes if n.id == "step2")
        assert step2_node.is_conditional is True
        assert step2_node.condition == "result.success"

        # Conditional steps are marked on nodes, not edges
        # (edges are sequential by default in top-level workflow)
        assert len(graph.edges) > 0  # Should have edges connecting steps

    def test_build_validate_step_with_retry(self) -> None:
        """Test building graph from workflow with validate step."""
        workflow = WorkflowFile(
            version="1.0",
            name="validate",
            steps=[
                ValidateStepRecord(
                    name="check_quality",
                    type=StepType.VALIDATE,
                    stages=["lint", "test"],
                    retry=3,
                ),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        # Validate step should create retry loop
        check_node = next(n for n in graph.nodes if n.id == "check_quality")
        assert check_node.step_type == "validate"

        # Should have retry edge back to itself
        retry_edges = [e for e in graph.edges if e.edge_type == EdgeType.RETRY]
        assert len(retry_edges) > 0

    def test_build_validate_step_with_on_failure(self) -> None:
        """Test building graph from validate step with on_failure handler."""
        workflow = WorkflowFile(
            version="1.0",
            name="validate-with-handler",
            steps=[
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=["test"],
                    retry=2,
                    on_failure=PythonStepRecord(
                        name="fix_issues",
                        type=StepType.PYTHON,
                        action="fix_fn",
                    ),
                ),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        # Should have both validate node and fix_issues node
        node_ids = [n.id for n in graph.nodes]
        assert "validate" in node_ids
        assert "fix_issues" in node_ids

        # Should have edges showing the retry loop through fix_issues
        edge_pairs = [(e.source, e.target) for e in graph.edges]
        assert ("validate", "fix_issues") in edge_pairs or (
            "fix_issues",
            "validate",
        ) in edge_pairs

    def test_build_branch_step(self) -> None:
        """Test building graph from workflow with branch step."""
        workflow = WorkflowFile(
            version="1.0",
            name="branching",
            steps=[
                BranchStepRecord(
                    name="check_env",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="env == 'prod'",
                            step=PythonStepRecord(
                                name="deploy_prod",
                                type=StepType.PYTHON,
                                action="deploy_prod_fn",
                            ),
                        ),
                        BranchOptionRecord(
                            when="env == 'dev'",
                            step=PythonStepRecord(
                                name="deploy_dev",
                                type=StepType.PYTHON,
                                action="deploy_dev_fn",
                            ),
                        ),
                    ],
                ),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        # Should have branch node plus child nodes
        node_ids = [n.id for n in graph.nodes]
        assert "check_env" in node_ids
        assert "deploy_prod" in node_ids
        assert "deploy_dev" in node_ids

        # Branch node should have children
        branch_node = next(n for n in graph.nodes if n.id == "check_env")
        assert len(branch_node.children) == 2

        # Should have branch edges
        branch_edges = [e for e in graph.edges if e.edge_type == EdgeType.BRANCH]
        assert len(branch_edges) >= 2

    def test_build_parallel_step(self) -> None:
        """Test building graph from workflow with parallel step."""
        workflow = WorkflowFile(
            version="1.0",
            name="parallel",
            steps=[
                ParallelStepRecord(
                    name="run_parallel",
                    type=StepType.PARALLEL,
                    steps=[
                        PythonStepRecord(
                            name="task1",
                            type=StepType.PYTHON,
                            action="task1_fn",
                        ),
                        PythonStepRecord(
                            name="task2",
                            type=StepType.PYTHON,
                            action="task2_fn",
                        ),
                        AgentStepRecord(
                            name="task3",
                            type=StepType.AGENT,
                            agent="agent1",
                        ),
                    ],
                ),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        # Should have parallel node plus child nodes
        node_ids = [n.id for n in graph.nodes]
        assert "run_parallel" in node_ids
        assert "task1" in node_ids
        assert "task2" in node_ids
        assert "task3" in node_ids

        # Parallel node should have children
        parallel_node = next(n for n in graph.nodes if n.id == "run_parallel")
        assert len(parallel_node.children) == 3
        assert parallel_node.step_type == "parallel"

    def test_build_subworkflow_step(self) -> None:
        """Test building graph from workflow with subworkflow step."""
        workflow = WorkflowFile(
            version="1.0",
            name="with-subworkflow",
            steps=[
                SubWorkflowStepRecord(
                    name="run_sub",
                    type=StepType.SUBWORKFLOW,
                    workflow="sub-workflow.yaml",
                    inputs={"param": "value"},
                ),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        assert len(graph.nodes) == 1
        sub_node = graph.nodes[0]
        assert sub_node.id == "run_sub"
        assert sub_node.step_type == "subworkflow"
        assert sub_node.label == "run_sub"

    def test_build_complex_workflow(self) -> None:
        """Test building graph from complex workflow with mixed step types."""
        workflow = WorkflowFile(
            version="1.0",
            name="complex",
            description="Complex workflow with all step types",
            steps=[
                PythonStepRecord(name="setup", type=StepType.PYTHON, action="setup_fn"),
                ParallelStepRecord(
                    name="parallel_tasks",
                    type=StepType.PARALLEL,
                    steps=[
                        AgentStepRecord(
                            name="analyze",
                            type=StepType.AGENT,
                            agent="analyzer",
                        ),
                        GenerateStepRecord(
                            name="generate",
                            type=StepType.GENERATE,
                            generator="doc_gen",
                        ),
                    ],
                ),
                ValidateStepRecord(
                    name="validate_all",
                    type=StepType.VALIDATE,
                    stages=["lint", "test"],
                    retry=2,
                ),
                BranchStepRecord(
                    name="decide",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="result.valid",
                            step=PythonStepRecord(
                                name="deploy",
                                type=StepType.PYTHON,
                                action="deploy_fn",
                            ),
                        ),
                    ],
                ),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        # Verify all main steps are present
        node_ids = [n.id for n in graph.nodes]
        assert "setup" in node_ids
        assert "parallel_tasks" in node_ids
        assert "validate_all" in node_ids
        assert "decide" in node_ids
        assert "analyze" in node_ids
        assert "generate" in node_ids
        assert "deploy" in node_ids

        # Verify graph structure
        assert graph.name == "complex"
        assert graph.description == "Complex workflow with all step types"
        assert len(graph.nodes) >= 7
        assert len(graph.edges) > 0

    def test_build_preserves_step_order(self) -> None:
        """Test that builder preserves the order of steps in workflow."""
        workflow = WorkflowFile(
            version="1.0",
            name="ordered",
            steps=[
                PythonStepRecord(name="first", type=StepType.PYTHON, action="fn1"),
                PythonStepRecord(name="second", type=StepType.PYTHON, action="fn2"),
                PythonStepRecord(name="third", type=StepType.PYTHON, action="fn3"),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        # Nodes should appear in order
        assert graph.nodes[0].id == "first"
        assert graph.nodes[1].id == "second"
        assert graph.nodes[2].id == "third"

    def test_build_empty_workflow_raises_error(self) -> None:
        """Test that building from invalid workflow raises appropriate error."""
        # WorkflowFile requires at least one step, so this should fail at Pydantic level
        with pytest.raises(Exception):  # Pydantic ValidationError
            WorkflowFile(
                version="1.0",
                name="empty",
                steps=[],
            )

    def test_node_ids_are_unique(self) -> None:
        """Test that all generated node IDs are unique."""
        workflow = WorkflowFile(
            version="1.0",
            name="test",
            steps=[
                ParallelStepRecord(
                    name="parallel",
                    type=StepType.PARALLEL,
                    steps=[
                        PythonStepRecord(
                            name="task1", type=StepType.PYTHON, action="fn1"
                        ),
                        PythonStepRecord(
                            name="task2", type=StepType.PYTHON, action="fn2"
                        ),
                    ],
                ),
                BranchStepRecord(
                    name="branch",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="true",
                            step=PythonStepRecord(
                                name="option1",
                                type=StepType.PYTHON,
                                action="fn3",
                            ),
                        ),
                    ],
                ),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        node_ids = [n.id for n in graph.nodes]
        assert len(node_ids) == len(set(node_ids))  # All unique

    def test_all_step_types_supported(self) -> None:
        """Test that all StepType enum values are supported by builder."""
        workflow = WorkflowFile(
            version="1.0",
            name="all-types",
            steps=[
                PythonStepRecord(name="python", type=StepType.PYTHON, action="fn"),
                AgentStepRecord(name="agent", type=StepType.AGENT, agent="agent1"),
                GenerateStepRecord(
                    name="generate", type=StepType.GENERATE, generator="gen1"
                ),
                ValidateStepRecord(
                    name="validate", type=StepType.VALIDATE, stages=["test"]
                ),
                SubWorkflowStepRecord(
                    name="subworkflow", type=StepType.SUBWORKFLOW, workflow="sub.yaml"
                ),
                BranchStepRecord(
                    name="branch",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="true",
                            step=PythonStepRecord(
                                name="opt1", type=StepType.PYTHON, action="fn2"
                            ),
                        ),
                    ],
                ),
                ParallelStepRecord(
                    name="parallel",
                    type=StepType.PARALLEL,
                    steps=[
                        PythonStepRecord(
                            name="par1", type=StepType.PYTHON, action="fn3"
                        ),
                    ],
                ),
            ],
        )

        builder = WorkflowGraphBuilder()
        graph = builder.build(workflow)

        # Should successfully build without errors
        assert len(graph.nodes) > 0

        # Verify all expected step types are present
        step_types = {n.step_type for n in graph.nodes}
        assert "python" in step_types
        assert "agent" in step_types
        assert "generate" in step_types
        assert "validate" in step_types
        assert "subworkflow" in step_types
        assert "branch" in step_types
        assert "parallel" in step_types
