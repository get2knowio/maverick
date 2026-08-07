"""``ProtectionPolicy`` (decision engine) + ``PermissionGate`` (Layer 1).

``ProtectionPolicy.decide(...)`` is the single source of truth both
enforcement layers consult: :class:`PermissionGate` (pre-write, airframe
``PermissionCallback``) and the backstop (:mod:`maverick.protection.snapshot`,
via its own per-path checks during the post-step scan).

See ``specs/056-context-file-protection/data-model.md`` (``ProtectionPolicy``
and ``PermissionGate`` sections) for the normative decision algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from maverick.logging import get_logger
from maverick.protection.matching import (
    compile_globs,
    is_default_protected,
    matches_glob,
    normalize_relpath,
)
from maverick.protection.records import BlockRecord

if TYPE_CHECKING:
    import pathspec
    from airframe.permission import PermissionDecision, PermissionRequest

    from maverick.protection.config import ProtectionConfig
    from maverick.protection.records import BlockCollector

logger = get_logger(__name__)

__all__ = [
    "FILE_WRITE_TOOL_SPECS",
    "Operation",
    "PermissionGate",
    "PolicyDecision",
    "ProtectionPolicy",
    "WriteToolSpec",
]

#: Operations a policy decision may be evaluated against. ``"restore"``
#: (the backstop's own record operation) is intentionally excluded — it is
#: never the input to a decision, only the recorded output of one.
Operation = Literal["create", "edit", "delete", "rename"]


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """The outcome of :meth:`ProtectionPolicy.decide`.

    Attributes:
        blocked: Whether the operation targets a protected path.
        rule: Human-readable label naming the rule that matched (empty
            when ``blocked`` is ``False``).
        reason: Human-readable explanation, suitable for a permission-deny
            message or a :class:`~maverick.protection.records.BlockRecord`
            ``detail``.
    """

    blocked: bool
    rule: str
    reason: str


@dataclass(frozen=True)
class ProtectionPolicy:
    """The effective protection rule set for one run.

    Constructed once per squadron open via :meth:`build`. Immutable —
    the compiled ``pathspec`` specs and resolved root are fixed for the
    run's lifetime.
    """

    root: Path
    extra_spec: pathspec.PathSpec
    allow_spec: pathspec.PathSpec
    dropped_patterns: tuple[str, ...] = field(default=())

    @classmethod
    def build(cls, root: Path, config: ProtectionConfig | None = None) -> ProtectionPolicy:
        """Construct the policy for ``root`` from a validated ``config``.

        Args:
            root: The policy root — the agent's cwd (checkout or spec-chain
                workspace). Resolved once here.
            config: The validated ``protection:`` block. ``None`` means
                defaults-only (no ``additional_globs``/``allowlist``).

        Returns:
            The compiled, immutable policy. Individually invalid glob
            patterns are dropped (with a warning logged here) rather than
            failing construction — a bad pattern narrows toward defaults,
            never blocks startup.
        """
        from maverick.protection.config import ProtectionConfig as _ProtectionConfig

        cfg = config if config is not None else _ProtectionConfig()
        extra_spec, dropped_extra = compile_globs(cfg.additional_globs)
        allow_spec, dropped_allow = compile_globs(cfg.allowlist)

        for pattern in dropped_extra:
            logger.warning(
                "protection_glob_pattern_invalid", field="additional_globs", pattern=pattern
            )
        for pattern in dropped_allow:
            logger.warning("protection_glob_pattern_invalid", field="allowlist", pattern=pattern)

        return cls(
            root=root.resolve(),
            extra_spec=extra_spec,
            allow_spec=allow_spec,
            dropped_patterns=(*dropped_extra, *dropped_allow),
        )

    def _candidate_protected(self, relpath: str) -> tuple[bool, str]:
        """Evaluate one normalized candidate path against the rule set.

        Allowlist is evaluated first and exempts *this candidate only* —
        per data-model.md's decision algorithm, an allowlist match on one
        side (literal or resolved) does not exempt the other side.
        """
        if matches_glob(relpath, self.allow_spec):
            return False, ""
        if is_default_protected(relpath):
            return True, f"default protected name ({relpath})"
        if matches_glob(relpath, self.extra_spec):
            return True, f"additional_globs pattern ({relpath})"
        return False, ""

    def protects_relpath(self, relpath: str) -> tuple[bool, str]:
        """Evaluate an already-normalized, root-relative POSIX path.

        The cheap membership probe for callers that produced ``relpath``
        themselves and therefore need neither the relative-to-root
        normalization nor the symlink resolution :meth:`decide` performs
        — notably the backstop's tree walk, where the two
        :meth:`Path.resolve` syscalls per file that ``decide`` implies
        dominate the whole snapshot pass.

        Args:
            relpath: POSIX-style path relative to :attr:`root`.

        Returns:
            ``(protected, rule)`` — ``rule`` is empty when not protected.
        """
        return self._candidate_protected(relpath)

    def _side_protected(self, candidate: str | Path) -> tuple[bool, str]:
        """Evaluate both the literal and resolved forms of one path.

        Protected if either candidate matches (FR-014 — catches a symlink
        planted at a protected location via the literal side, and a
        symlink pointing at a protected target via the resolved side).
        """
        for resolve in (False, True):
            relpath = normalize_relpath(candidate, root=self.root, resolve=resolve)
            if relpath is None:
                continue
            protected, rule = self._candidate_protected(relpath)
            if protected:
                return True, rule
        return False, ""

    def decide(
        self,
        path: str | Path,
        operation: Operation,
        destination: str | Path | None = None,
    ) -> PolicyDecision:
        """Decide whether ``operation`` on ``path`` (and optional ``destination``)
        is protected.

        Rename operations (``destination`` non-``None``) are blocked if
        *either* side is protected (FR-003) — a bead moving an unprotected
        file onto a protected path, or moving a protected file away, both
        count as a mutation of the protected set.

        An internal error during evaluation fails closed for the default
        protected names (a best-effort literal-string basename match) and
        open otherwise — the backstop remains the guarantee either way
        (FR-011).

        Args:
            path: The primary target path (source, for renames).
            operation: The attempted operation.
            destination: The rename destination, when ``operation`` is
                effectively a rename. ``None`` for create/edit/delete.

        Returns:
            The decision, with a human-readable ``rule``/``reason`` when
            blocked.
        """
        try:
            path_blocked, path_rule = self._side_protected(path)
            if path_blocked:
                return PolicyDecision(
                    blocked=True,
                    rule=path_rule,
                    reason=f"{operation} targets protected path {path!s} — {path_rule}",
                )
            if destination is not None:
                dest_blocked, dest_rule = self._side_protected(destination)
                if dest_blocked:
                    return PolicyDecision(
                        blocked=True,
                        rule=dest_rule,
                        reason=(
                            f"{operation} targets protected destination "
                            f"{destination!s} — {dest_rule}"
                        ),
                    )
            return PolicyDecision(blocked=False, rule="", reason="")
        except Exception as exc:  # noqa: BLE001 — fail closed, see FR-011
            logger.warning(
                "protection_policy_decide_failed",
                path=str(path),
                destination=str(destination) if destination is not None else None,
                error=str(exc),
            )
            return self._fail_closed(path, destination)

    @staticmethod
    def _fail_closed(path: str | Path, destination: str | Path | None) -> PolicyDecision:
        """Best-effort literal-name fallback when :meth:`decide` itself errors.

        Denies only when a candidate's basename literally (case-insensitive)
        matches a default protected name — no filesystem access, no
        ``pathspec`` evaluation (the thing that just failed). Everything
        else is allowed; the backstop still carries the guarantee.
        """
        for candidate in (path, destination):
            if candidate is None:
                continue
            name = Path(str(candidate)).name.lower()
            if name in ("agents.md", "claude.md"):
                return PolicyDecision(
                    blocked=True,
                    rule="fail-closed default-name match",
                    reason=(
                        "internal error evaluating protection policy; denying by "
                        f"literal basename match on {candidate!s}"
                    ),
                )
        return PolicyDecision(
            blocked=False,
            rule="",
            reason="internal error evaluating protection policy; allowed (backstop still applies)",
        )


# ----------------------------------------------------------------------------
# Layer 1 — pre-write permission gate
# ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WriteToolSpec:
    """How to read a protected-path candidate out of one file-write tool's args.

    Attributes:
        operation: The :data:`Operation` this tool performs. ``Write`` is
            classified ``"edit"`` — it may create or overwrite, and the
            distinction isn't knowable pre-write; ``"edit"`` is the safe,
            conservative label (still denies either way).
        path_fields: ``tool_args`` keys that carry the primary target
            path. The first present, non-empty key wins.
        destination_fields: ``tool_args`` keys carrying a rename
            destination, when this tool renames/moves. ``None`` for
            non-rename tools.
    """

    operation: Operation
    path_fields: tuple[str, ...]
    destination_fields: tuple[str, ...] | None = None


#: Known file-write tool names → how to extract their target path(s).
#: Covers the Claude Agent SDK's native tool set (``Write``/``Edit``/
#: ``MultiEdit``/``NotebookEdit``, argument names verified against
#: ``claude_agent_sdk``) plus generic aliases seen across other adapters'
#: tool-calling conventions (``path``, ``old_path``/``new_path``). A tool
#: not listed here — including every Bash-like/exec tool — is not parsed
#: for embedded paths (research.md R4: heuristic command-string parsing is
#: out of scope; the backstop covers that channel deterministically) and
#: falls through to ``"allow"``.
FILE_WRITE_TOOL_SPECS: dict[str, WriteToolSpec] = {
    "Write": WriteToolSpec(operation="edit", path_fields=("file_path",)),
    "Edit": WriteToolSpec(operation="edit", path_fields=("file_path",)),
    "MultiEdit": WriteToolSpec(operation="edit", path_fields=("file_path",)),
    "NotebookEdit": WriteToolSpec(operation="edit", path_fields=("notebook_path",)),
    "str_replace_editor": WriteToolSpec(operation="edit", path_fields=("path", "file_path")),
    "create_file": WriteToolSpec(operation="create", path_fields=("path", "file_path")),
    "delete_file": WriteToolSpec(operation="delete", path_fields=("path", "file_path")),
    "rename_file": WriteToolSpec(
        operation="rename",
        path_fields=("old_path", "source_path", "path"),
        destination_fields=("new_path", "destination_path"),
    ),
    "move_file": WriteToolSpec(
        operation="rename",
        path_fields=("old_path", "source_path", "path"),
        destination_fields=("new_path", "destination_path"),
    ),
}


def _extract_path(tool_args: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field_name in fields:
        value = tool_args.get(field_name)
        if isinstance(value, str) and value:
            return value
    return None


@dataclass(frozen=True, slots=True)
class PermissionGate:
    """The airframe ``PermissionCallback`` implementation (Layer 1).

    Attach via ``runtime.session(on_permission=PermissionGate(policy, collector,
    agent_role=..., workflow=...))`` — one instance can be reused across a
    session's full lifetime (and across rotated sessions, since
    ``agent_role``/``workflow`` never change for a given agent). ``bead_id``
    is deliberately *not* a frozen field — it changes every bead while a
    session/gate instance may outlive several beads, so it's read fresh on
    every call from :func:`~maverick.agents.context.current_tags` (the same
    ambient-tag mechanism :meth:`Agent._emit_cost` uses).
    """

    policy: ProtectionPolicy
    collector: BlockCollector
    agent_role: str
    workflow: str

    async def handle(self, request: PermissionRequest) -> PermissionDecision:
        """Decide whether to allow, deny, or defer ``request``.

        Tools this gate has no opinion about — every Bash-like/exec tool,
        every MCP tool, every file-write tool whose target couldn't be
        extracted — return ``"defer"``, **not** ``"allow"``. The
        distinction is load-bearing: attaching ``on_permission=`` at all
        replaces the vendor's own permission policy, and on adapters
        where the two decisions differ (Copilot maps ``"allow"`` to
        ``PermissionDecisionApproveOnce`` but ``"defer"`` to
        ``PermissionDecisionUserNotAvailable``, i.e. "SDK default takes
        over") returning ``"allow"`` would silently auto-approve every
        tool the vendor used to gate. ``"defer"`` reproduces the
        pre-protection behavior exactly. A protected match returns
        ``"deny"`` and records a ``layer="pre-write"``
        :class:`BlockRecord`. An exception inside this method is caught
        and treated as fail-closed for default names (matching
        :meth:`ProtectionPolicy._fail_closed`), never allowed to
        propagate and kill the session.
        """
        from maverick.agents.context import current_tags

        bead_id = current_tags().get("bead_id") or None
        try:
            spec = FILE_WRITE_TOOL_SPECS.get(request.tool_name)
            if spec is None:
                return "defer"

            target = _extract_path(request.tool_args, spec.path_fields)
            if target is None:
                # Tool matched but no target extractable — nothing to
                # evaluate; defer to the vendor's own policy.
                return "defer"

            destination = (
                _extract_path(request.tool_args, spec.destination_fields)
                if spec.destination_fields
                else None
            )
            operation: Operation = "rename" if destination else spec.operation

            decision = self.policy.decide(target, operation, destination=destination)
            if not decision.blocked:
                return "allow"

            self.collector.append(
                BlockRecord(
                    agent_role=self.agent_role,
                    workflow=self.workflow,
                    operation=operation,
                    path=target,
                    destination_path=destination,
                    layer="pre-write",
                    bead_id=bead_id,
                    detail=decision.reason,
                )
            )
            return "deny"
        except Exception as exc:  # noqa: BLE001 — never kill the session; fail closed
            logger.warning(
                "protection_permission_gate_failed",
                tool_name=getattr(request, "tool_name", "?"),
                error=str(exc),
            )
            try:
                args = getattr(request, "tool_args", None) or {}
                target = args.get("file_path") or args.get("path") or ""
                fallback = self.policy._fail_closed(  # noqa: SLF001 — same-package internal reuse
                    target, None
                )
                if not fallback.blocked:
                    return "defer"
                self.collector.append(
                    BlockRecord(
                        agent_role=self.agent_role,
                        workflow=self.workflow,
                        operation="edit",
                        path=str(target),
                        destination_path=None,
                        layer="pre-write",
                        bead_id=bead_id,
                        detail=fallback.reason,
                    )
                )
                return "deny"
            except Exception as inner:  # noqa: BLE001 — the handler itself must never raise
                logger.warning("protection_permission_gate_fallback_failed", error=str(inner))
                return "defer"
