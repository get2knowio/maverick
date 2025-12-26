from __future__ import annotations

import os
import re
import unicodedata
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from maverick.hooks.config import SafetyConfig
from maverick.logging import get_logger

logger = get_logger(__name__)

# Default dangerous bash patterns (FR-006)
DANGEROUS_BASH_PATTERNS: list[tuple[str, str]] = [
    # Recursive delete of root/home
    (
        r"rm\s+(-[rfRF]+\s+)*(/|~|\$HOME|\$\{HOME\})\s*$",
        "Recursive delete of root or home",
    ),
    (r"rm\s+(-[rfRF]+\s+)*/\*", "Recursive delete of root"),
    # Fork bombs
    (r":\(\)\s*\{.*:\|:.*\}", "Fork bomb detected"),
    # Disk formatting
    (r"mkfs\.\w+", "Disk formatting command"),
    # Raw disk write
    (r"dd\s+.*of=/dev/[a-z]+\s*$", "Raw disk write"),
    (r"dd\s+.*of=/dev/[a-z]+\d*\s*$", "Raw disk write"),
    # System shutdown
    (r"\b(shutdown|reboot|halt|poweroff)\b", "System shutdown command"),
    # Kill all processes
    (r"kill\s+-9\s+-1", "Kill all processes"),
    # Chmod 777 on system directories
    (r"chmod\s+(-R\s+)?777\s+/", "Dangerous chmod on root"),
    # Writing to passwd/shadow
    (r">\s*/etc/(passwd|shadow)", "Write to password file"),
]

# Pre-compiled dangerous patterns for performance (compiled once at module load)
_COMPILED_DANGEROUS_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(pattern, re.IGNORECASE), description, pattern)
    for pattern, description in DANGEROUS_BASH_PATTERNS
]


def normalize_command(cmd: str) -> str:
    """Normalize unicode and decode escape sequences.

    Args:
        cmd: Raw command string.

    Returns:
        Normalized command string.
    """
    # Normalize unicode to NFC form
    normalized = unicodedata.normalize("NFC", cmd)
    # Replace various whitespace characters with regular space
    normalized = re.sub(r"[\t\r\n]+", " ", normalized)
    # Handle common hex escape sequences
    try:
        normalized = normalized.encode().decode("unicode_escape")
    except (UnicodeDecodeError, UnicodeEncodeError) as e:
        logger.debug(f"Unicode normalization skipped: {e}")
    return normalized.strip()


def expand_variables(cmd: str) -> str:
    """Expand environment variables in command.

    Args:
        cmd: Command string with potential variables.

    Returns:
        Command with variables expanded.
    """
    # Expand $VAR and ${VAR} patterns
    return os.path.expandvars(cmd)


def parse_compound_command(cmd: str) -> list[str]:
    """Parse compound bash commands into components.

    Args:
        cmd: Compound command string.

    Returns:
        List of individual command components.
    """
    # Simple tokenizer that respects quotes and braces
    components: list[str] = []
    current = ""
    in_single_quote = False
    in_double_quote = False
    brace_depth = 0
    i = 0

    while i < len(cmd):
        char = cmd[i]

        # Handle quotes
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current += char
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current += char
        # Handle braces (for function definitions)
        elif not in_single_quote and not in_double_quote:
            if char == "{":
                brace_depth += 1
                current += char
            elif char == "}":
                brace_depth -= 1
                current += char
            # Check for && or ||
            elif (
                i + 1 < len(cmd) and cmd[i : i + 2] in ("&&", "||") and brace_depth == 0
            ):
                if current.strip():
                    components.append(current.strip())
                current = ""
                i += 2
                continue
            # Check for ; or | (only when not inside braces)
            elif char in ";|" and brace_depth == 0:
                if current.strip():
                    components.append(current.strip())
                current = ""
            else:
                current += char
        else:
            current += char
        i += 1

    if current.strip():
        components.append(current.strip())

    return components if components else [cmd]


def _check_compiled_patterns(
    cmd: str, compiled_patterns: list[tuple[re.Pattern[str], str, str]]
) -> tuple[bool, str | None, str | None]:
    """Check if command matches any pre-compiled dangerous pattern.

    Args:
        cmd: Command to check.
        compiled_patterns: List of (compiled_pattern, description, original_pattern).

    Returns:
        Tuple of (is_dangerous, reason, pattern).
    """
    for compiled_pattern, description, original_pattern in compiled_patterns:
        if compiled_pattern.search(cmd):
            return True, description, original_pattern
    return False, None, None


def _check_custom_patterns(
    cmd: str, patterns: list[str]
) -> tuple[bool, str | None, str | None]:
    """Check if command matches any custom blocklist pattern.

    Args:
        cmd: Command to check.
        patterns: List of custom regex pattern strings.

    Returns:
        Tuple of (is_dangerous, reason, pattern).
    """
    for pattern in patterns:
        if re.search(pattern, cmd, re.IGNORECASE):
            return True, f"Custom blocked pattern: {pattern}", pattern
    return False, None, None


