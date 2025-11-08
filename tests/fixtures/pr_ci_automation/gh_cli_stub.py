"""Stub helper for gh CLI command simulation in PR CI automation tests.

This module provides utilities for mocking gh CLI responses in unit and integration
tests without requiring actual GitHub API connectivity.
"""

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class GhCommandStub:
    """Stub response for a gh CLI command."""

    stdout: str = ""
    stderr: str = ""
    returncode: int = 0

    @classmethod
    def success(cls, data: dict[str, Any] | list[dict[str, Any]]) -> "GhCommandStub":
        """Create successful JSON response stub."""
        return cls(stdout=json.dumps(data), returncode=0)

    @classmethod
    def failure(cls, error_message: str, returncode: int = 1) -> "GhCommandStub":
        """Create failure response stub."""
        return cls(stderr=error_message, returncode=returncode)


class GhCliStubHelper:
    """Helper for stubbing gh CLI subprocess calls in tests.

    Usage:
        helper = GhCliStubHelper()
        helper.stub_pr_view(pr_number=123, state="OPEN")
        helper.stub_pr_create(pr_number=456, url="https://github.com/...")

        # In test, patch subprocess to return helper.get_stub(cmd)
    """

    def __init__(self) -> None:
        self._stubs: dict[tuple[str, ...], GhCommandStub] = {}

    def add_stub(self, command_parts: tuple[str, ...], stub: GhCommandStub) -> None:
        """Register a stub for specific command arguments.

        Args:
            command_parts: Command tuple (e.g., ("gh", "pr", "view", "123"))
            stub: Response to return for this command
        """
        self._stubs[command_parts] = stub

    def get_stub(self, command_parts: tuple[str, ...]) -> GhCommandStub | None:
        """Retrieve registered stub for command, or None if not found."""
        return self._stubs.get(command_parts)

    def stub_pr_view(
        self,
        pr_number: int,
        state: str = "OPEN",
        base_branch: str = "main",
        head_branch: str = "feature",
        url: str = "https://github.com/owner/repo/pull/123",
        merged_at: str | None = None,
    ) -> None:
        """Register stub for `gh pr view <number> --json ...` command."""
        pr_data = {
            "number": pr_number,
            "state": state,
            "baseRefName": base_branch,
            "headRefName": head_branch,
            "url": url,
            "mergedAt": merged_at,
            "isCrossRepository": False,
        }
        # Stub for gh pr view <number> --json ...
        self.add_stub(
            (
                "gh",
                "pr",
                "view",
                str(pr_number),
                "--json",
                "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository",
            ),
            GhCommandStub.success(pr_data),
        )
        # Also stub for gh pr view --head <branch> --json ...
        self.add_stub(
            (
                "gh",
                "pr",
                "view",
                "--head",
                head_branch,
                "--json",
                "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository",
            ),
            GhCommandStub.success(pr_data),
        )

    def stub_pr_create(
        self,
        pr_number: int,
        url: str = "https://github.com/owner/repo/pull/123",
        base_branch: str = "main",
        head_branch: str = "feature",
    ) -> None:
        """Register stub for `gh pr create` command."""
        pr_data = {
            "number": pr_number,
            "url": url,
            "baseRefName": base_branch,
            "headRefName": head_branch,
        }
        # Stub the create command with various possible argument combinations
        for title_arg in ["--title", "-t"]:
            for body_arg in ["--body", "-b"]:
                self.add_stub(
                    ("gh", "pr", "create", title_arg, body_arg, "--base", base_branch, "--head", head_branch),
                    GhCommandStub.success(pr_data),
                )

    def stub_pr_checks(
        self,
        pr_number: int,
        checks: list[dict[str, Any]],
    ) -> None:
        """Register stub for `gh pr checks <number> --json ...` command.

        Args:
            pr_number: PR number
            checks: List of check run data with status, conclusion, name, etc.
        """
        self.add_stub(
            ("gh", "pr", "checks", str(pr_number), "--json", "name,status,conclusion,completedAt,detailsUrl"),
            GhCommandStub.success(checks),
        )

    def stub_pr_merge(
        self,
        pr_number: int,
        merge_commit_sha: str = "abc123def456",
        merged: bool = True,
    ) -> None:
        """Register stub for `gh pr merge <number>` command."""
        if merged:
            merge_data = {
                "sha": merge_commit_sha,
                "merged": True,
            }
            self.add_stub(("gh", "pr", "merge", str(pr_number), "--merge", "--auto"), GhCommandStub.success(merge_data))
        else:
            self.add_stub(
                ("gh", "pr", "merge", str(pr_number), "--merge", "--auto"),
                GhCommandStub.failure("Pull request is not mergeable", returncode=1),
            )

    def stub_run_view(
        self,
        run_id: int,
        status: str = "completed",
        conclusion: str = "success",
        created_at: str = "2025-01-01T00:00:00Z",
        updated_at: str = "2025-01-01T00:05:00Z",
    ) -> None:
        """Register stub for `gh run view <run_id> --json ...` command."""
        run_data = {
            "id": run_id,
            "status": status,
            "conclusion": conclusion,
            "createdAt": created_at,
            "updatedAt": updated_at,
        }
        self.add_stub(
            ("gh", "run", "view", str(run_id), "--json", "id,status,conclusion,createdAt,updatedAt"),
            GhCommandStub.success(run_data),
        )

    def stub_repo_view(
        self,
        default_branch: str = "main",
        owner: str = "owner",
        name: str = "repo",
    ) -> None:
        """Register stub for `gh repo view --json defaultBranchRef` command."""
        repo_data = {
            "defaultBranchRef": {"name": default_branch},
            "owner": {"login": owner},
            "name": name,
        }
        self.add_stub(("gh", "repo", "view", "--json", "defaultBranchRef,owner,name"), GhCommandStub.success(repo_data))

    def stub_api_rate_limit_error(self, command_parts: tuple[str, ...]) -> None:
        """Register a rate limit error for any gh command."""
        self.add_stub(
            command_parts, GhCommandStub.failure("gh: API rate limit exceeded (error code: 403)", returncode=1)
        )
