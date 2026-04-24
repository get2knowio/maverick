"""Actor definitions for Maverick's actor-mailbox architecture.

All actors run on the xoscar runtime — see
:mod:`maverick.actors.xoscar` for the concrete implementations and
:mod:`maverick.actors.xoscar.pool` for the pool-lifecycle helpers used
by workflows.

Kept at the top level for ergonomic imports
(``from maverick.actors import RefuelSupervisor``).
"""

from __future__ import annotations

from maverick.actors.xoscar.ac_check import ACCheckActor
from maverick.actors.xoscar.bead_creator import BeadCreatorActor
from maverick.actors.xoscar.briefing import BriefingActor
from maverick.actors.xoscar.committer import CommitterActor
from maverick.actors.xoscar.decomposer import DecomposerActor
from maverick.actors.xoscar.fly_supervisor import FlyInputs, FlySupervisor
from maverick.actors.xoscar.gate import GateActor
from maverick.actors.xoscar.generator import GeneratorActor
from maverick.actors.xoscar.implementer import ImplementerActor
from maverick.actors.xoscar.plan_supervisor import PlanInputs, PlanSupervisor
from maverick.actors.xoscar.plan_validator import PlanValidatorActor
from maverick.actors.xoscar.plan_writer import PlanWriterActor
from maverick.actors.xoscar.pool import (
    DEFAULT_POOL_ADDRESS,
    actor_pool,
    create_pool,
    teardown_pool,
)
from maverick.actors.xoscar.refuel_supervisor import RefuelInputs, RefuelSupervisor
from maverick.actors.xoscar.reviewer import ReviewerActor
from maverick.actors.xoscar.spec_check import SpecCheckActor
from maverick.actors.xoscar.validator import ValidatorActor

__all__ = [
    "DEFAULT_POOL_ADDRESS",
    "ACCheckActor",
    "BeadCreatorActor",
    "BriefingActor",
    "CommitterActor",
    "DecomposerActor",
    "FlyInputs",
    "FlySupervisor",
    "GateActor",
    "GeneratorActor",
    "ImplementerActor",
    "PlanInputs",
    "PlanSupervisor",
    "PlanValidatorActor",
    "PlanWriterActor",
    "RefuelInputs",
    "RefuelSupervisor",
    "ReviewerActor",
    "SpecCheckActor",
    "ValidatorActor",
    "actor_pool",
    "create_pool",
    "teardown_pool",
]
