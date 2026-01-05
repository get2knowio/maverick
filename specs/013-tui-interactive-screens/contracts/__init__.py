"""Contract interfaces for TUI interactive screens.

This package contains Protocol definitions for screens and widgets
in the interactive screens feature.
"""

from __future__ import annotations

from .screens import (
    ConfirmDialogProtocol,
    ErrorDialogProtocol,
    FlyScreenProtocol,
    HomeScreenProtocol,
    InputDialogProtocol,
    MaverickScreenProtocol,
    RefuelScreenProtocol,
    ReviewScreenProtocol,
    SettingsScreenProtocol,
    WorkflowSessionProtocol,
)
from .widgets import (
    BranchInputFieldProtocol,
    ConfirmDialogWidgetProtocol,
    ErrorDialogWidgetProtocol,
    FormFieldProtocol,
    InputDialogWidgetProtocol,
    IssueListItemProtocol,
    IssueListWidgetProtocol,
    NumericFieldProtocol,
    ResultItemProtocol,
    ResultSummaryWidgetProtocol,
    SelectFieldProtocol,
    SettingFieldProtocol,
    SettingsSectionWidgetProtocol,
    ToggleFieldProtocol,
)

__all__ = [
    # Screen protocols
    "MaverickScreenProtocol",
    "HomeScreenProtocol",
    "FlyScreenProtocol",
    "RefuelScreenProtocol",
    "ReviewScreenProtocol",
    "SettingsScreenProtocol",
    "WorkflowSessionProtocol",
    # Modal dialog protocols
    "ConfirmDialogProtocol",
    "ErrorDialogProtocol",
    "InputDialogProtocol",
    # Widget protocols
    "ConfirmDialogWidgetProtocol",
    "ErrorDialogWidgetProtocol",
    "InputDialogWidgetProtocol",
    "FormFieldProtocol",
    "BranchInputFieldProtocol",
    "NumericFieldProtocol",
    "ToggleFieldProtocol",
    "SelectFieldProtocol",
    "IssueListItemProtocol",
    "IssueListWidgetProtocol",
    "SettingsSectionWidgetProtocol",
    "SettingFieldProtocol",
    "ResultItemProtocol",
    "ResultSummaryWidgetProtocol",
]
