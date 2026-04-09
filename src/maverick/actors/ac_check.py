"""ACCheckActor — Thespian actor for acceptance criteria verification."""

import asyncio

from thespian.actors import Actor


class ACCheckActor(Actor):
    """Deterministic AC check. Runs verification commands."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        if message.get("type") == "ac_check":
            description = message.get("description", "")
            cwd = message.get("cwd")

            try:
                result = asyncio.run(self._run_check(description, cwd))
                self.send(sender, {"type": "ac_result", **result})
            except Exception as exc:
                self.send(
                    sender,
                    {
                        "type": "ac_result",
                        "passed": False,
                        "reasons": [str(exc)],
                    },
                )

    async def _run_check(self, description, cwd):
        from pathlib import Path

        from maverick.runners.command import CommandRunner
        from maverick.workflows.fly_beads.steps import (
            _parse_verification_commands,
            _parse_work_unit_sections,
        )

        sections = _parse_work_unit_sections(description)
        verification_text = sections.get("verification", "")

        if not verification_text:
            return {"passed": True, "reasons": []}

        reasons = []
        work_cwd = Path(cwd) if cwd else Path.cwd()
        runner = CommandRunner(cwd=work_cwd)

        for cmd_str in _parse_verification_commands(verification_text):
            first_word = cmd_str.split()[0] if cmd_str.split() else ""
            if first_word not in ("rg", "grep", "cargo", "make"):
                continue
            try:
                result = await runner.run(["sh", "-c", cmd_str])
                if result.returncode != 0:
                    reasons.append(f"Verification failed: `{cmd_str}`")
            except Exception as exc:
                reasons.append(f"Verification error: `{cmd_str}`: {exc}")

        return {"passed": len(reasons) == 0, "reasons": reasons}
