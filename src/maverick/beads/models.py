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
        VALIDATION: Fix bead for lint/type/test failures.
        REVIEW: Fix bead for code review findings.
    """

    FOUNDATION = "foundation"
    USER_STORY = "user_story"
    CLEANUP = "cleanup"
    VALIDATION = "validation"
    REVIEW = "review"


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
    priority: int = Field(ge=0, le=4, description="Priority (0 = highest, max 4)")
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

    Uses ``bd dep add <blocked_id> --blocked-by <blocker_id> --type blocks``
    semantics: ``blocker_id`` must complete before ``blocked_id`` can start.

    Attributes:
        blocker_id: ID of the prerequisite bead (must finish first).
        blocked_id: ID of the dependent bead (waits for blocker).
        dep_type: Type of dependency relationship.
    """

    blocker_id: str = Field(min_length=1, description="Prerequisite bead ID")
    blocked_id: str = Field(min_length=1, description="Dependent bead ID")
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


class ReadyBead(BaseModel):
    """A bead returned by ``bd ready`` that is available for work.

    Attributes:
        id: Bead identifier.
        title: Human-readable bead title.
        priority: Numeric priority (lower = higher priority).
        bead_type: Whether this is an epic or task.
        description: Full bead description.
        parent_id: Parent bead ID (epic ID) if any.
    """

    id: str = Field(min_length=1, description="Bead ID")
    title: str = Field(description="Bead title")
    priority: int = Field(description="Priority (1 = highest)")
    bead_type: str = Field(default="task", description="Bead type")
    description: str = Field(default="", description="Full description")
    parent_id: str | None = Field(default=None, description="Parent bead ID")

    model_config = ConfigDict(frozen=True)


class ClosedBead(BaseModel):
    """Result of closing a bead via ``bd close``.

    Attributes:
        id: Bead identifier.
        status: Final status after closing.
        closed_at: ISO timestamp when the bead was closed.
    """

    id: str = Field(min_length=1, description="Bead ID")
    status: str = Field(description="Final status")
    closed_at: str = Field(default="", description="ISO close timestamp")

    model_config = ConfigDict(frozen=True)


class BeadDetails(BaseModel):
    """Full details of a bead from ``bd show``.

    Attributes:
        id: Bead identifier.
        title: Human-readable bead title.
        description: Full bead description.
        bead_type: Whether this is an epic or task.
        priority: Numeric priority.
        status: Current bead status.
        parent_id: Parent bead ID if any.
        labels: Labels attached to the bead.
        state: Arbitrary key-value state metadata.
    """

    id: str = Field(min_length=1, description="Bead ID")
    title: str = Field(description="Bead title")
    description: str = Field(default="", description="Full description")
    bead_type: str = Field(default="task", description="Bead type")
    priority: int = Field(default=1, description="Priority")
    status: str = Field(default="open", description="Current status")
    parent_id: str | None = Field(default=None, description="Parent bead ID")
    labels: list[str] = Field(default_factory=list, description="Labels")
    state: dict[str, str] = Field(default_factory=dict, description="State metadata")

    model_config = ConfigDict(frozen=True)


class BeadSummary(BaseModel):
    """Lightweight bead summary from ``bd children`` or ``bd query``.

    Attributes:
        id: Bead identifier.
        title: Human-readable bead title.
        status: Current bead status.
        priority: Numeric priority.
        bead_type: Whether this is an epic or task.
    """

    id: str = Field(min_length=1, description="Bead ID")
    title: str = Field(description="Bead title")
    status: str = Field(default="open", description="Current status")
    priority: int = Field(default=1, description="Priority")
    bead_type: str = Field(default="task", description="Bead type")

    model_config = ConfigDict(frozen=True)
