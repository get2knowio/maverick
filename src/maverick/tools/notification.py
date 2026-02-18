"""Notification MCP tools for Maverick agents.

This module provides MCP tools for sending notifications via ntfy.sh.
Tools are async functions decorated with @tool that return MCP-formatted responses.

Rate limiting is supported via aiolimiter to prevent overwhelming ntfy.sh servers.

Usage:
    from maverick.tools.notification import create_notification_tools_server

    server = create_notification_tools_server()
    agent = MaverickAgent(mcp_servers={"notification-tools": server})
"""

from __future__ import annotations

import json
from typing import Any

import aiohttp
from aiolimiter import AsyncLimiter
from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from maverick.config import NotificationConfig
from maverick.logging import get_logger

logger = get_logger(__name__)


class _RetryableNotificationError(Exception):
    """Internal exception to signal a retryable notification error."""

    pass


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

#: Default rate limit for ntfy.sh (requests per minute)
#: ntfy.sh doesn't have strict rate limits, but 30/minute is reasonable
DEFAULT_NTFY_RATE_LIMIT: int = 30

#: Time period for rate limiting in seconds (1 minute)
DEFAULT_NTFY_RATE_PERIOD: float = 60.0

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
    rate_limiter: AsyncLimiter | None = None,
) -> tuple[bool, str, str | None]:
    """Send a notification request to ntfy.sh with retry logic.

    Args:
        config: Notification configuration with server and topic.
        message: Notification body text.
        title: Optional notification title.
        priority: Priority level (min, low, default, high, urgent).
        tags: Optional list of emoji tags.
        max_retries: Maximum retry attempts (default 2).
        rate_limiter: Optional AsyncLimiter for rate limiting requests.

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

    # Define the actual request logic
    async def _make_request() -> tuple[bool, str, str | None]:
        """Make the HTTP request to ntfy.sh. Returns result tuple or raises."""
        try:
            timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(url, data=message, headers=headers) as resp,
            ):
                if resp.status == 200:
                    try:
                        response_data = await resp.json()
                    except (ValueError, aiohttp.ContentTypeError) as e:
                        # Malformed JSON response - treat as retryable
                        raise _RetryableNotificationError(
                            f"Malformed JSON response: {e}"
                        ) from e
                    notification_id = response_data.get("id")
                    logger.info("Notification sent (id: %s)", notification_id)
                    return (True, "Notification sent", notification_id)
                else:
                    resp_text = await resp.text()
                    error_msg = f"HTTP {resp.status}: {resp_text}"
                    raise _RetryableNotificationError(error_msg)
        except TimeoutError:
            raise _RetryableNotificationError("Request timed out") from None
        except aiohttp.ClientError as e:
            raise _RetryableNotificationError(f"Client error: {e}") from e

    # Retry with tenacity using exponential backoff
    last_error: str | None = None
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential(
                multiplier=RETRY_BASE_DELAY, min=RETRY_BASE_DELAY, max=4
            ),
            retry=retry_if_exception_type(_RetryableNotificationError),
            reraise=True,
        ):
            with attempt:
                attempt_num = attempt.retry_state.attempt_number
                try:
                    # Apply rate limiting if configured
                    if rate_limiter is not None:
                        async with rate_limiter:
                            return await _make_request()
                    else:
                        return await _make_request()
                except _RetryableNotificationError as e:
                    last_error = str(e)
                    logger.warning(
                        "Notification attempt %s failed: %s",
                        attempt_num,
                        last_error,
                    )
                    raise
    except _RetryableNotificationError:
        # All retries exhausted
        pass

    # All retries failed - gracefully degrade
    logger.warning(
        "Failed to deliver notification after %s attempts. Last error: %s",
        max_retries + 1,
        last_error,
    )
    return (True, "Notification not delivered", None)


# =============================================================================
# Factory Function
# =============================================================================


def create_notification_tools_server(
    config: NotificationConfig | None = None,
    rate_limit: int | None = None,
    rate_period: float | None = None,
) -> McpSdkServerConfig:
    """Create MCP server with all notification tools registered (T047).

    This factory function creates an MCP server instance with all notification
    tools registered. Configuration is optional - if not provided, uses defaults
    (notifications disabled unless topic is configured).

    Args:
        config: Notification configuration. Defaults to NotificationConfig().
        rate_limit: Optional maximum number of requests per rate_period.
            If not provided, rate limiting is disabled. Use
            DEFAULT_NTFY_RATE_LIMIT (30) for reasonable limits.
        rate_period: Time period in seconds for rate limiting.
            Defaults to DEFAULT_NTFY_RATE_PERIOD (60.0 = 1 minute).
            Only used if rate_limit is provided.

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

        # With rate limiting
        server = create_notification_tools_server(
            config,
            rate_limit=DEFAULT_NTFY_RATE_LIMIT,
            rate_period=DEFAULT_NTFY_RATE_PERIOD,
        )
        ```
    """
    # Capture config in closure scope
    _config = config if config is not None else NotificationConfig()

    # Initialize rate limiter if rate_limit is provided
    if rate_limit is not None:
        period = rate_period if rate_period is not None else DEFAULT_NTFY_RATE_PERIOD
        _rate_limiter: AsyncLimiter | None = AsyncLimiter(rate_limit, period)
        logger.info(
            "Creating notification tools MCP server (version %s) with rate limiting "
            "(%d requests per %.1f seconds)",
            SERVER_VERSION,
            rate_limit,
            period,
        )
    else:
        _rate_limiter = None
        logger.info(
            "Creating notification tools MCP server (version %s)", SERVER_VERSION
        )

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

        Raises:
            Never raises - always returns MCP response format with success or error.

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
            rate_limiter=_rate_limiter,
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

        Raises:
            Never raises - always returns MCP response format with success or error.

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
                    "send_notification called with invalid tags type: %s", type(tags)
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
                "send_notification called with invalid priority: %s", priority
            )
            valid_list = ", ".join(sorted(valid_priorities))
            return _error_response(
                f"Invalid priority '{priority}'. Must be one of: {valid_list}",
                "INVALID_INPUT",
            )

        logger.info(
            "Sending notification: message='%s...', title=%s, priority=%s, tags=%s",
            message[:50],
            title,
            priority,
            tags,
        )

        # Send notification with graceful degradation (T046)
        success, status_message, notification_id = await _send_ntfy_request(
            _config,
            message=message,
            title=title,
            priority=priority,
            tags=tags,
            rate_limiter=_rate_limiter,
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
    # Type ignore because we're adding to the dict for test purposes
    server["_tools"] = {  # type: ignore[typeddict-unknown-key]
        "send_workflow_update": send_workflow_update,
        "send_notification": send_notification,
    }

    return server
