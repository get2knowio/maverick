"""Maverick MCP tool definitions and servers.

This package provides Claude MCP tool implementations for integration with
Claude Agent SDK workflows, including GitHub CLI wrappers and utilities.
"""
from __future__ import annotations

from maverick.tools.github import create_github_tools_server

__all__ = ["create_github_tools_server"]
