"""Built-in workflow library.

This module provides access to Maverick's built-in workflows
and scaffolding templates.

Submodules:
- templates: Jinja2 scaffolding templates
"""

from __future__ import annotations

from maverick.library.scaffold import (
    InvalidNameError,
    OutputExistsError,
    ScaffoldError,
    ScaffoldRequest,
    ScaffoldResult,
    ScaffoldService,
    TemplateFormat,
    TemplateInfo,
    TemplateRenderError,
    TemplateType,
    create_scaffold_service,
    get_default_output_dir,
    validate_workflow_name,
)

__all__ = [
    # Enums
    "TemplateType",
    "TemplateFormat",
    # Models - Scaffold
    "TemplateInfo",
    "ScaffoldRequest",
    "ScaffoldResult",
    # Exceptions
    "ScaffoldError",
    "InvalidNameError",
    "OutputExistsError",
    "TemplateRenderError",
    # Services
    "ScaffoldService",
    # Functions
    "validate_workflow_name",
    "get_default_output_dir",
    "create_scaffold_service",
]
