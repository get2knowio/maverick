from __future__ import annotations

import contextlib
from collections.abc import Generator
from typing import TYPE_CHECKING

import click

from maverick.cli.context import ExitCode
from maverick.cli.output import format_error
from maverick.dsl.context_builders import register_all_context_builders
from maverick.dsl.discovery import DiscoveryResult, create_discovery
from maverick.exceptions import AgentError, GitError, MaverickError
from maverick.library.actions import register_all_actions
from maverick.library.agents import register_all_agents
from maverick.library.generators import register_all_generators
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.dsl.serialization.registry import ComponentRegistry


@contextlib.contextmanager
def cli_error_handler() -> Generator[None, None, None]:
    """Context manager for common CLI error handling.

    Handles common error patterns across CLI commands:
    - KeyboardInterrupt: Exit with code 130
    - GitError: Format error with operation details
    - AgentError: Format error with agent context
    - MaverickError: Format error with message
    - Generic exceptions: Log and format error

    Example:
        >>> with cli_error_handler():
        >>>     # Command logic here
        >>>     workflow.execute()
    """
    logger = get_logger(__name__)

    try:
        yield
    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user.", err=True)
        raise SystemExit(ExitCode.INTERRUPTED) from None
    except GitError as e:
        error_msg = format_error(
            e.message,
            details=[f"Operation: {e.operation}"] if e.operation else None,
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
    except AgentError as e:
        error_msg = format_error(e.message)
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
    except MaverickError as e:
        error_msg = format_error(e.message)
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
    except Exception as e:
        logger.exception("Unexpected error in command")
        click.echo(f"Error: {e!s}", err=True)
        raise SystemExit(ExitCode.FAILURE) from e


def create_registered_registry(strict: bool = False) -> ComponentRegistry:
    """Create a ComponentRegistry with all built-in components registered.

    This function creates a new ComponentRegistry and registers all built-in
    actions, agents, generators, context builders, and discovered workflows
    so they can be resolved by workflows.

    Args:
        strict: If True, create registry in strict mode (reference resolution
            errors will be raised immediately).

    Returns:
        ComponentRegistry with all built-in components and discovered
        workflows registered.
    """
    from maverick.dsl.discovery import load_workflows_into_registry
    from maverick.dsl.serialization.registry import ComponentRegistry

    registry = ComponentRegistry(strict=strict)

    # Register all built-in components
    register_all_actions(registry)
    register_all_agents(registry)
    register_all_generators(registry)
    register_all_context_builders(registry)

    # Register all discovered workflows and fragments
    load_workflows_into_registry(registry)

    return registry


def get_discovery_result(ctx: click.Context) -> DiscoveryResult:
    """Get or create workflow discovery result.

    Runs discovery on first call and caches result in CLI context.

    Args:
        ctx: Click context.

    Returns:
        DiscoveryResult from workflow discovery.
    """
    if "discovery_result" not in ctx.obj:
        discovery = create_discovery()
        ctx.obj["discovery_result"] = discovery.discover()
    result: DiscoveryResult = ctx.obj["discovery_result"]
    return result
