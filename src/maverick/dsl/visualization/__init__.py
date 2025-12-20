"""Workflow visualization module for Maverick DSL.

This module provides diagram generation capabilities for workflows defined
using the Maverick DSL. It supports multiple output formats:

- **Mermaid**: Industry-standard flowchart diagrams compatible with GitHub,
  GitLab, and documentation tools
- **ASCII**: Terminal-friendly text-based diagrams for quick visualization

The visualization system converts workflow definitions into graph structures
that can be rendered in different formats, making it easy to understand
workflow structure, dependencies, and control flow at a glance.

Modules:
    mermaid: Mermaid diagram generator
    ascii: ASCII diagram generator

Classes:
    GraphNode: Represents a workflow step or control flow node
    GraphEdge: Represents a connection between nodes
    WorkflowGraph: Complete graph representation of a workflow
    EdgeType: Enumeration of edge types (sequential, conditional, parallel)
    WorkflowGraphBuilder: Converts WorkflowFile to WorkflowGraph
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from maverick.dsl.visualization.ascii import ASCIIGenerator
from maverick.dsl.visualization.graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    WorkflowGraph,
    WorkflowGraphBuilder,
)
from maverick.dsl.visualization.mermaid import MermaidGenerator

if TYPE_CHECKING:
    from maverick.dsl.serialization.schema import WorkflowFile

__all__ = [
    "ASCIIGenerator",
    "MermaidGenerator",
    "EdgeType",
    "GraphNode",
    "GraphEdge",
    "WorkflowGraph",
    "WorkflowGraphBuilder",
    "to_mermaid",
    "to_ascii",
]


def to_mermaid(
    workflow: WorkflowFile,
    direction: str = "TD",
) -> str:
    """Generate Mermaid flowchart from a workflow definition.

    Convenience function that combines graph building and Mermaid generation
    into a single call.

    Args:
        workflow: WorkflowFile to visualize.
        direction: Flowchart direction ("TD" for top-down, "LR" for left-right).
            Defaults to "TD".

    Returns:
        Mermaid flowchart code as a string.

    Raises:
        ValueError: If workflow has no steps or direction is invalid.

    Example:
        >>> from maverick.dsl.serialization.schema import WorkflowFile
        >>> mermaid_code = to_mermaid(workflow_file)
        >>> print(mermaid_code)
        flowchart TD
            START((Start)) --> step1[Process Data]
            step1 --> END((End))
    """
    builder = WorkflowGraphBuilder()
    graph = builder.build(workflow)
    generator = MermaidGenerator(direction=direction)
    return generator.generate(graph)


def to_ascii(
    workflow: WorkflowFile,
    width: int = 60,
) -> str:
    """Generate ASCII diagram from a workflow definition.

    Convenience function that creates an ASCII visualization of the workflow
    using box-drawing characters.

    Args:
        workflow: WorkflowFile to visualize.
        width: Maximum diagram width in characters. Defaults to 60.

    Returns:
        ASCII diagram string using box-drawing characters.

    Raises:
        ValueError: If workflow has no steps.

    Example:
        >>> from maverick.dsl.serialization.schema import WorkflowFile
        >>> diagram = to_ascii(workflow_file, width=80)
        >>> print(diagram)
        ┌──────────────────────────────────────┐
        │ Workflow: my-workflow                │
        │ A simple example workflow            │
        ...
    """
    generator = ASCIIGenerator(width=width)
    return generator.generate(workflow)
