"""Shared fixtures for CLI command tests.

This module provides shared fixtures and utilities for testing CLI commands.
The fixtures are scoped to the tests/unit/cli/ directory.

Common fixtures available from parent conftest.py:
- cli_runner: Click CLI test runner (from tests/conftest.py)
- temp_dir: Temporary directory for test files (from tests/conftest.py)
- clean_env: Clean environment without MAVERICK_ vars (from tests/conftest.py)
- sample_config_yaml: Sample YAML config content (from tests/conftest.py)
"""

from __future__ import annotations

# No additional fixtures needed at this time.
# The cli_runner, temp_dir, clean_env, and sample_config_yaml fixtures
# from the parent conftest.py are sufficient for all CLI command tests.
