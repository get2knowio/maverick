"""VCS abstraction layer.

Provides a :class:`VcsRepository` protocol that both
:class:`~maverick.git.repository.AsyncGitRepository` and
:class:`~maverick.jj.repository.JjRepository` satisfy, plus a factory
function :func:`create_vcs_repository` for automatic backend detection.
"""

from __future__ import annotations

from maverick.vcs.factory import create_vcs_repository
from maverick.vcs.protocol import VcsRepository

__all__ = [
    "VcsRepository",
    "create_vcs_repository",
]
