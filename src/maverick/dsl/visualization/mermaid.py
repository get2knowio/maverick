"""Mermaid diagram generator for workflow visualization.

This module provides the MermaidGenerator class that converts WorkflowGraph
structures into Mermaid flowchart syntax.

Mermaid is a JavaScript-based diagramming and charting tool that renders
Markdown-inspired text definitions to create diagrams dynamically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.dsl.visualization.graph import GraphEdge, GraphNode, WorkflowGraph

__all__ = ["MermaidGenerator"]


class MermaidGenerator:
    """Generates Mermaid flowchart diagrams from workflow graphs.

    Converts WorkflowGraph structures into Mermaid flowchart syntax that can
    be rendered in Markdown files, documentation sites, GitHub, GitLab, etc.

    The generator supports:
    - Different node shapes based on step type (rectangle, diamond, etc.)
    - Sequential and conditional edges with labels
    - Parallel execution via subgraphs
    - Branch and retry logic
    - Configurable flowchart direction (TD, LR)

    Example:
        >>> generator = MermaidGenerator(direction="TD")
        >>> mermaid_code = generator.generate(workflow_graph)
        >>> print(mermaid_code)
        flowchart TD
            START((Start)) --> step1[Process Data]
            step1 --> END((End))
    """

    def __init__(self, direction: str = "TD") -> None:
        """Initialize the Mermaid generator.

        Args:
            direction: Flowchart direction. Valid values: "TD" (top-down),
                      "LR" (left-right). Defaults to "TD".

        Raises:
            ValueError: If direction is not "TD" or "LR"
        """
        if direction not in ("TD", "LR"):
            raise ValueError(f"Invalid direction: {direction}. Must be 'TD' or 'LR'")
        self.direction = direction

    def generate(self, graph: WorkflowGraph) -> str:
        """Generate Mermaid flowchart code from a workflow graph.

        Args:
            graph: Workflow graph to convert

        Returns:
            Mermaid flowchart code as a string
        """
        lines: list[str] = []

        # Add header with direction
        lines.append(f"flowchart {self.direction}")

        # Add workflow metadata as comment
        if graph.description:
            lines.append(f"    %% {graph.name}: {graph.description}")
        else:
            lines.append(f"    %% {graph.name}")
        lines.append("")

        # Add START node
        lines.append("    START((Start))")

        # Add all nodes
        processed_nodes: set[str] = set()
        for node in graph.nodes:
            if node.id not in processed_nodes:
                self._add_node(lines, node, processed_nodes)

        # Add END node
        lines.append("    END((End))")
        lines.append("")

        # Add all edges
        for edge in graph.edges:
            self._add_edge(lines, edge)

        return "\n".join(lines)

    def _add_node(self, lines: list[str], node: GraphNode, processed: set[str]) -> None:
        """Add a node definition to the output.

        Args:
            lines: Output lines list to append to
            node: Node to add
            processed: Set of already processed node IDs
        """
        if node.id in processed:
            return

        processed.add(node.id)

        # Handle parallel steps with subgraph
        if node.step_type == "parallel" and node.children:
            lines.append(f"    subgraph {node.id}[{node.label}]")
            for child in node.children:
                # Add child nodes inside subgraph
                child_shape = self._get_node_shape(child)
                lines.append(f"        {child.id}{child_shape}")
            lines.append("    end")
        else:
            # Regular node
            shape = self._get_node_shape(node)
            lines.append(f"    {node.id}{shape}")

    def _get_node_shape(self, node: GraphNode) -> str:
        """Get the Mermaid node shape syntax for a node.

        Args:
            node: Node to get shape for

        Returns:
            Mermaid shape syntax (e.g., "[label]", "{label}")
        """
        label = self._escape_label(node.label)

        # Use diamond for conditional nodes (validate, when clauses)
        if node.is_conditional or node.step_type == "validate":
            return f"{{{label}}}"

        # Use rectangle for all other step types
        return f"[{label}]"

    def _escape_label(self, label: str) -> str:
        """Escape special characters in labels.

        Args:
            label: Label to escape

        Returns:
            Escaped label safe for Mermaid
        """
        # Replace characters that interfere with Mermaid syntax
        label = label.replace('"', "'")  # Replace double quotes with single
        label = label.replace("[", "(").replace("]", ")")  # Replace brackets
        label = label.replace("{", "(").replace("}", ")")  # Replace braces
        label = label.replace("(", "（").replace(")", "）")  # Use full-width parens

        # Strip newlines and extra spaces
        label = " ".join(label.split())

        return label

    def _add_edge(self, lines: list[str], edge: GraphEdge) -> None:
        """Add an edge definition to the output.

        Args:
            lines: Output lines list to append to
            edge: Edge to add
        """
        # Format edge with label if present
        if edge.label:
            escaped_label = self._escape_label(edge.label)
            lines.append(f"    {edge.source} -->|{escaped_label}| {edge.target}")
        else:
            lines.append(f"    {edge.source} --> {edge.target}")
