"""Data models for bead generation and tracking.

Defines enums for bead classification and frozen Pydantic models for
bead definitions, created beads, dependencies, and generation results.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class BeadType(str, Enum):
    """Type of bead in the work hierarchy.

    Attributes:
        EPIC: Top-level container grouping related work beads.
        TASK: Individual unit of work to be resolved by an agent.
    """

    EPIC = "epic"
    TASK = "task"


class BeadCategory(str, Enum):
    """Category describing a bead's role in the workflow.

    Attributes:
        FOUNDATION: Setup/infrastructure work that blocks other beads.
        USER_STORY: Feature work derived from a user story phase.
        CLEANUP: Polish/cross-cutting work that depends on all stories.
    """

    FOUNDATION = "foundation"
    USER_STORY = "user_story"
    CLEANUP = "cleanup"


class DependencyType(str, Enum):
    """Relationship type between beads.

    Attributes:
        BLOCKS: The source bead blocks the target bead.
    """

    BLOCKS = "blocks"


class BeadDefinition(BaseModel):
    """Intent to create a bead, before ``bd create`` is called.

    Attributes:
        title: Human-readable bead title.
        bead_type: Whether this is an epic or task.
        priority: Numeric priority (lower = higher priority).
        category: Classification of the bead's role.
        description: Full description including context, tasks, and criteria.
        phase_names: Original phase names from tasks.md that this bead covers.
        user_story_id: User story identifier if applicable (e.g., "US1").
        task_ids: Task IDs from tasks.md included in this bead.
    """

    title: str = Field(min_length=1, description="Bead title")
    bead_type: BeadType = Field(description="Epic or task")
    priority: int = Field(ge=1, description="Priority (1 = highest)")
    category: BeadCategory = Field(description="Bead category")
    description: str = Field(default="", description="Full bead description")
    phase_names: list[str] = Field(
        default_factory=list, description="Source phase names"
    )
    user_story_id: str | None = Field(
        default=None, description="User story ID (e.g., US1)"
    )
    task_ids: list[str] = Field(
        default_factory=list, description="Task IDs from tasks.md"
    )

    model_config = ConfigDict(frozen=True)


class CreatedBead(BaseModel):
    """A bead that has been successfully created via ``bd create``.

    Attributes:
        bd_id: The bead ID assigned by ``bd``.
        definition: The original definition used to create this bead.
    """

    bd_id: str = Field(min_length=1, description="Bead ID from bd")
    definition: BeadDefinition = Field(description="Original definition")

    model_config = ConfigDict(frozen=True)


class BeadDependency(BaseModel):
    """Dependency relationship between two beads.

    Attributes:
        from_id: ID of the bead that blocks.
        to_id: ID of the bead that is blocked.
        dep_type: Type of dependency relationship.
    """

    from_id: str = Field(min_length=1, description="Source bead ID")
    to_id: str = Field(min_length=1, description="Target bead ID")
    dep_type: DependencyType = Field(
        default=DependencyType.BLOCKS, description="Dependency type"
    )

    model_config = ConfigDict(frozen=True)


class BeadGenerationResult(BaseModel):
    """Result of generating beads from a source (e.g., SpecKit).

    Attributes:
        epic: The created epic bead (if successful).
        work_beads: List of created work beads (tasks).
        dependencies: Dependencies wired between beads.
        errors: Errors encountered during generation.
    """

    epic: CreatedBead | None = Field(default=None, description="Epic bead")
    work_beads: list[CreatedBead] = Field(
        default_factory=list, description="Work beads"
    )
    dependencies: list[BeadDependency] = Field(
        default_factory=list, description="Dependencies wired"
    )
    errors: list[str] = Field(default_factory=list, description="Errors encountered")

    model_config = ConfigDict(frozen=True)

    @property
    def success(self) -> bool:
        """True if epic was created and no errors occurred."""
        return self.epic is not None and len(self.errors) == 0

    @property
    def total_beads(self) -> int:
        """Total number of beads created (epic + work beads)."""
        return (1 if self.epic else 0) + len(self.work_beads)