async def validate_bash_command(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
    *,
    config: SafetyConfig | None = None,
) -> dict[str, Any]:
    """Validate bash commands for dangerous patterns.

    Args:
        input_data: Contains 'tool_name' and 'tool_input' with 'command' key.
        tool_use_id: SDK tool use identifier.
        context: Hook context from SDK.
        config: Optional safety configuration.

    Returns:
        Empty dict if allowed, or dict with permissionDecision='deny' if blocked.
    """
    config = config or SafetyConfig()

    try:
        # Skip if bash validation is disabled
        if not config.bash_validation_enabled:
            return {}

        # Extract command
        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command", "")

        if not command:
            # Fail closed - no command means block
            return _deny_response("No command provided", "missing_command")

        # Normalize and expand
        normalized = normalize_command(command)
        expanded = expand_variables(normalized)

        # Check allow overrides first
        for pattern in config.bash_allow_override:
            if re.search(pattern, expanded, re.IGNORECASE):
                logger.debug(f"Command allowed by override: {pattern}")
                return {}

        # Parse compound commands
        components = parse_compound_command(expanded)

        # Check each component against pre-compiled default patterns and custom patterns
        for component in components:
            # Check pre-compiled default dangerous patterns first
            is_dangerous, matched_reason, matched_pattern = _check_compiled_patterns(
                component, _COMPILED_DANGEROUS_PATTERNS
            )
            if is_dangerous:
                logger.warning(
                    f"Dangerous command blocked: {component} "
                    f"(pattern: {matched_pattern})"
                )
                return _deny_response(
                    f"Dangerous command blocked: {matched_reason}", matched_pattern
                )

            # Check custom blocklist patterns if any
            if config.bash_blocklist:
                is_dangerous, matched_reason, matched_pattern = _check_custom_patterns(
                    component, config.bash_blocklist
                )
                if is_dangerous:
                    logger.warning(
                        f"Dangerous command blocked: {component} "
                        f"(pattern: {matched_pattern})"
                    )
                    return _deny_response(
                        f"Dangerous command blocked: {matched_reason}", matched_pattern
                    )

        return {}

    except Exception as e:
        # Fail closed on any exception
        if config.fail_closed:
            logger.error(f"Hook exception (fail-closed): {e}")
            return _deny_response(f"Hook validation error: {e}", "exception")

        # Fail open - allow operation but log error
        logger.warning(f"Hook exception (fail-open): {e}")
        return {}


def _deny_response(reason: str, pattern: str | None) -> dict[str, Any]:
    """Create a deny response for the hook.

    Args:
        reason: Human-readable reason for denial.
        pattern: Pattern that triggered the block.

    Returns:
        Hook response dict with denial.
    """
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
            "blockedPattern": pattern,
        }
    }


# File Write Validation Functions (User Story 2)


def normalize_path(path: str) -> str:
    """Normalize path for consistent matching.

    Args:
        path: Path string to normalize.

    Returns:
        Normalized absolute path.
    """
    # Expand ~ and environment variables
    expanded = os.path.expanduser(os.path.expandvars(path))

    # Resolve to absolute path
    try:
        resolved = Path(expanded).resolve()
        return str(resolved)
    except (OSError, RuntimeError):
        # If resolution fails, return expanded path
        return expanded


def _matches_path_pattern(path: str, pattern: str) -> bool:
    """Check if path matches a pattern.

    Args:
        path: Normalized path to check.
        pattern: Pattern (may include wildcards or be a prefix).

    Returns:
        True if path matches pattern.
    """
    # Normalize the pattern too
    normalized_pattern = os.path.expanduser(pattern)

    # Check for glob-style patterns
    if "*" in pattern:
        basename_match = fnmatch(os.path.basename(path), pattern)
        return basename_match or fnmatch(path, normalized_pattern)

    # Check for directory patterns (ending with /)
    if pattern.endswith("/"):
        return normalized_pattern.rstrip("/") in path

    # Check for exact match or basename match
    return (
        path == normalized_pattern
        or path.endswith(f"/{pattern}")
        or os.path.basename(path) == pattern
        or normalized_pattern in path
    )


async def validate_file_write(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
    *,
    config: SafetyConfig | None = None,
) -> dict[str, Any]:
    """Validate file writes to sensitive paths.

    Args:
        input_data: Contains 'tool_name' and 'tool_input' with 'file_path' key.
        tool_use_id: SDK tool use identifier.
        context: Hook context from SDK.
        config: Optional safety configuration.

    Returns:
        Empty dict if allowed, or dict with permissionDecision='deny' if blocked.
    """
    config = config or SafetyConfig()

    try:
        # Skip if file write validation is disabled
        if not config.file_write_validation_enabled:
            return {}

        # Extract file path
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")

        if not file_path:
            # Fail closed - no path means block
            return _deny_response("No file path provided", "missing_path")

        # Normalize path
        normalized = normalize_path(file_path)

        # Check allowlist first (takes precedence)
        for pattern in config.path_allowlist:
            if _matches_path_pattern(normalized, pattern):
                logger.debug(f"Path allowed by allowlist: {pattern}")
                return {}

        # Check custom blocklist
        for pattern in config.path_blocklist:
            if _matches_path_pattern(normalized, pattern):
                logger.warning(
                    f"Path blocked by custom blocklist: {file_path} "
                    f"(pattern: {pattern})"
                )
                return _deny_response(f"Path blocked: {pattern}", pattern)

        # Check default sensitive paths
        for pattern in config.sensitive_paths:
            if _matches_path_pattern(normalized, pattern):
                logger.warning(
                    f"Sensitive path blocked: {file_path} (pattern: {pattern})"
                )
                return _deny_response(f"Sensitive path blocked: {pattern}", pattern)

        return {}

    except Exception as e:
        # Fail closed on any exception
        if config.fail_closed:
            logger.error(f"Hook exception (fail-closed): {e}")
            return _deny_response(f"Hook validation error: {e}", "exception")

        # Fail open - allow operation but log error
        logger.warning(f"Hook exception (fail-open): {e}")
        return {}
