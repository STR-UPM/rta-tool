"""Immutable, unit-independent input models and analysis results."""
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from typing import Optional

from .errors import ModelError
from .numbers import TimeLike, nonnegative_integer, time_value


class Activation(str, Enum):
    PERIODIC = "periodic"
    SPORADIC = "sporadic"
    INTERRUPT = "interrupt"
    UNDEFINED = "undefined"


def _name(value: str, field_name: str) -> str:
    # Python/JSON names may contain spaces, for compatibility with the original.
    # The TSF parser/serializer enforces its more restrictive identifier grammar.
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ModelError(f"{field_name} must be a nonempty name without control characters")
    return value


@dataclass(frozen=True)
class LockUse:
    lock: str
    duration: Optional[TimeLike] = None

    def __post_init__(self) -> None:
        _name(self.lock, "lock use")
        if self.duration is not None:
            object.__setattr__(self, "duration", time_value(self.duration, f"critical section on {self.lock}"))


@dataclass(frozen=True)
class Lock:
    name: str
    ceiling: int = 0

    def __post_init__(self) -> None:
        _name(self.name, "lock name")
        nonnegative_integer(self.ceiling, f"ceiling of {self.name}")


@dataclass(frozen=True)
class TaskSpec:
    name: str
    period: TimeLike
    wcet: TimeLike
    deadline: TimeLike
    activation: Activation = Activation.PERIODIC
    priority: int = 0
    offset: TimeLike = 0
    jitter: TimeLike = 0
    blocking: TimeLike = 0
    interference: TimeLike = 0
    response: TimeLike = 0
    uses: tuple[LockUse, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _name(self.name, "task name")
        nonnegative_integer(self.priority, f"priority of {self.name}")
        try:
            activation = self.activation if isinstance(self.activation, Activation) else Activation(str(self.activation).casefold())
        except ValueError as exc:
            raise ModelError(f"unknown activation pattern {self.activation!r}") from exc
        object.__setattr__(self, "activation", activation)
        for name in ("period", "wcet", "deadline", "offset", "jitter", "blocking", "interference", "response"):
            object.__setattr__(self, name, time_value(getattr(self, name), f"{self.name}.{name}"))
        object.__setattr__(self, "uses", tuple(self.uses))
        if self.period <= 0:
            raise ModelError(f"{self.name}: period/minimum separation must be positive")
        if self.wcet > self.period:
            raise ModelError(f"{self.name}: WCET cannot exceed period (guide section 2.2)")
        for use in self.uses:
            if not isinstance(use, LockUse):
                raise ModelError(f"{self.name}: uses must contain LockUse objects")
            if use.duration is not None and use.duration > self.wcet:
                raise ModelError(f"{self.name}: critical section on {use.lock} exceeds task WCET")


@dataclass(frozen=True)
class TaskSet:
    name: str
    tasks: tuple[TaskSpec, ...]
    locks: tuple[Lock, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _name(self.name, "task-set name")
        object.__setattr__(self, "tasks", tuple(self.tasks))
        object.__setattr__(self, "locks", tuple(self.locks))
        for objects, kind, expected in ((self.tasks, "task", TaskSpec), (self.locks, "lock", Lock)):
            seen: set[str] = set()
            for item in objects:
                if not isinstance(item, expected):
                    raise ModelError(f"{kind} collection contains an invalid object")
                key = item.name.casefold()
                if key in seen:
                    raise ModelError(f"duplicate {kind} name {item.name!r} (names are case-insensitive)")
                seen.add(key)
        known_locks = {lock.name.casefold() for lock in self.locks}
        for task in self.tasks:
            seen_uses: set[str] = set()
            for use in task.uses:
                key = use.lock.casefold()
                if key not in known_locks:
                    raise ModelError(f"{task.name}: undeclared lock {use.lock!r}")
                if key in seen_uses:
                    raise ModelError(f"{task.name}: duplicate use of lock {use.lock!r}; supply the longest section once")
                seen_uses.add(key)

    @property
    def utilization(self) -> Fraction:
        return sum((t.wcet / t.period for t in self.tasks), Fraction(0))


@dataclass(frozen=True)
class AnalysisOptions:
    assign_priorities: bool = True
    compute_ceilings: bool = True
    compute_blocking: bool = True
    protocol: str = "ICPP"
    max_iterations: int = 100_000
    max_jobs: int = 10_000
    capture_trace: bool = False

    def __post_init__(self) -> None:
        for flag in ("assign_priorities", "compute_ceilings", "compute_blocking", "capture_trace"):
            if not isinstance(getattr(self, flag), bool):
                raise ModelError(f"{flag} must be boolean")
        for limit in ("max_iterations", "max_jobs"):
            if nonnegative_integer(getattr(self, limit), limit) == 0:
                raise ModelError(f"{limit} must be positive")
        if not isinstance(self.protocol, str):
            raise ModelError("protocol must be a string")
        object.__setattr__(self, "protocol", self.protocol.upper())
        if self.protocol not in {"PCP", "ICPP", "IPCP", "HLP", "PIP"}:
            raise ModelError(f"unknown locking protocol {self.protocol!r}")


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class JobResult:
    q: int
    completion: Fraction
    response: Fraction
    interference: Fraction
    iterations: int
    fixed_point_steps: tuple[Fraction, ...] = ()


@dataclass(frozen=True)
class TaskResult:
    task: TaskSpec
    task_id: int
    schedulable: bool
    worst_job: int
    jobs_analyzed: int
    iterations: int
    jobs: tuple[JobResult, ...] = ()

    @property
    def response(self) -> Fraction:
        return self.task.response

    @property
    def blocking(self) -> Fraction:
        return self.task.blocking

    @property
    def interference(self) -> Fraction:
        return self.task.interference


@dataclass(frozen=True)
class AnalysisResult:
    task_set: TaskSet
    tasks: tuple[TaskResult, ...]
    diagnostics: tuple[Diagnostic, ...]
    options: AnalysisOptions

    @property
    def utilization(self) -> Fraction:
        return self.task_set.utilization

    @property
    def schedulable(self) -> bool:
        return all(task.schedulable for task in self.tasks)

    def ordered_tasks(self, sort: bool = True) -> tuple[TaskResult, ...]:
        return tuple(sorted(self.tasks, key=lambda item: -item.task.priority)) if sort else self.tasks

    def task(self, name: str) -> TaskResult:
        for result in self.tasks:
            if result.task.name.casefold() == name.casefold():
                return result
        raise KeyError(name)
