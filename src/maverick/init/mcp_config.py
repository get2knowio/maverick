"""Write provider-specific MCP config files for supervisor inbox tools.

At `maverick init` time, writes config files that pre-define the
supervisor inbox MCP server for providers that don't support dynamic
MCP attachment via ACP (Copilot, Gemini).

Config files are written idempotently — existing configs are merged,
not overwritten. Other MCP servers and settings are preserved.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)

#: Default Thespian admin port for the supervisor inbox
DEFAULT_ADMIN_PORT = 19500

#: MCP server name used in all provider configs
SERVER_NAME = "supervisor-inbox"


def _build_server_definition(
    maverick_bin: str | None = None,
    admin_port: int = DEFAULT_ADMIN_PORT,
) -> dict[str, Any]:
    """Build the MCP server definition for the supervisor inbox.

    Returns a dict suitable for inclusion in any provider's MCP config.
    """
    from maverick.tools.supervisor_inbox.schemas import ALL_TOOL_SCHEMAS

    if maverick_bin is None:
        maverick_bin = shutil.which("maverick") or "maverick"

    all_tools = ",".join(sorted(ALL_TOOL_SCHEMAS.keys()))

    return {
        "command": maverick_bin,
        "args": [
            "serve-inbox",
            "--tools", all_tools,
            "--admin-port", str(admin_port),
        ],
    }


def write_provider_mcp_configs(
    providers: list[str],
    maverick_bin: str | None = None,
    admin_port: int = DEFAULT_ADMIN_PORT,
    project_dir: Path | None = None,
) -> dict[str, str]:
    """Write MCP config files for providers that need them.

    Args:
        providers: List of provider names (e.g., ["copilot", "gemini"]).
        maverick_bin: Path to maverick binary. Auto-detected if None.
        admin_port: Thespian admin port for the supervisor inbox.
        project_dir: Project root for project-level configs. Defaults to cwd.

    Returns:
        Dict of provider name → config file path written.
    """
    server_def = _build_server_definition(maverick_bin, admin_port)
    project = project_dir or Path.cwd()
    written: dict[str, str] = {}

    for provider in providers:
        provider = provider.strip().lower()

        if provider == "copilot":
            path = _write_copilot_config(server_def)
            if path:
                written["copilot"] = str(path)

        elif provider == "gemini":
            path = _write_gemini_config(server_def, project)
            if path:
                written["gemini"] = str(path)

        elif provider == "claude":
            # Claude supports dynamic MCP via ACP — no config file needed
            logger.debug(
                "mcp_config.claude_skip",
                msg="Claude supports dynamic MCP; no config file needed",
            )

        else:
            logger.warning(
                "mcp_config.unknown_provider",
                provider=provider,
            )

    return written


def _write_copilot_config(server_def: dict[str, Any]) -> Path | None:
    """Write/update ~/.copilot/mcp-config.json with supervisor inbox.

    Merges with existing config — preserves other MCP servers.
    """
    config_dir = Path.home() / ".copilot"
    config_path = config_dir / "mcp-config.json"

    try:
        config_dir.mkdir(parents=True, exist_ok=True)

        # Load existing config
        existing: dict[str, Any] = {}
        if config_path.exists():
            existing = json.loads(
                config_path.read_text(encoding="utf-8")
            )

        # Merge our server into mcpServers
        if "mcpServers" not in existing:
            existing["mcpServers"] = {}
        existing["mcpServers"][SERVER_NAME] = server_def

        config_path.write_text(
            json.dumps(existing, indent=2) + "\n",
            encoding="utf-8",
        )

        logger.info(
            "mcp_config.copilot_written",
            path=str(config_path),
        )
        return config_path

    except Exception as exc:
        logger.warning(
            "mcp_config.copilot_write_failed",
            error=str(exc),
        )
        return None


def _write_gemini_config(
    server_def: dict[str, Any],
    project_dir: Path,
) -> Path | None:
    """Write/update .gemini/settings.json with supervisor inbox.

    Project-level config. Merges with existing settings.
    """
    config_dir = project_dir / ".gemini"
    config_path = config_dir / "settings.json"

    try:
        config_dir.mkdir(parents=True, exist_ok=True)

        # Load existing config
        existing: dict[str, Any] = {}
        if config_path.exists():
            existing = json.loads(
                config_path.read_text(encoding="utf-8")
            )

        # Merge our server into mcpServers
        if "mcpServers" not in existing:
            existing["mcpServers"] = {}
        existing["mcpServers"][SERVER_NAME] = server_def

        config_path.write_text(
            json.dumps(existing, indent=2) + "\n",
            encoding="utf-8",
        )

        logger.info(
            "mcp_config.gemini_written",
            path=str(config_path),
        )
        return config_path

    except Exception as exc:
        logger.warning(
            "mcp_config.gemini_write_failed",
            error=str(exc),
        )
        return None
