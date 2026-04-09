"""Unit tests for cross-plan dependency resolution and wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.library.actions.cross_plan_deps import (
    CrossPlanDependencyResult,
    ResolvedPlanDep,
    resolve_plan_epic_ids,
    wire_cross_plan_dependencies,
)

# =============================================================================
# ResolvedPlanDep
# =============================================================================


class TestResolvedPlanDep:
    """Tests for ResolvedPlanDep dataclass."""

    def test_to_dict(self) -> None:
        dep = ResolvedPlanDep(plan_name="auth", epic_bd_id="epic-123")
        assert dep.to_dict() == {
            "plan_name": "auth",
            "epic_bd_id": "epic-123",
        }


# =============================================================================
# CrossPlanDependencyResult
# =============================================================================


class TestCrossPlanDependencyResult:
    """Tests for CrossPlanDependencyResult dataclass."""

    def test_to_dict_empty(self) -> None:
        result = CrossPlanDependencyResult(wired_count=0, resolved_plans=(), errors=())
        assert result.to_dict() == {
            "wired_count": 0,
            "resolved_plans": [],
            "errors": [],
        }

    def test_to_dict_with_data(self) -> None:
        dep = ResolvedPlanDep(plan_name="auth", epic_bd_id="e-1")
        result = CrossPlanDependencyResult(
            wired_count=1,
            resolved_plans=(dep,),
            errors=("warning",),
        )
        d = result.to_dict()
        assert d["wired_count"] == 1
        assert len(d["resolved_plans"]) == 1
        assert d["errors"] == ["warning"]


# =============================================================================
# resolve_plan_epic_ids
# =============================================================================


class TestResolvePlanEpicIds:
    """Tests for resolve_plan_epic_ids."""

    @pytest.mark.asyncio
    async def test_empty_plan_names_returns_empty(self) -> None:
        resolved, errors = await resolve_plan_epic_ids((), cwd=Path("/tmp"))
        assert resolved == []
        assert errors == []

    @pytest.mark.asyncio
    async def test_resolves_matching_epic(self) -> None:
        """Finds epic with matching flight_plan_name in state."""
        mock_summary = MagicMock()
        mock_summary.id = "epic-abc"

        mock_details = MagicMock()
        mock_details.state = {"flight_plan_name": "add-auth"}

        with patch("maverick.beads.client.BeadClient") as MockClient:
            client = MockClient.return_value
            client.query = AsyncMock(return_value=[mock_summary])
            client.show = AsyncMock(return_value=mock_details)

            resolved, errors = await resolve_plan_epic_ids(("add-auth",), cwd=Path("/tmp"))

        assert len(resolved) == 1
        assert resolved[0].plan_name == "add-auth"
        assert resolved[0].epic_bd_id == "epic-abc"
        assert errors == []

    @pytest.mark.asyncio
    async def test_returns_error_for_unknown_plan(self) -> None:
        """Plan name not found in any epic produces an error."""
        with patch("maverick.beads.client.BeadClient") as MockClient:
            client = MockClient.return_value
            client.query = AsyncMock(return_value=[])

            resolved, errors = await resolve_plan_epic_ids(("nonexistent-plan",), cwd=Path("/tmp"))

        assert resolved == []
        assert len(errors) == 1
        assert "nonexistent-plan" in errors[0]

    @pytest.mark.asyncio
    async def test_query_failure_returns_error(self) -> None:
        with patch("maverick.beads.client.BeadClient") as MockClient:
            client = MockClient.return_value
            client.query = AsyncMock(side_effect=RuntimeError("bd not available"))

            resolved, errors = await resolve_plan_epic_ids(("plan-a",), cwd=Path("/tmp"))

        assert resolved == []
        assert len(errors) == 1
        assert "bd not available" in errors[0]

    @pytest.mark.asyncio
    async def test_multiple_plans_partial_resolution(self) -> None:
        """Resolves some plans, errors on others."""
        epic1 = MagicMock()
        epic1.id = "e-1"
        epic2 = MagicMock()
        epic2.id = "e-2"

        details1 = MagicMock()
        details1.state = {"flight_plan_name": "plan-a"}
        details2 = MagicMock()
        details2.state = {"flight_plan_name": "plan-b"}

        with patch("maverick.beads.client.BeadClient") as MockClient:
            client = MockClient.return_value
            client.query = AsyncMock(return_value=[epic1, epic2])
            client.show = AsyncMock(side_effect=[details1, details2])

            resolved, errors = await resolve_plan_epic_ids(("plan-a", "plan-c"), cwd=Path("/tmp"))

        assert len(resolved) == 1
        assert resolved[0].plan_name == "plan-a"
        assert len(errors) == 1
        assert "plan-c" in errors[0]


# =============================================================================
# wire_cross_plan_dependencies
# =============================================================================


class TestWireCrossPlanDependencies:
    """Tests for wire_cross_plan_dependencies."""

    @pytest.mark.asyncio
    async def test_empty_dep_ids_returns_zero(self) -> None:
        result = await wire_cross_plan_dependencies(
            new_epic_bd_id="e-new",
            dependency_epic_ids=[],
            cwd=Path("/tmp"),
        )
        assert result.wired_count == 0
        assert result.errors == ()

    @pytest.mark.asyncio
    async def test_dry_run_returns_count_without_calling_bd(self) -> None:
        result = await wire_cross_plan_dependencies(
            new_epic_bd_id="e-new",
            dependency_epic_ids=["e-dep1", "e-dep2"],
            cwd=Path("/tmp"),
            dry_run=True,
        )
        assert result.wired_count == 2
        assert len(result.resolved_plans) == 2
        assert result.errors == ()

    @pytest.mark.asyncio
    async def test_wires_epic_dependencies(self) -> None:
        """Calls add_dependency for each dependency epic."""
        with patch("maverick.beads.client.BeadClient") as MockClient:
            client = MockClient.return_value
            client.add_dependency = AsyncMock()

            result = await wire_cross_plan_dependencies(
                new_epic_bd_id="e-new",
                dependency_epic_ids=["e-dep1"],
                cwd=Path("/tmp"),
            )

        assert result.wired_count == 1
        assert result.errors == ()
        client.add_dependency.assert_called_once()
        dep = client.add_dependency.call_args[0][0]
        assert dep.blocker_id == "e-dep1"
        assert dep.blocked_id == "e-new"

    @pytest.mark.asyncio
    async def test_captures_wiring_errors(self) -> None:
        with patch("maverick.beads.client.BeadClient") as MockClient:
            client = MockClient.return_value
            client.add_dependency = AsyncMock(side_effect=RuntimeError("dep failed"))

            result = await wire_cross_plan_dependencies(
                new_epic_bd_id="e-new",
                dependency_epic_ids=["e-dep1"],
                cwd=Path("/tmp"),
            )

        assert result.wired_count == 0
        assert len(result.errors) == 1
        assert "dep failed" in result.errors[0]
