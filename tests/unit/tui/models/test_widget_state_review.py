"""Unit tests for TUI review widget state models."""

from __future__ import annotations

import pytest

from maverick.tui.models import (
    CodeContext,
    CodeLocation,
    FindingSeverity,
    PRInfo,
    PRState,
    PRSummaryState,
    ReviewFinding,
    ReviewFindingItem,
    ReviewFindingsState,
    ValidationStatusState,
    ValidationStep,
    ValidationStepStatus,
)


class TestReviewFindingsState:
    """Tests for ReviewFindingsState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating ReviewFindingsState with default values."""
        state = ReviewFindingsState()

        assert state.findings == ()
        assert state.expanded_index is None
        assert state.code_context is None
        assert state.focused_index == 0

    def test_creation_with_custom_values(self) -> None:
        """Test creating ReviewFindingsState with custom values."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test",
        )
        item = ReviewFindingItem(finding=finding, selected=True)

        context = CodeContext(
            file_path="test.py",
            start_line=1,
            end_line=3,
            content="code",
            highlight_line=2,
        )

        state = ReviewFindingsState(
            findings=(item,),
            expanded_index=0,
            code_context=context,
            focused_index=0,
        )

        assert len(state.findings) == 1
        assert state.expanded_index == 0
        assert state.code_context == context
        assert state.focused_index == 0

    def test_selected_findings_property_with_selections(self) -> None:
        """Test selected_findings property with selected items."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding1 = ReviewFinding(
            id="f1",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test 1",
            description="Test",
        )
        finding2 = ReviewFinding(
            id="f2",
            severity=FindingSeverity.WARNING,
            location=location,
            title="Test 2",
            description="Test",
        )
        finding3 = ReviewFinding(
            id="f3",
            severity=FindingSeverity.SUGGESTION,
            location=location,
            title="Test 3",
            description="Test",
        )

        item1 = ReviewFindingItem(finding=finding1, selected=True)
        item2 = ReviewFindingItem(finding=finding2, selected=False)
        item3 = ReviewFindingItem(finding=finding3, selected=True)

        state = ReviewFindingsState(findings=(item1, item2, item3))

        selected = state.selected_findings
        assert len(selected) == 2
        assert finding1 in selected
        assert finding3 in selected
        assert finding2 not in selected

    def test_selected_findings_property_no_selections(self) -> None:
        """Test selected_findings property with no selections."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test",
        )
        item = ReviewFindingItem(finding=finding, selected=False)

        state = ReviewFindingsState(findings=(item,))
        assert state.selected_findings == ()

    def test_selected_count_property(self) -> None:
        """Test selected_count property."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding1 = ReviewFinding(
            id="f1",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test 1",
            description="Test",
        )
        finding2 = ReviewFinding(
            id="f2",
            severity=FindingSeverity.WARNING,
            location=location,
            title="Test 2",
            description="Test",
        )

        item1 = ReviewFindingItem(finding=finding1, selected=True)
        item2 = ReviewFindingItem(finding=finding2, selected=True)

        state = ReviewFindingsState(findings=(item1, item2))
        assert state.selected_count == 2

    def test_selected_count_property_no_selections(self) -> None:
        """Test selected_count property with no selections."""
        state = ReviewFindingsState()
        assert state.selected_count == 0

    def test_findings_by_severity_property(self) -> None:
        """Test findings_by_severity property groups correctly."""
        location = CodeLocation(file_path="test.py", line_number=1)

        error1 = ReviewFinding(
            id="e1",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Error 1",
            description="Test",
        )
        error2 = ReviewFinding(
            id="e2",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Error 2",
            description="Test",
        )
        warning = ReviewFinding(
            id="w1",
            severity=FindingSeverity.WARNING,
            location=location,
            title="Warning 1",
            description="Test",
        )
        suggestion = ReviewFinding(
            id="s1",
            severity=FindingSeverity.SUGGESTION,
            location=location,
            title="Suggestion 1",
            description="Test",
        )

        item1 = ReviewFindingItem(finding=error1)
        item2 = ReviewFindingItem(finding=error2)
        item3 = ReviewFindingItem(finding=warning)
        item4 = ReviewFindingItem(finding=suggestion)

        state = ReviewFindingsState(findings=(item1, item2, item3, item4))

        grouped = state.findings_by_severity
        assert len(grouped[FindingSeverity.ERROR]) == 2
        assert len(grouped[FindingSeverity.WARNING]) == 1
        assert len(grouped[FindingSeverity.SUGGESTION]) == 1

    def test_findings_by_severity_property_empty(self) -> None:
        """Test findings_by_severity property with no findings."""
        state = ReviewFindingsState()

        grouped = state.findings_by_severity
        assert len(grouped[FindingSeverity.ERROR]) == 0
        assert len(grouped[FindingSeverity.WARNING]) == 0
        assert len(grouped[FindingSeverity.SUGGESTION]) == 0

    def test_is_empty_property_when_empty(self) -> None:
        """Test is_empty property when no findings."""
        state = ReviewFindingsState()
        assert state.is_empty is True

    def test_is_empty_property_when_not_empty(self) -> None:
        """Test is_empty property when findings exist."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test",
        )
        item = ReviewFindingItem(finding=finding)

        state = ReviewFindingsState(findings=(item,))
        assert state.is_empty is False

    def test_review_findings_state_is_frozen(self) -> None:
        """Test ReviewFindingsState is immutable (frozen)."""
        state = ReviewFindingsState()

        with pytest.raises(Exception):  # FrozenInstanceError
            state.focused_index = 1  # type: ignore[misc]


class TestValidationStatusState:
    """Tests for ValidationStatusState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating ValidationStatusState with default values."""
        state = ValidationStatusState()

        assert state.steps == ()
        assert state.expanded_step is None
        assert state.loading is False
        assert state.running_step is None

    def test_creation_with_custom_values(self) -> None:
        """Test creating ValidationStatusState with custom values."""
        step1 = ValidationStep(
            name="format",
            display_name="Format",
            status=ValidationStepStatus.PASSED,
        )
        step2 = ValidationStep(
            name="lint",
            display_name="Lint",
            status=ValidationStepStatus.RUNNING,
        )

        state = ValidationStatusState(
            steps=(step1, step2),
            expanded_step="format",
            loading=True,
            running_step="lint",
        )

        assert len(state.steps) == 2
        assert state.expanded_step == "format"
        assert state.loading is True
        assert state.running_step == "lint"

    def test_all_passed_property_when_all_passed(self) -> None:
        """Test all_passed property when all steps passed."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="test",
                display_name="Test",
                status=ValidationStepStatus.PASSED,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.all_passed is True

    def test_all_passed_property_when_some_failed(self) -> None:
        """Test all_passed property when some steps failed."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.FAILED,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.all_passed is False

    def test_all_passed_property_when_some_pending(self) -> None:
        """Test all_passed property when some steps pending."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.PENDING,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.all_passed is False

    def test_has_failures_property_when_failures(self) -> None:
        """Test has_failures property when steps failed."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.FAILED,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.has_failures is True

    def test_has_failures_property_when_no_failures(self) -> None:
        """Test has_failures property when no failures."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.RUNNING,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.has_failures is False

    def test_is_running_property_when_running(self) -> None:
        """Test is_running property when steps are running."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.RUNNING,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.is_running is True

    def test_is_running_property_when_not_running(self) -> None:
        """Test is_running property when no steps running."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.PENDING,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.is_running is False

    def test_is_empty_property_when_empty(self) -> None:
        """Test is_empty property when no steps."""
        state = ValidationStatusState()
        assert state.is_empty is True

    def test_is_empty_property_when_not_empty(self) -> None:
        """Test is_empty property when steps exist."""
        step = ValidationStep(
            name="format",
            display_name="Format",
            status=ValidationStepStatus.PASSED,
        )
        state = ValidationStatusState(steps=(step,))
        assert state.is_empty is False

    def test_is_empty_property_when_loading(self) -> None:
        """Test is_empty property when loading."""
        state = ValidationStatusState(loading=True)
        assert state.is_empty is False

    def test_validation_status_state_is_frozen(self) -> None:
        """Test ValidationStatusState is immutable (frozen)."""
        state = ValidationStatusState()

        with pytest.raises(Exception):  # FrozenInstanceError
            state.loading = True  # type: ignore[misc]


