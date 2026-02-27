"""Pydantic model for prompt override configuration in maverick.yaml."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, model_validator


class PromptOverrideConfig(BaseModel):
    """User-provided prompt override for a single step.

    Configured in maverick.yaml under the prompts: key.

    Validation:
        - prompt_suffix and prompt_file are mutually exclusive.
        - At least one must be set.
        - Empty strings are treated as None (no-op).
    """

    prompt_suffix: str | None = None
    prompt_file: str | None = None

    @model_validator(mode="after")
    def _check_mutual_exclusivity(self) -> Self:
        # Normalize empty strings to None
        if self.prompt_suffix is not None and self.prompt_suffix.strip() == "":
            self.prompt_suffix = None
        if self.prompt_file is not None and self.prompt_file.strip() == "":
            self.prompt_file = None

        if self.prompt_suffix is not None and self.prompt_file is not None:
            msg = "Cannot configure both prompt_suffix and prompt_file"
            raise ValueError(msg)

        if self.prompt_suffix is None and self.prompt_file is None:
            msg = "At least one of prompt_suffix or prompt_file must be set"
            raise ValueError(msg)

        return self
