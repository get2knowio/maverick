"""Tests for maverick.flight.models module.

T007: FlightPlan, SuccessCriterion, CompletionStatus, Scope model tests.
T012: WorkUnit, AcceptanceCriterion, FileScope model tests.

Tests are written before implementation (TDD) and must fail until models
are implemented.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

if TYPE_CHECKING:
    from maverick.flight.models import FlightPlan, WorkUnit

# ===========================================================================
# T007: FlightPlan model tests
# ===========================================================================


class TestSuccessCriterion:
    """Tests for SuccessCriterion model."""

    def test_checked_criterion(self) -> None:
        """SuccessCriterion with checked=True is created correctly."""
        from maverick.flight.models import SuccessCriterion

        sc = SuccessCriterion(text="Users can register", checked=True)
        assert sc.text == "Users can register"
        assert sc.checked is True

    def test_unchecked_criterion(self) -> None:
        """SuccessCriterion with checked=False is created correctly."""
        from maverick.flight.models import SuccessCriterion

        sc = SuccessCriterion(text="Users can log in", checked=False)
        assert sc.checked is False

    def test_frozen_immutability(self) -> None:
        """SuccessCriterion is frozen — mutation raises an error."""
        from maverick.flight.models import SuccessCriterion

        sc = SuccessCriterion(text="item", checked=False)
        with pytest.raises((TypeError, ValidationError)):
            sc.checked = True  # type: ignore[misc]

    def test_empty_text_raises(self) -> None:
        """Empty text raises ValidationError."""
        from maverick.flight.models import SuccessCriterion

        with pytest.raises(ValidationError):
            SuccessCriterion(text="", checked=False)


class TestCompletionStatus:
    """Tests for CompletionStatus model."""

    def test_some_checked(self) -> None:
        """CompletionStatus with some checked items has correct percentage."""
        from maverick.flight.models import CompletionStatus

        cs = CompletionStatus(checked=1, total=3, percentage=33.333333333333336)
        assert cs.checked == 1
        assert cs.total == 3
        assert cs.percentage is not None
        assert abs(cs.percentage - 33.33) < 1.0

    def test_all_checked_percentage_100(self) -> None:
        """CompletionStatus with all checked has percentage=100.0."""
        from maverick.flight.models import CompletionStatus

        cs = CompletionStatus(checked=3, total=3, percentage=100.0)
        assert cs.percentage == 100.0

    def test_none_checked_percentage_0(self) -> None:
        """CompletionStatus with none checked has percentage=0.0."""
        from maverick.flight.models import CompletionStatus

        cs = CompletionStatus(checked=0, total=3, percentage=0.0)
        assert cs.percentage == 0.0

    def test_zero_total_percentage_none(self) -> None:
        """CompletionStatus with zero total has percentage=None."""
        from maverick.flight.models import CompletionStatus

        cs = CompletionStatus(checked=0, total=0, percentage=None)
        assert cs.percentage is None

    def test_frozen_immutability(self) -> None:
        """CompletionStatus is frozen."""
        from maverick.flight.models import CompletionStatus

        cs = CompletionStatus(checked=1, total=2, percentage=50.0)
        with pytest.raises((TypeError, ValidationError)):
            cs.checked = 2  # type: ignore[misc]


class TestScope:
    """Tests for Scope model."""

    def test_all_subsections(self) -> None:
        """Scope with all subsections populated."""
        from maverick.flight.models import Scope

        scope = Scope(
            in_scope=("Registration endpoint", "Login endpoint"),
            out_of_scope=("OAuth providers",),
            boundaries=("JWT tokens expire after 24 hours",),
        )
        assert "Registration endpoint" in scope.in_scope
        assert "OAuth providers" in scope.out_of_scope
        assert len(scope.boundaries) == 1

    def test_empty_subsections(self) -> None:
        """Scope with empty subsections is valid."""
        from maverick.flight.models import Scope

        scope = Scope(in_scope=(), out_of_scope=(), boundaries=())
        assert scope.in_scope == ()
        assert scope.out_of_scope == ()

    def test_frozen_immutability(self) -> None:
        """Scope is frozen."""
        from maverick.flight.models import Scope

        scope = Scope(in_scope=("item",), out_of_scope=(), boundaries=())
        with pytest.raises((TypeError, ValidationError)):
            scope.in_scope = ("other",)  # type: ignore[misc]

    def test_in_scope_is_tuple(self) -> None:
        """in_scope is a tuple even when constructed with a list."""
        from maverick.flight.models import Scope

        scope = Scope(in_scope=["a", "b"], out_of_scope=[], boundaries=[])  # type: ignore[arg-type]
        assert isinstance(scope.in_scope, tuple)


class TestFlightPlan:
    """Tests for FlightPlan model."""

    def _make_flight_plan(self) -> FlightPlan:
        """Build a valid FlightPlan from sample data."""
        from maverick.flight.models import FlightPlan, Scope, SuccessCriterion

        return FlightPlan(
            name="setup-authentication",
            version="1.0",
            created=date(2026, 2, 27),
            tags=("auth", "security"),
            objective="Implement user authentication with JWT tokens.",
            success_criteria=(
                SuccessCriterion(
                    text="Users can register with email and password", checked=True
                ),
                SuccessCriterion(
                    text="Users can log in and receive a JWT", checked=False
                ),
                SuccessCriterion(
                    text="Protected routes reject unauthenticated requests",
                    checked=False,
                ),
            ),
            scope=Scope(
                in_scope=("Registration endpoint", "Login endpoint", "JWT middleware"),
                out_of_scope=("OAuth providers", "Password reset flow"),
                boundaries=("JWT tokens expire after 24 hours",),
            ),
            context="Building on the existing Express.js API framework.",
            constraints=(
                "Must use bcrypt for password hashing",
                "Token secret from environment variable",
            ),
            notes="Consider adding refresh tokens in a follow-up.",
        )

    def test_construction_all_fields(self) -> None:
        """FlightPlan can be constructed with all fields."""
        fp = self._make_flight_plan()
        from maverick.flight.models import FlightPlan

        assert isinstance(fp, FlightPlan)

    def test_required_fields_accessible(self) -> None:
        """All required fields are accessible on the model."""
        fp = self._make_flight_plan()

        assert fp.name == "setup-authentication"
        assert fp.version == "1.0"
        assert fp.created == date(2026, 2, 27)
        assert "auth" in fp.tags

    def test_frozen_immutability(self) -> None:
        """FlightPlan is frozen — mutation raises an error."""
        fp = self._make_flight_plan()
        with pytest.raises((TypeError, ValidationError)):
            fp.name = "changed"  # type: ignore[misc]

    def test_completion_some_checked(self) -> None:
        """completion property returns correct status when some criteria checked."""
        fp = self._make_flight_plan()

        status = fp.completion
        assert status.checked == 1
        assert status.total == 3
        assert status.percentage is not None
        assert abs(status.percentage - 33.333) < 0.5

    def test_completion_all_checked(self) -> None:
        """completion returns 100% when all criteria checked."""
        from maverick.flight.models import FlightPlan, Scope, SuccessCriterion

        fp = FlightPlan(
            name="plan",
            version="1.0",
            created=date(2026, 1, 1),
            tags=("test",),
            objective="Do something",
            success_criteria=(
                SuccessCriterion(text="A", checked=True),
                SuccessCriterion(text="B", checked=True),
            ),
            scope=Scope(in_scope=(), out_of_scope=(), boundaries=()),
        )
        assert fp.completion.percentage == 100.0

    def test_completion_none_checked(self) -> None:
        """completion returns 0% when no criteria checked."""
        from maverick.flight.models import FlightPlan, Scope, SuccessCriterion

        fp = FlightPlan(
            name="plan",
            version="1.0",
            created=date(2026, 1, 1),
            tags=("test",),
            objective="Do something",
            success_criteria=(
                SuccessCriterion(text="A", checked=False),
                SuccessCriterion(text="B", checked=False),
            ),
            scope=Scope(in_scope=(), out_of_scope=(), boundaries=()),
        )
        assert fp.completion.percentage == 0.0

    def test_completion_zero_criteria_percentage_none(self) -> None:
        """completion returns percentage=None when there are zero criteria."""
        from maverick.flight.models import FlightPlan, Scope

        fp = FlightPlan(
            name="plan",
            version="1.0",
            created=date(2026, 1, 1),
            tags=("test",),
            objective="Do something",
            success_criteria=(),
            scope=Scope(in_scope=(), out_of_scope=(), boundaries=()),
        )
        status = fp.completion
        assert status.total == 0
        assert status.checked == 0
        assert status.percentage is None

    def test_optional_fields_have_defaults(self) -> None:
        """Optional fields (context, constraints, notes) have sensible defaults."""
        from maverick.flight.models import FlightPlan, Scope

        fp = FlightPlan(
            name="plan",
            version="1.0",
            created=date(2026, 1, 1),
            tags=(),
            objective="Something",
            success_criteria=(),
            scope=Scope(in_scope=(), out_of_scope=(), boundaries=()),
        )
        assert fp.context == ""
        assert fp.constraints == ()
        assert fp.notes == ""
        assert fp.source_path is None

    def test_validation_error_missing_name(self) -> None:
        """Missing required field 'name' raises ValidationError."""
        from maverick.flight.models import FlightPlan, Scope

        with pytest.raises(ValidationError):
            FlightPlan(  # type: ignore[call-arg]
                version="1.0",
                created=date(2026, 1, 1),
                tags=("test",),
                objective="Something",
                success_criteria=(),
                scope=Scope(in_scope=(), out_of_scope=(), boundaries=()),
            )

    def test_validation_error_empty_name(self) -> None:
        """Empty 'name' raises ValidationError."""
        from maverick.flight.models import FlightPlan, Scope

        with pytest.raises(ValidationError):
            FlightPlan(
                name="",
                version="1.0",
                created=date(2026, 1, 1),
                tags=(),
                objective="Something",
                success_criteria=(),
                scope=Scope(in_scope=(), out_of_scope=(), boundaries=()),
            )

    def test_validation_error_missing_version(self) -> None:
        """Missing 'version' raises ValidationError."""
        from maverick.flight.models import FlightPlan, Scope

        with pytest.raises(ValidationError):
            FlightPlan(  # type: ignore[call-arg]
                name="plan",
                created=date(2026, 1, 1),
                tags=(),
                objective="Something",
                success_criteria=(),
                scope=Scope(in_scope=(), out_of_scope=(), boundaries=()),
            )

    def test_validation_error_missing_objective(self) -> None:
        """Missing 'objective' raises ValidationError."""
        from maverick.flight.models import FlightPlan, Scope

        with pytest.raises(ValidationError):
            FlightPlan(  # type: ignore[call-arg]
                name="plan",
                version="1.0",
                created=date(2026, 1, 1),
                tags=(),
                success_criteria=(),
                scope=Scope(in_scope=(), out_of_scope=(), boundaries=()),
            )

    def test_to_dict_has_expected_keys(self) -> None:
        """to_dict() output contains all expected keys."""
        fp = self._make_flight_plan()
        d = fp.to_dict()
        assert "name" in d
        assert "version" in d
        assert "created" in d
        assert "tags" in d
        assert "objective" in d
        assert "success_criteria" in d
        assert "scope" in d
        assert "context" in d
        assert "constraints" in d
        assert "notes" in d

    def test_to_dict_date_is_iso_string(self) -> None:
        """to_dict() serializes date as ISO-format string."""
        fp = self._make_flight_plan()
        d = fp.to_dict()
        assert isinstance(d["created"], str)
        assert d["created"] == "2026-02-27"

    def test_to_dict_tuples_as_lists(self) -> None:
        """to_dict() converts tuple fields to lists."""
        fp = self._make_flight_plan()
        d = fp.to_dict()
        assert isinstance(d["tags"], list)
        assert isinstance(d["constraints"], list)
        assert isinstance(d["success_criteria"], list)

    def test_to_dict_nested_models_as_dicts(self) -> None:
        """to_dict() converts nested models to dicts."""
        fp = self._make_flight_plan()
        d = fp.to_dict()
        assert isinstance(d["scope"], dict)
        assert isinstance(d["success_criteria"][0], dict)

    def test_tags_is_tuple(self) -> None:
        """tags field is stored as a tuple."""
        fp = self._make_flight_plan()
        assert isinstance(fp.tags, tuple)

    def test_source_path_defaults_to_none(self) -> None:
        """source_path defaults to None."""
        fp = self._make_flight_plan()
        assert fp.source_path is None

    def test_depends_on_plans_default_empty(self) -> None:
        """depends_on_plans defaults to empty tuple."""
        fp = self._make_flight_plan()
        assert fp.depends_on_plans == ()

    def test_depends_on_plans_with_values(self) -> None:
        """depends_on_plans stores plan names as tuple."""
        from maverick.flight.models import FlightPlan, Scope, SuccessCriterion

        fp = FlightPlan(
            name="add-payments",
            version="1.0",
            created=date(2026, 3, 1),
            tags=(),
            depends_on_plans=("add-auth", "add-database"),
            objective="Add payment processing.",
            success_criteria=(SuccessCriterion(text="Payments work", checked=False),),
            scope=Scope(
                in_scope=("src/payments/",),
                out_of_scope=(),
                boundaries=(),
            ),
        )
        assert fp.depends_on_plans == ("add-auth", "add-database")

    def test_depends_on_plans_in_to_dict(self) -> None:
        """to_dict() includes depends_on_plans as a list."""
        fp = self._make_flight_plan()
        d = fp.to_dict()
        assert "depends_on_plans" in d
        assert isinstance(d["depends_on_plans"], list)


# ===========================================================================
# T012: WorkUnit model tests
# ===========================================================================


class TestAcceptanceCriterion:
    """Tests for AcceptanceCriterion model."""

    def test_without_trace_ref(self) -> None:
        """AcceptanceCriterion without trace_ref has trace_ref=None."""
        from maverick.flight.models import AcceptanceCriterion

        ac = AcceptanceCriterion(
            text="Users table has email, password_hash columns", trace_ref=None
        )
        assert ac.text == "Users table has email, password_hash columns"
        assert ac.trace_ref is None

    def test_with_trace_ref(self) -> None:
        """AcceptanceCriterion with SC-### trace_ref is stored correctly."""
        from maverick.flight.models import AcceptanceCriterion

        ac = AcceptanceCriterion(
            text="Database connection pool is configured", trace_ref="SC-001"
        )
        assert ac.trace_ref == "SC-001"

    def test_frozen_immutability(self) -> None:
        """AcceptanceCriterion is frozen."""
        from maverick.flight.models import AcceptanceCriterion

        ac = AcceptanceCriterion(text="item", trace_ref=None)
        with pytest.raises((TypeError, ValidationError)):
            ac.text = "changed"  # type: ignore[misc]

    def test_empty_text_raises(self) -> None:
        """Empty text raises ValidationError."""
        from maverick.flight.models import AcceptanceCriterion

        with pytest.raises(ValidationError):
            AcceptanceCriterion(text="", trace_ref=None)


