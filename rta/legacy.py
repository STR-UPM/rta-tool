"""Migration adapter for the public API of the supplied rta.py.

The original file remains unchanged in legacy/rta_original.py. This adapter routes
analysis through the guide-based engine, not the original single-job algorithm.
"""
from fractions import Fraction
from typing import Iterable

from .analysis import analyze, interference_at, prepare
from .errors import ModelError
from .model import AnalysisOptions, AnalysisResult, Lock, LockUse, TaskSet, TaskSpec
from .numbers import TimeLike, time_value
from .report import render_text

PIP = "PIP"
ICPP = "ICPP"


class Task:
    def __init__(self, name: str, priority: int, task_type: str, period_ms: TimeLike,
                 wcet_ms: TimeLike, deadline_ms: TimeLike, *, offset_ms: TimeLike = 0,
                 jitter_ms: TimeLike = 0, blocking_ms: TimeLike = 0) -> None:
        self.name, self.priority, self.type = name, priority, task_type
        self.period_ms = time_value(period_ms, "period_ms")
        self.wcet_ms = time_value(wcet_ms, "wcet_ms")
        self.deadline_ms = time_value(deadline_ms, "deadline_ms")
        self.offset_ms = time_value(offset_ms, "offset_ms")
        self.jitter_ms = time_value(jitter_ms, "jitter_ms")
        self.pr_objs: dict[Protected_Object, Fraction] = {}
        self.rta_blocking_time_ms = time_value(blocking_ms, "blocking_ms")
        self.rta_response_time_ms = Fraction(0)
        self.rta_interference_time_ms = Fraction(0)
        self.rta_schedulable = False

    def access(self, po: "Protected_Object", time_ms: TimeLike) -> "Task":
        duration = time_value(time_ms, "critical-section duration")
        # Guide: duration of the LONGEST section, not the most recent declaration.
        self.pr_objs[po] = max(duration, self.pr_objs.get(po, Fraction(0)))
        po.accessed_by(self)
        return self

    def access_time(self, to: "Protected_Object") -> Fraction:
        return self.pr_objs[to]

    def as_row(self) -> list:
        return [self.name, self.type, self.priority, self.period_ms, self.wcet_ms,
                self.rta_blocking_time_ms, self.deadline_ms, self.rta_response_time_ms,
                "Yes" if self.rta_schedulable else "No"]


class Protected_Object:
    def __init__(self, name: str) -> None:
        self.name = name
        self.tasks: set[Task] = set()
        self.ceiling = 0

    def accessed_by(self, task: Task) -> None:
        self.tasks.add(task)

    def wcet(self) -> Fraction:
        return max((task.access_time(to=self) for task in self.tasks), default=Fraction(0))


class RTA_solver:
    def __init__(self, tasks: Iterable[Task], pr_objs: Iterable[Protected_Object], sync_protocol: str = ICPP,
                 *, use_supplied_blocking: bool = False, max_iterations: int = 100_000,
                 max_jobs: int = 10_000) -> None:
        self.tasks = sorted(tasks, key=lambda task: (-task.priority, task.name.casefold()))
        self.pr_objs = sorted(pr_objs, key=lambda po: po.name.casefold())
        self.system_is_schedulable = False
        self.sync_protocol = sync_protocol
        self.use_supplied_blocking = use_supplied_blocking
        self.max_iterations, self.max_jobs = max_iterations, max_jobs
        self.result: AnalysisResult | None = None

    def _options(self) -> AnalysisOptions:
        return AnalysisOptions(assign_priorities=False, compute_blocking=not self.use_supplied_blocking,
                               protocol=self.sync_protocol, max_iterations=self.max_iterations, max_jobs=self.max_jobs)

    def _task_set(self) -> TaskSet:
        known = set(self.pr_objs)
        for task in self.tasks:
            if not set(task.pr_objs).issubset(known):
                raise ModelError(f"{task.name}: a protected object was not supplied to the solver")
        return TaskSet("Legacy", tuple(TaskSpec(
            name=t.name, period=t.period_ms, wcet=t.wcet_ms, deadline=t.deadline_ms,
            activation=t.type, priority=t.priority, offset=t.offset_ms, jitter=t.jitter_ms,
            blocking=t.rta_blocking_time_ms,
            uses=tuple(LockUse(po.name, duration) for po, duration in t.pr_objs.items())
        ) for t in self.tasks), tuple(Lock(po.name) for po in self.pr_objs))

    def solve(self) -> AnalysisResult:
        self.result = None
        self.system_is_schedulable = False
        for task in self.tasks:
            task.rta_response_time_ms = Fraction(0)
            task.rta_interference_time_ms = Fraction(0)
            task.rta_schedulable = False
        result = analyze(self._task_set(), self._options())
        self.tasks.sort(key=lambda task: -task.priority)
        for task in self.tasks:
            item = result.task(task.name)
            task.rta_blocking_time_ms = item.blocking
            task.rta_response_time_ms = item.response
            task.rta_interference_time_ms = item.interference
            task.rta_schedulable = item.schedulable
        ceilings = {lock.name.casefold(): lock.ceiling for lock in result.task_set.locks}
        for po in self.pr_objs:
            po.ceiling = ceilings[po.name.casefold()]
        self.result = result
        self.system_is_schedulable = result.schedulable
        return result

    def print(self) -> None:
        if self.result is None:
            raise ModelError("call solve() successfully before print()")
        print(render_text(self.result), end="")
        for diagnostic in self.result.diagnostics:
            print(f"Warning [{diagnostic.code}]: {diagnostic.message}")

    def usage(self, po: Protected_Object, task: Task) -> bool:
        owners = [owner for owner in self.tasks if po in owner.pr_objs]
        return any(owner.priority >= task.priority for owner in owners) and any(owner.priority < task.priority for owner in owners)

    def calculate_blocking_time(self, task: Task) -> None:
        if task not in self.tasks:
            raise ModelError("task is not in this solver")
        task_set, _ = prepare(self._task_set(), self._options())
        task.rta_blocking_time_ms = next(t.blocking for t in task_set.tasks if t.name.casefold() == task.name.casefold())

    def higher_priority_interference(self, task: Task) -> Fraction:
        higher = tuple(t for t in self._task_set().tasks if t.priority > task.priority)
        return interference_at(time_value(task.rta_response_time_ms), higher)

    def calculate_response_time(self, task: Task) -> None:
        if task not in self.tasks:
            raise ModelError("task is not in this solver")
        # Recompute consistently; do not reuse stale response-time state.
        self.solve()
