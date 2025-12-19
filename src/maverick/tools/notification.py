"""Notification MCP tools for Maverick agents.

This module provides MCP tools for sending notifications via ntfy.sh.
Tools are async functions decorated with @tool that return MCP-formatted responses.

Usage:
    from maverick.tools.notification import create_notification_tools_server

    server = create_notification_tools_server()
    agent = MaverickAgent(mcp_servers={"notification-tools": server})
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from claude_agent_sdk import create_sdk_mcp_server, tool

if TYPE_CHECKING:
    from mcp import FastMCP

from maverick.config import NotificationConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

#: Default timeout for HTTP requests in seconds
DEFAULT_TIMEOUT: float = 2.0

#: Base delay for exponential backoff retry in seconds
RETRY_BASE_DELAY: float = 0.5

#: MCP Server configuration
SERVER_NAME: str = "notification-tools"
SERVER_VERSION: str = "1.0.0"

#: ntfy priority mapping (name -> numeric value)
NTFY_PRIORITIES: dict[str, int] = {
    "min": 1,
    "low": 2,
    "default": 3,
    "high": 4,
    "urgent": 5,
}

#: Workflow stage to priority/tags mapping
STAGE_MAPPING: dict[str, dict[str, Any]] = {
    "start": {"priority": "default", "tags": ["rocket"]},
    "implementation": {"priority": "default", "tags": ["hammer"]},
    "review": {"priority": "default", "tags": ["mag"]},
    "validation": {"priority": "default", "tags": ["white_check_mark"]},
    "complete": {"priority": "high", "tags": ["tada"]},
    "error": {"priority": "urgent", "tags": ["x", "warning"]},
}


# =============================================================================
# Helper Functions
# =============================================================================


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    """Create MCP success response.

    Args:
        data: Response data to be JSON-serialized.

    Returns:
        MCP-formatted success response.
    """
    return {"content": [{"type": "text", "text": json.dumps(data)}]}


def _error_response(
    message: str,
    error_code: str,
    retry_after_seconds: int | None = None,
) -> dict[str, Any]:
    """Create MCP error response.

    Args:
        message: Human-readable error message.
        error_code: Machine-readable error code.
        retry_after_seconds: Optional retry delay suggestion.

    Returns:
        MCP-formatted error response.
    """
    error_data: dict[str, Any] = {
        "isError": True,
        "message": message,
        "error_code": error_code,
    }
    if retry_after_seconds is not None:
        error_data["retry_after_seconds"] = retry_after_seconds
    return {"content": [{"type": "text", "text": json.dumps(error_data)}]}


async def _send_ntfy_request(
    config: NotificationConfig,
    message: str,
    title: str | None = None,
    priority: str = "default",
    tags: list[str] | None = None,
    max_retries: int = 2,
) -> tuple[bool, str, str | None]:
    """Send a notification request to ntfy.sh with retry logic.

    Args:
        config: Notification configuration with server and topic.
        message: Notification body text.
        title: Optional notification title.
        priority: Priority level (min, low, default, high, urgent).
        tags: Optional list of emoji tags.
        max_retries: Maximum retry attempts (default 2).

    Returns:
        Tuple of (success, message, notification_id).
        - success: True if notification was sent or gracefully handled
        - message: Status message (e.g., "Notification sent", "Notifications disabled")
        - notification_id: ntfy response ID if available, None otherwise
    """
    # Check if notifications are disabled
    if not config.topic:
        logger.debug("Notifications disabled (no topic configured)")
        return (True, "Notifications disabled", None)

    # Build request URL and headers
    url = f"{config.server}/{config.topic}"
    headers = {
        "Priority": str(NTFY_PRIORITIES.get(priority, NTFY_PRIORITIES["default"])),
    }
    if title:
        headers["Title"] = title
    if tags:
        headers["Tags"] = ",".join(tags)

    # Retry loop
    last_error: str | None = None
    for attempt in range(max_retries + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(url, data=message, headers=headers) as response,
            ):
                if response.status == 200:
                    response_data = await response.json()
                    notification_id = response_data.get("id")
                    logger.info(
                        f"Notification sent successfully (id: {notification_id})"
                    )
                    return (True, "Notification sent", notification_id)
                else:
                    last_error = f"HTTP {response.status}: {await response.text()}"
                    logger.warning(
                        f"Notification attempt {attempt + 1} failed: {last_error}"
                    )
        except asyncio.TimeoutError:
            last_error = "Request timed out"
            logger.warning(f"Notification attempt {attempt + 1} timed out")
        except aiohttp.ClientError as e:
            last_error = f"Client error: {e}"
            logger.warning(f"Notification attempt {attempt + 1} failed: {last_error}")
        except Exception as e:
            last_error = f"Unexpected error: {e}"
            logger.warning(f"Notification attempt {attempt + 1} failed: {last_error}")

        # Wait before retry (except on last attempt)
        if attempt < max_retries:
            await asyncio.sleep(RETRY_BASE_DELAY * (attempt + 1))  # Exponential backoff

    # All retries failed - gracefully degrade
    logger.warning(
        f"Failed to deliver notification after {max_retries + 1} attempts. "
        f"Last error: {last_error}"
    )
    return (True, "Notification not delivered", None)


# =============================================================================
# Factory Function
# =============================================================================


def create_notification_tools_server(
    config: NotificationConfig | None = None,
) -> FastMCP:
    """Create MCP server with all notification tools registered (T047).

    This factory function creates an MCP server instance with all notification
    tools registered. Configuration is optional - if not provided, uses defaults
    (notifications disabled unless topic is configured).

    Args:
        config: Notification configuration. Defaults to NotificationConfig().

    Returns:
        Configured MCP server instance.

    Example:
        ```python
        from maverick.tools.notification import create_notification_tools_server
        from maverick.config import NotificationConfig

        config = NotificationConfig(topic="my-topic")
        server = create_notification_tools_server(config)
        agent = MaverickAgent(
            mcp_servers={"notification-tools": server},
            allowed_tools=["mcp__notification-tools__send_workflow_update"],
        )
        ```
    """
    # Capture config in closure scope
    _config = config if config is not None else NotificationConfig()

    logger.info("Creating notification tools MCP server (version %s)", SERVER_VERSION)

    # =============================================================================
    # MCP Tools (defined within factory to capture config in closure)
    # =============================================================================

    @tool(
        "send_workflow_update",
        "Send a workflow progress notification with stage-appropriate formatting",
        {"stage": str, "message": str, "workflow_name": str},
    )
    async def send_workflow_update(args: dict[str, Any]) -> dict[str, Any]:
        """Send workflow stage notification with automatic priority/tag mapping.

        Automatically applies priority and tags based on workflow stage using
        STAGE_MAPPING. Title is formatted as "{emoji} {workflow_name} {Stage}"
        based on stage.

        Args:
            args: Dictionary containing:
                - stage: Workflow stage (start, implementation, review,
                  validation, complete, error)
                - message: Update message body
                - workflow_name: Optional workflow identifier (default: "Workflow")

        Returns:
            MCP-formatted success or error response.

        Example:
            >>> await send_workflow_update({
            ...     "stage": "complete",
            ...     "message": "All tasks finished successfully",
            ...     "workflow_name": "FlyWorkflow"
            ... })
            {"content": [{"type": "text",
                "text": '{"success": true, "message": "Notification sent"}'}]}
        """
        stage = args["stage"]
        message = args["message"]
        workflow_name = args.get("workflow_name", "Workflow")

        # Validate stage
        if stage not in STAGE_MAPPING:
            valid_stages = ", ".join(STAGE_MAPPING.keys())
            return _error_response(
                f"Invalid stage '{stage}'. Must be one of: {valid_stages}",
                "INVALID_INPUT",
            )

        # Get stage configuration
        stage_config = STAGE_MAPPING[stage]
        priority = stage_config["priority"]
        tags = stage_config["tags"]

        # Format title based on stage
        # Map emoji tag names to actual emoji
        emoji_map = {
            "rocket": "🚀",
            "hammer": "🔨",
            "mag": "🔍",
            "white_check_mark": "✅",
            "tada": "🎉",
            "x": "❌",
        }

        # Get first emoji for title
        stage_emoji = emoji_map.get(tags[0], "")

        # Format stage name for title
        stage_names = {
            "start": "Started",
            "implementation": "Implementation Update",
            "review": "Code Review",
            "validation": "Validation",
            "complete": "Complete",
            "error": "Error",
        }
        stage_display = stage_names.get(stage, stage.capitalize())

        # Build title
        if stage in ("start", "complete", "error"):
            title = f"{stage_emoji} {workflow_name} {stage_display}"
        else:
            title = f"{stage_emoji} {stage_display}"

        logger.info(
            "Sending workflow update: stage=%s, workflow=%s, priority=%s",
            stage,
            workflow_name,
            priority,
        )

        # Send notification
        success, status_message, notification_id = await _send_ntfy_request(
            config=_config,
            message=message,
            title=title,
            priority=priority,
            tags=tags,
        )

        # Build response
        response_data: dict[str, Any] = {
            "success": True,
            "message": status_message,
        }

        if notification_id:
            response_data["notification_id"] = notification_id

        # Add warning if notification wasn't delivered
        if status_message == "Notification not delivered":
            response_data["warning"] = "ntfy.sh server unreachable after retries"
        elif status_message == "Notifications disabled":
            response_data["message"] = "Notifications disabled (no topic configured)"

        logger.debug("Workflow update response: %s", response_data)

        return _success_response(response_data)

    @tool(
        "send_notification",
        "Send a custom push notification via ntfy.sh",
        {"message": str, "title": str, "priority": str, "tags": list},
    )
    async def send_notification(args: dict[str, Any]) -> dict[str, Any]:
        """Send a custom notification with full control over parameters (T044-T046).

        This tool allows agents to send arbitrary notifications beyond workflow
        updates. Useful for security alerts, manual intervention requests, or
        other custom notifications.

        Args via args dict:
            message: Notification body text (required).
            title: Optional notification title.
            priority: Optional priority level - must be one of: min, low,
                default, high, urgent.
            tags: Optional list of emoji tag strings for ntfy.sh.

        Returns:
            MCP success response with:
            - success: true
            - message: Status message ("Notification sent",
                "Notifications disabled", etc.)
            - notification_id: ntfy response ID if available
            - warning: Present if retry was needed or server unreachable

        Example:
            ```python
            result = await send_notification({
                "message": "Credential detected in code",
                "title": "Security Alert",
                "priority": "urgent",
                "tags": ["warning", "security"]
            })
            # Returns: {"success": true, "message": "Notification sent",
            #           "notification_id": "abc123"}
            ```
        """
        # Extract and validate message (required)
        message = args.get("message", "").strip()
        if not message:
            logger.warning("send_notification called with empty message")
            return _error_response(
                "Notification message cannot be empty",
                "INVALID_INPUT",
            )

        # Extract optional parameters
        title = args.get("title")
        if title is not None:
            title = str(title).strip() if title else None

        priority = args.get("priority", "default")
        if priority is not None:
            priority = str(priority).lower()

        tags = args.get("tags")
        if tags is not None:
            # Validate tags is a list
            if not isinstance(tags, list):
                logger.warning(
                    f"send_notification called with invalid tags type: {type(tags)}"
                )
                return _error_response(
                    "Tags must be a list of strings",
                    "INVALID_INPUT",
                )
            # Convert all tags to strings
            tags = [str(tag) for tag in tags]

        # Validate priority (T045)
        valid_priorities = {"min", "low", "default", "high", "urgent"}
        if priority not in valid_priorities:
            logger.warning(
                f"send_notification called with invalid priority: {priority}"
            )
            valid_list = ", ".join(sorted(valid_priorities))
            return _error_response(
                f"Invalid priority '{priority}'. Must be one of: {valid_list}",
                "INVALID_INPUT",
            )

        logger.info(
            f"Sending notification: message='{message[:50]}...', title={title}, "
            f"priority={priority}, tags={tags}"
        )

        # Send notification with graceful degradation (T046)
        success, status_message, notification_id = await _send_ntfy_request(
            _config,
            message=message,
            title=title,
            priority=priority,
            tags=tags,
        )

        # Build response
        response_data: dict[str, Any] = {
            "success": True,
            "message": status_message,
        }

        if notification_id:
            response_data["notification_id"] = notification_id

        # Add warning if notification wasn't delivered or was disabled
        if status_message == "Notification not delivered":
            response_data["warning"] = "ntfy.sh server unreachable after 2 attempts"
        elif status_message == "Notifications disabled":
            response_data["message"] = "Notifications disabled (no topic configured)"

        return _success_response(response_data)

    # Create and return MCP server with all tools
    server = create_sdk_mcp_server(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        tools=[
            send_workflow_update,
            send_notification,
        ],
    )

    # Store tool functions for test access
    # This allows tests to call tools directly while keeping config in closure
    server["_test_tools"] = {
        "send_workflow_update": send_workflow_update,
        "send_notification": send_notification,
    }

    return server