class TestFileScope:
    """Tests for FileScope model."""

    def test_all_sections(self) -> None:
        """FileScope with all sections populated."""
        from maverick.flight.models import FileScope

        fs = FileScope(
            create=("src/db/connection.py", "src/db/models/user.py"),
            modify=("src/config.py",),
            protect=("src/main.py",),
        )
        assert "src/db/connection.py" in fs.create
        assert "src/config.py" in fs.modify
        assert "src/main.py" in fs.protect

    def test_empty_sections(self) -> None:
        """FileScope with all empty sections is valid."""
        from maverick.flight.models import FileScope

        fs = FileScope(create=(), modify=(), protect=())
        assert fs.create == ()

    def test_frozen_immutability(self) -> None:
        """FileScope is frozen."""
        from maverick.flight.models import FileScope

        fs = FileScope(create=("file.py",), modify=(), protect=())
        with pytest.raises((TypeError, ValidationError)):
            fs.create = ("other.py",)  # type: ignore[misc]

    def test_create_is_tuple(self) -> None:
        """create field is a tuple."""
        from maverick.flight.models import FileScope

        fs = FileScope(create=["a.py"], modify=[], protect=[])  # type: ignore[arg-type]
        assert isinstance(fs.create, tuple)


class TestWorkUnit:
    """Tests for WorkUnit model."""

    def _make_work_unit(self, **overrides: object) -> WorkUnit:
        """Build a valid WorkUnit from sample data."""
        from maverick.flight.models import AcceptanceCriterion, FileScope, WorkUnit

        defaults: dict[str, object] = {
            "id": "setup-database",
            "flight_plan": "setup-authentication",
            "sequence": 1,
            "parallel_group": None,
            "depends_on": (),
            "task": "Create the users table and database connection module.",
            "acceptance_criteria": (
                AcceptanceCriterion(
                    text="Database connection pool is configured", trace_ref="SC-001"
                ),
                AcceptanceCriterion(
                    text="Users table has email, password_hash, created_at columns",
                    trace_ref=None,
                ),
            ),
            "file_scope": FileScope(
                create=("src/db/connection.py", "src/db/models/user.py"),
                modify=("src/config.py",),
                protect=("src/main.py",),
            ),
            "instructions": "Use SQLAlchemy with async support.",
            "verification": ("make test-fast", "make lint", "make typecheck"),
            "provider_hints": None,
        }
        defaults.update(overrides)
        return WorkUnit(**defaults)  # type: ignore[arg-type]

    def test_construction_all_fields(self) -> None:
        """WorkUnit can be constructed with all fields."""
        from maverick.flight.models import WorkUnit

        wu = self._make_work_unit()
        assert isinstance(wu, WorkUnit)

    def test_required_fields_accessible(self) -> None:
        """All required fields are accessible."""
        wu = self._make_work_unit()
        assert wu.id == "setup-database"
        assert wu.flight_plan == "setup-authentication"
        assert wu.sequence == 1

    def test_frozen_immutability(self) -> None:
        """WorkUnit is frozen — mutation raises."""
        wu = self._make_work_unit()
        with pytest.raises((TypeError, ValidationError)):
            wu.sequence = 2  # type: ignore[misc]

    # --- ID validation ---

    def test_valid_kebab_case_id(self) -> None:
        """Simple kebab-case ID passes validation."""
        wu = self._make_work_unit(id="setup-database")
        assert wu.id == "setup-database"

    def test_valid_kebab_case_id_with_numbers(self) -> None:
        """Kebab-case ID with numbers passes."""
        wu = self._make_work_unit(id="step-1-create")
        assert wu.id == "step-1-create"

    def test_invalid_id_uppercase_raises(self) -> None:
        """PascalCase ID raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(id="SetupDatabase")

    def test_invalid_id_underscores_raises(self) -> None:
        """Underscore-separated ID raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(id="setup_database")

    def test_invalid_id_double_hyphens_raises(self) -> None:
        """Double-hyphen ID raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(id="setup--database")

    def test_invalid_id_leading_hyphen_raises(self) -> None:
        """Leading hyphen in ID raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(id="-setup-database")

    def test_invalid_id_trailing_hyphen_raises(self) -> None:
        """Trailing hyphen in ID raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(id="setup-database-")

    # --- sequence validation ---

    def test_sequence_1_is_valid(self) -> None:
        """sequence=1 is valid."""
        wu = self._make_work_unit(sequence=1)
        assert wu.sequence == 1

    def test_sequence_0_raises(self) -> None:
        """sequence=0 raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(sequence=0)

    def test_sequence_negative_raises(self) -> None:
        """Negative sequence raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(sequence=-1)

    # --- optional field defaults ---

    def test_depends_on_defaults_to_empty_tuple(self) -> None:
        """depends_on defaults to empty tuple."""
        from maverick.flight.models import AcceptanceCriterion, FileScope, WorkUnit

        wu = WorkUnit(
            id="simple-task",
            flight_plan="my-plan",
            sequence=1,
            task="Do it",
            acceptance_criteria=(AcceptanceCriterion(text="Done", trace_ref=None),),
            file_scope=FileScope(create=(), modify=(), protect=()),
            instructions="Just do it.",
            verification=("make test",),
        )
        assert wu.depends_on == ()

    def test_parallel_group_defaults_to_none(self) -> None:
        """parallel_group defaults to None."""
        from maverick.flight.models import AcceptanceCriterion, FileScope, WorkUnit

        wu = WorkUnit(
            id="simple-task",
            flight_plan="my-plan",
            sequence=1,
            task="Do it",
            acceptance_criteria=(AcceptanceCriterion(text="Done", trace_ref=None),),
            file_scope=FileScope(create=(), modify=(), protect=()),
            instructions="Just do it.",
            verification=("make test",),
        )
        assert wu.parallel_group is None

    def test_provider_hints_defaults_to_none(self) -> None:
        """provider_hints defaults to None."""
        wu = self._make_work_unit()
        assert wu.provider_hints is None

    def test_source_path_defaults_to_none(self) -> None:
        """source_path defaults to None."""
        wu = self._make_work_unit()
        assert wu.source_path is None

    # --- parallel_group with depends_on ---

    def test_work_unit_with_parallel_group(self) -> None:
        """WorkUnit with parallel_group and depends_on is valid."""
        wu = self._make_work_unit(
            id="add-login-endpoint",
            sequence=2,
            parallel_group="endpoints",
            depends_on=("setup-database",),
        )
        assert wu.parallel_group == "endpoints"
        assert "setup-database" in wu.depends_on

    # --- to_dict ---

    def test_to_dict_has_expected_keys(self) -> None:
        """to_dict() output has all expected keys."""
        wu = self._make_work_unit()
        d = wu.to_dict()
        assert "id" in d
        assert "flight_plan" in d
        assert "sequence" in d
        assert "parallel_group" in d
        assert "depends_on" in d
        assert "task" in d
        assert "acceptance_criteria" in d
        assert "file_scope" in d
        assert "instructions" in d
        assert "verification" in d
        assert "provider_hints" in d

    def test_to_dict_tuples_as_lists(self) -> None:
        """to_dict() converts tuple fields to lists."""
        wu = self._make_work_unit()
        d = wu.to_dict()
        assert isinstance(d["depends_on"], list)
        assert isinstance(d["verification"], list)
        assert isinstance(d["acceptance_criteria"], list)

    def test_to_dict_nested_models_as_dicts(self) -> None:
        """to_dict() converts nested models to dicts."""
        wu = self._make_work_unit()
        d = wu.to_dict()
        assert isinstance(d["file_scope"], dict)
        assert isinstance(d["acceptance_criteria"][0], dict)

    def test_flight_plan_empty_raises(self) -> None:
        """Empty flight_plan raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(flight_plan="")

    def test_depends_on_is_tuple(self) -> None:
        """depends_on is stored as a tuple."""
        wu = self._make_work_unit(depends_on=["a", "b"])
        assert isinstance(wu.depends_on, tuple)

    # --- depends_on kebab-case validation (SPEC-1) ---

    def test_depends_on_valid_kebab_case(self) -> None:
        """depends_on with valid kebab-case entries passes validation."""
        wu = self._make_work_unit(depends_on=("setup-database", "create-schema"))
        assert wu.depends_on == ("setup-database", "create-schema")

    def test_depends_on_uppercase_raises(self) -> None:
        """depends_on entry with uppercase raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(depends_on=("SetupDatabase",))

    def test_depends_on_underscores_raises(self) -> None:
        """depends_on entry with underscores raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(depends_on=("setup_database",))

    def test_depends_on_leading_hyphen_raises(self) -> None:
        """depends_on entry with leading hyphen raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(depends_on=("-setup",))

    def test_depends_on_empty_string_raises(self) -> None:
        """depends_on entry that is empty string raises ValidationError."""
        with pytest.raises(ValidationError):
            self._make_work_unit(depends_on=("",))

    def test_depends_on_mixed_valid_invalid_raises(self) -> None:
        """depends_on with one invalid entry among valid ones raises."""
        with pytest.raises(ValidationError):
            self._make_work_unit(depends_on=("valid-id", "Invalid_Id"))


# ===========================================================================
# SPEC-2: AcceptanceCriterion.trace_ref validation tests
# ===========================================================================


class TestAcceptanceCriterionTraceRef:
    """Tests for trace_ref SC-\\d+ format validation."""

    def test_valid_trace_ref_sc001(self) -> None:
        """SC-001 is a valid trace_ref."""
        from maverick.flight.models import AcceptanceCriterion

        ac = AcceptanceCriterion(text="criterion", trace_ref="SC-001")
        assert ac.trace_ref == "SC-001"

    def test_valid_trace_ref_sc99(self) -> None:
        """SC-99 is a valid trace_ref."""
        from maverick.flight.models import AcceptanceCriterion

        ac = AcceptanceCriterion(text="criterion", trace_ref="SC-99")
        assert ac.trace_ref == "SC-99"

    def test_none_trace_ref_is_valid(self) -> None:
        """None trace_ref is valid (optional field)."""
        from maverick.flight.models import AcceptanceCriterion

        ac = AcceptanceCriterion(text="criterion", trace_ref=None)
        assert ac.trace_ref is None

    def test_invalid_trace_ref_wrong_prefix(self) -> None:
        """trace_ref with wrong prefix raises ValidationError."""
        from maverick.flight.models import AcceptanceCriterion

        with pytest.raises(ValidationError):
            AcceptanceCriterion(text="criterion", trace_ref="XX-001")

    def test_invalid_trace_ref_no_digits(self) -> None:
        """trace_ref without digits raises ValidationError."""
        from maverick.flight.models import AcceptanceCriterion

        with pytest.raises(ValidationError):
            AcceptanceCriterion(text="criterion", trace_ref="SC-")

    def test_invalid_trace_ref_lowercase(self) -> None:
        """trace_ref with lowercase 'sc' raises ValidationError."""
        from maverick.flight.models import AcceptanceCriterion

        with pytest.raises(ValidationError):
            AcceptanceCriterion(text="criterion", trace_ref="sc-001")

    def test_invalid_trace_ref_no_hyphen(self) -> None:
        """trace_ref without hyphen raises ValidationError."""
        from maverick.flight.models import AcceptanceCriterion

        with pytest.raises(ValidationError):
            AcceptanceCriterion(text="criterion", trace_ref="SC001")

    def test_valid_trace_ref_with_suffix(self) -> None:
        """trace_ref with alphanumeric suffix is valid (e.g., SC-B1-default)."""
        from maverick.flight.models import AcceptanceCriterion

        ac = AcceptanceCriterion(text="criterion", trace_ref="SC-001-extra")
        assert ac.trace_ref == "SC-001-extra"

    def test_valid_trace_ref_comma_separated(self) -> None:
        """Comma-separated SC refs are valid (agent may reference multiple)."""
        from maverick.flight.models import AcceptanceCriterion

        ac = AcceptanceCriterion(text="criterion", trace_ref="SC-002, SC-003")
        assert ac.trace_ref == "SC-002, SC-003"

    def test_valid_trace_ref_comma_no_space(self) -> None:
        """Comma-separated SC refs without space are valid."""
        from maverick.flight.models import AcceptanceCriterion

        ac = AcceptanceCriterion(text="criterion", trace_ref="SC-001,SC-002")
        assert ac.trace_ref == "SC-001,SC-002"

    def test_range_notation_expanded(self) -> None:
        """'SC-1 through SC-3' is normalized to 'SC-1, SC-2, SC-3'."""
        from maverick.flight.models import AcceptanceCriterion

        ac = AcceptanceCriterion(text="criterion", trace_ref="SC-1 through SC-3")
        assert ac.trace_ref == "SC-1, SC-2, SC-3"

    def test_large_range_notation_expanded(self) -> None:
        """'SC-1 through SC-14' is normalized to comma-separated refs."""
        from maverick.flight.models import AcceptanceCriterion

        ac = AcceptanceCriterion(text="criterion", trace_ref="SC-1 through SC-14")
        assert ac.trace_ref == ", ".join(f"SC-{i}" for i in range(1, 15))


# ===========================================================================
# SPEC-3 & SPEC-4: CompletionStatus validation tests
# ===========================================================================


class TestCompletionStatusValidation:
    """Tests for CompletionStatus checked/total >= 0 and percentage range."""

    def test_negative_checked_raises(self) -> None:
        """Negative checked raises ValidationError."""
        from maverick.flight.models import CompletionStatus

        with pytest.raises(ValidationError):
            CompletionStatus(checked=-1, total=3, percentage=0.0)

    def test_negative_total_raises(self) -> None:
        """Negative total raises ValidationError."""
        from maverick.flight.models import CompletionStatus

        with pytest.raises(ValidationError):
            CompletionStatus(checked=0, total=-1, percentage=0.0)

    def test_zero_checked_and_total_valid(self) -> None:
        """Zero checked and total are valid."""
        from maverick.flight.models import CompletionStatus

        cs = CompletionStatus(checked=0, total=0, percentage=None)
        assert cs.checked == 0
        assert cs.total == 0

    def test_percentage_negative_raises(self) -> None:
        """Negative percentage raises ValidationError."""
        from maverick.flight.models import CompletionStatus

        with pytest.raises(ValidationError):
            CompletionStatus(checked=0, total=3, percentage=-1.0)

    def test_percentage_above_100_raises(self) -> None:
        """Percentage above 100.0 raises ValidationError."""
        from maverick.flight.models import CompletionStatus

        with pytest.raises(ValidationError):
            CompletionStatus(checked=3, total=3, percentage=100.1)

    def test_percentage_exactly_0_valid(self) -> None:
        """Percentage of exactly 0.0 is valid."""
        from maverick.flight.models import CompletionStatus

        cs = CompletionStatus(checked=0, total=3, percentage=0.0)
        assert cs.percentage == 0.0

    def test_percentage_exactly_100_valid(self) -> None:
        """Percentage of exactly 100.0 is valid."""
        from maverick.flight.models import CompletionStatus

        cs = CompletionStatus(checked=3, total=3, percentage=100.0)
        assert cs.percentage == 100.0

    def test_percentage_none_valid(self) -> None:
        """Percentage of None is valid."""
        from maverick.flight.models import CompletionStatus

        cs = CompletionStatus(checked=0, total=0, percentage=None)
        assert cs.percentage is None


# ===========================================================================
# SPEC-5: ExecutionBatch.units non-empty validation tests
# ===========================================================================


class TestExecutionBatchValidation:
    """Tests for ExecutionBatch.units non-empty validation."""

    def _make_work_unit(self) -> WorkUnit:
        """Build a minimal valid WorkUnit for batch testing."""
        from maverick.flight.models import AcceptanceCriterion, FileScope, WorkUnit

        return WorkUnit(
            id="test-unit",
            flight_plan="test-plan",
            sequence=1,
            task="Test task",
            acceptance_criteria=(AcceptanceCriterion(text="Done", trace_ref=None),),
            file_scope=FileScope(create=(), modify=(), protect=()),
            instructions="Do it.",
            verification=("make test",),
        )

    def test_empty_units_raises(self) -> None:
        """Empty units tuple raises ValidationError."""
        from maverick.flight.models import ExecutionBatch

        with pytest.raises(ValidationError):
            ExecutionBatch(units=())

    def test_single_unit_valid(self) -> None:
        """Single unit in batch is valid."""
        from maverick.flight.models import ExecutionBatch

        wu = self._make_work_unit()
        batch = ExecutionBatch(units=(wu,))
        assert len(batch.units) == 1

    def test_multiple_units_valid(self) -> None:
        """Multiple units in batch is valid."""
        from maverick.flight.models import ExecutionBatch

        wu = self._make_work_unit()
        batch = ExecutionBatch(units=(wu, wu))
        assert len(batch.units) == 2