class TestPRSummaryState:
    """Tests for PRSummaryState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating PRSummaryState with default values."""
        state = PRSummaryState()

        assert state.pr is None
        assert state.description_expanded is False
        assert state.loading is False

    def test_creation_with_custom_values(self) -> None:
        """Test creating PRSummaryState with custom values."""
        pr = PRInfo(
            number=123,
            title="Test PR",
            description="Test description",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/123",
        )

        state = PRSummaryState(pr=pr, description_expanded=True, loading=False)

        assert state.pr == pr
        assert state.description_expanded is True
        assert state.loading is False

    def test_is_empty_property_when_empty(self) -> None:
        """Test is_empty property when no PR data."""
        state = PRSummaryState()
        assert state.is_empty is True

    def test_is_empty_property_when_not_empty(self) -> None:
        """Test is_empty property when PR data exists."""
        pr = PRInfo(
            number=123,
            title="Test PR",
            description="Test description",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/123",
        )
        state = PRSummaryState(pr=pr)
        assert state.is_empty is False

    def test_is_empty_property_when_loading(self) -> None:
        """Test is_empty property when loading."""
        state = PRSummaryState(loading=True)
        assert state.is_empty is False

    def test_pr_summary_state_is_frozen(self) -> None:
        """Test PRSummaryState is immutable (frozen)."""
        state = PRSummaryState()

        with pytest.raises(Exception):  # FrozenInstanceError
            state.loading = True  # type: ignore[misc]


# =============================================================================
# Cross-Model Integration Tests
# =============================================================================
