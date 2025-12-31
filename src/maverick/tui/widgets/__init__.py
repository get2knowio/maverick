"""Maverick TUI widgets package.

This module exports all widget classes for the Maverick TUI application.
Includes widgets and their Textual Message classes for inter-widget communication.
"""

from __future__ import annotations

from maverick.tui.widgets.agent_output import AgentOutput
from maverick.tui.widgets.diff_panel import DiffPanel
from maverick.tui.widgets.form import (
    BranchInputField,
    NumericField,
    SelectField,
    ToggleField,
)
from maverick.tui.widgets.issue_list import IssueList, IssueListItem
from maverick.tui.widgets.log_panel import LogPanel
from maverick.tui.widgets.modal import ConfirmDialog, ErrorDialog, InputDialog
from maverick.tui.widgets.pr_summary import PRSummary
from maverick.tui.widgets.result_summary import ResultSummary
from maverick.tui.widgets.review_findings import ReviewFindings
from maverick.tui.widgets.settings import SettingField, SettingsSection
from maverick.tui.widgets.sidebar import Sidebar
from maverick.tui.widgets.stage_indicator import StageIndicator
from maverick.tui.widgets.validation_status import ValidationStatus
from maverick.tui.widgets.workflow_list import WorkflowList
from maverick.tui.widgets.workflow_progress import (
    StageCollapsed,
    StageExpanded,
    WorkflowProgress,
)

# Message classes for inter-widget communication
# These are exported to allow screens and other widgets to handle messages
AgentOutputSearchActivated = AgentOutput.SearchActivated
AgentOutputToolCallExpanded = AgentOutput.ToolCallExpanded
AgentOutputToolCallCollapsed = AgentOutput.ToolCallCollapsed

ReviewFindingsFindingExpanded = ReviewFindings.FindingExpanded
ReviewFindingsFindingSelected = ReviewFindings.FindingSelected
ReviewFindingsBulkDismissRequested = ReviewFindings.BulkDismissRequested
ReviewFindingsBulkCreateIssueRequested = ReviewFindings.BulkCreateIssueRequested
ReviewFindingsFileLocationClicked = ReviewFindings.FileLocationClicked

ValidationStatusStepExpanded = ValidationStatus.StepExpanded
ValidationStatusStepCollapsed = ValidationStatus.StepCollapsed
ValidationStatusRerunRequested = ValidationStatus.RerunRequested

PRSummaryOpenPRRequested = PRSummary.OpenPRRequested
PRSummaryDescriptionExpanded = PRSummary.DescriptionExpanded
PRSummaryDescriptionCollapsed = PRSummary.DescriptionCollapsed

IssueListSelectionChanged = IssueList.SelectionChanged
IssueListItemToggled = IssueListItem.Toggled

ResultSummaryPRLinkClicked = ResultSummary.PRLinkClicked

__all__ = [
    # Widgets
    "AgentOutput",
    "DiffPanel",
    "IssueList",
    "IssueListItem",
    "LogPanel",
    "PRSummary",
    "ResultSummary",
    "ReviewFindings",
    "SettingField",
    "SettingsSection",
    "Sidebar",
    "StageIndicator",
    "ValidationStatus",
    "WorkflowList",
    "WorkflowProgress",
    # Modal dialogs
    "ConfirmDialog",
    "ErrorDialog",
    "InputDialog",
    # Form fields
    "BranchInputField",
    "NumericField",
    "SelectField",
    "ToggleField",
    # WorkflowProgress messages
    "StageExpanded",
    "StageCollapsed",
    # AgentOutput messages
    "AgentOutputSearchActivated",
    "AgentOutputToolCallExpanded",
    "AgentOutputToolCallCollapsed",
    # ReviewFindings messages
    "ReviewFindingsFindingExpanded",
    "ReviewFindingsFindingSelected",
    "ReviewFindingsBulkDismissRequested",
    "ReviewFindingsBulkCreateIssueRequested",
    "ReviewFindingsFileLocationClicked",
    # ValidationStatus messages
    "ValidationStatusStepExpanded",
    "ValidationStatusStepCollapsed",
    "ValidationStatusRerunRequested",
    # PRSummary messages
    "PRSummaryOpenPRRequested",
    "PRSummaryDescriptionExpanded",
    "PRSummaryDescriptionCollapsed",
    # IssueList messages
    "IssueListSelectionChanged",
    "IssueListItemToggled",
    # ResultSummary messages
    "ResultSummaryPRLinkClicked",
]
