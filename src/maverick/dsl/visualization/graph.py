"""Graph data structures for workflow visualization.

This module defines the core data structures used to represent workflows
as graphs for visualization purposes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from maverick.dsl.serialization.schema import (
    AgentStepRecord,
    BranchStepRecord,
    GenerateStepRecord,
    LoopStepRecord,
    PythonStepRecord,
    StepRecordUnion,
    SubWorkflowStepRecord,
    ValidateStepRecord,
    WorkflowFile,
)

__all__ = [
    "EdgeType",
    "GraphNode",
    "GraphEdge",
    "WorkflowGraph",
    "WorkflowGraphBuilder",
]


# =============================================================================
# Graph Data Structures
# =============================================================================


class EdgeType(str, Enum):
    """Types of edges in workflow graph.

    Attributes:
        SEQUENTIAL: Normal step-to-step flow
        CONDITIONAL: Conditional branch (if/else)
        RETRY: Retry loop edge
        BRANCH: Branch option edge
    """

    SEQUENTIAL = "sequential"
    CONDITIONAL = "conditional"
    RETRY = "retry"
    BRANCH = "branch"


@dataclass(frozen=True, slots=True)
class GraphNode:
    """Represents a node in the workflow graph.

    A node can be a regular step, a conditional step, or a container for
    parallel/branch steps.

    Attributes:
        id: Unique node identifier (step name)
        label: Display label for the node
        step_type: Type of step (python, agent, validate, etc.)
        is_conditional: Whether this node represents a decision point
        condition: Optional condition expression for conditional nodes
        children: Nested child nodes for parallel/branch steps
    """

    id: str
    label: str
    step_type: str
    is_conditional: bool = False
    condition: str | None = None
    children: tuple[GraphNode, ...] = ()


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """Represents an edge between nodes in the workflow graph.

    Attributes:
        source: Source node ID
        target: Target node ID
        label: Optional edge label (e.g., "pass", "fail")
        edge_type: Type of edge (sequential, conditional, etc.)
    """

    source: str
    target: str
    label: str = ""
    edge_type: EdgeType = EdgeType.SEQUENTIAL


@dataclass(frozen=True, slots=True)
class WorkflowGraph:
    """Complete graph representation of a workflow.

    Attributes:
        name: Workflow name
        description: Workflow description
        nodes: Tuple of all nodes in the graph
        edges: Tuple of all edges in the graph
    """

    name: str
    description: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


# =============================================================================
# Graph Builder
# =============================================================================


class WorkflowGraphBuilder:
    """Builds a WorkflowGraph from a WorkflowFile.

    Converts the serialized workflow definition into a graph structure
    suitable for visualization, handling all step types including nested
    parallel and branch steps.

    Example:
        >>> builder = WorkflowGraphBuilder()
        >>> graph = builder.build(workflow_file)
    """

    def build(self, workflow: WorkflowFile) -> WorkflowGraph:
        """Build a graph from a workflow file.

        Args:
            workflow: Workflow file to convert

        Returns:
            WorkflowGraph with nodes and edges representing the workflow
        """
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # Add START edge to first step
        if workflow.steps:
            edges.append(GraphEdge(source="START", target=workflow.steps[0].name))

        # Process each step
        prev_step_id: str | None = None
        for step in workflow.steps:
            # Build node(s) for this step
            step_nodes, step_edges = self._build_step(step)
            nodes.extend(step_nodes)
            edges.extend(step_edges)

            # Connect to previous step if sequential
            if prev_step_id:
                edges.append(GraphEdge(source=prev_step_id, target=step.name))

            prev_step_id = step.name

        # Add edge from last step to END
        if workflow.steps:
            edges.append(GraphEdge(source=workflow.steps[-1].name, target="END"))

        return WorkflowGraph(
            name=workflow.name,
            description=workflow.description,
            nodes=tuple(nodes),
            edges=tuple(edges),
        )

    def _build_step(
        self, step: StepRecordUnion
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        """Build node(s) and edge(s) for a single step.

        Args:
            step: Step record to process

        Returns:
            Tuple of (nodes, edges) created for this step
        """
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # Determine if step is conditional
        is_conditional = step.when is not None

        # Handle different step types
        if isinstance(step, PythonStepRecord):
            nodes.append(
                GraphNode(
                    id=step.name,
                    label=step.name,
                    step_type="python",
                    is_conditional=is_conditional,
                    condition=step.when,
                )
            )
        elif isinstance(step, AgentStepRecord):
            nodes.append(
                GraphNode(
                    id=step.name,
                    label=step.name,
                    step_type="agent",
                    is_conditional=is_conditional,
                    condition=step.when,
                )
            )
        elif isinstance(step, GenerateStepRecord):
            nodes.append(
                GraphNode(
                    id=step.name,
                    label=step.name,
                    step_type="generate",
                    is_conditional=is_conditional,
                    condition=step.when,
                )
            )
        elif isinstance(step, ValidateStepRecord):
            # Validate steps are inherently conditional (pass/fail)
            nodes.append(
                GraphNode(
                    id=step.name,
                    label=step.name,
                    step_type="validate",
                    is_conditional=True,  # Always conditional
                    condition=step.when,
                )
            )

            # Handle retry logic
            if step.retry > 0 and step.on_failure:
                # Add failure handler node
                handler_nodes, handler_edges = self._build_step(step.on_failure)
                nodes.extend(handler_nodes)
                edges.extend(handler_edges)

                # Create retry loop
                edges.append(
                    GraphEdge(
                        source=step.name,
                        target=step.on_failure.name,
                        label="fail",
                        edge_type=EdgeType.RETRY,
                    )
                )
                edges.append(
                    GraphEdge(
                        source=step.on_failure.name,
                        target=step.name,
                        edge_type=EdgeType.RETRY,
                    )
                )
            elif step.retry > 0:
                # Simple retry loop back to self
                edges.append(
                    GraphEdge(
                        source=step.name,
                        target=step.name,
                        label="retry",
                        edge_type=EdgeType.RETRY,
                    )
                )
        elif isinstance(step, SubWorkflowStepRecord):
            nodes.append(
                GraphNode(
                    id=step.name,
                    label=step.name,
                    step_type="subworkflow",
                    is_conditional=is_conditional,
                    condition=step.when,
                )
            )
        elif isinstance(step, BranchStepRecord):
            # Create branch node with children
            branch_children: list[GraphNode] = []
            for option in step.options:
                child_nodes, child_edges = self._build_step(option.step)
                branch_children.extend(child_nodes)
                nodes.extend(child_nodes)
                edges.extend(child_edges)

                # Add branch edge
                edges.append(
                    GraphEdge(
                        source=step.name,
                        target=option.step.name,
                        label=option.when,
                        edge_type=EdgeType.BRANCH,
                    )
                )

            nodes.append(
                GraphNode(
                    id=step.name,
                    label=step.name,
                    step_type="branch",
                    is_conditional=is_conditional,
                    condition=step.when,
                    children=tuple(branch_children),
                )
            )
        elif isinstance(step, LoopStepRecord):
            # Create parallel node with children
            parallel_children: list[GraphNode] = []
            for parallel_step in step.steps:
                child_nodes, child_edges = self._build_step(parallel_step)
                parallel_children.extend(child_nodes)
                nodes.extend(child_nodes)
                edges.extend(child_edges)

            nodes.append(
                GraphNode(
                    id=step.name,
                    label=step.name,
                    step_type="parallel",
                    is_conditional=is_conditional,
                    condition=step.when,
                    children=tuple(parallel_children),
                )
            )

        return nodes, edges
