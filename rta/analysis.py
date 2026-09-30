"""Guide sections 3.1--3.3: ceilings, blocking, and multi-job recurrence."""
from dataclasses import replace
from fractions import Fraction

from .errors import AnalysisLimitError, ModelError, OverloadError, UnsupportedModelError
from .model import (
    Activation, AnalysisOptions, AnalysisResult, Diagnostic, JobResult,
    TaskResult, TaskSet, TaskSpec,
)
from .numbers import ceil_fraction


def prepare(task_set: TaskSet, options: AnalysisOptions) -> tuple[TaskSet, tuple[Diagnostic, ...]]:
    """Validate scheduling assumptions and compute priorities/ceilings/blocking.

    Returns a new immutable model. The input is never mutated.
    """
    warnings: list[Diagnostic] = []
    #if options.protocol == "PIP" and options.compute_blocking:
    for task in task_set.tasks:
        if task.activation == Activation.UNDEFINED:
            raise UnsupportedModelError(f"{task.name}: 'undefined' parses but has no analysis semantics")
        if task.offset:
            warnings.append(Diagnostic("OFFSET_NOT_USED", f"{task.name}: offset {task.offset} is preserved but "
                                       "not used by the guide's phase-independent recurrence"))
    tasks = list(task_set.tasks)
    if options.assign_priorities:
        # Stable ties: earlier input task receives the higher unique priority.
        order = sorted(range(len(tasks)), key=lambda i: tasks[i].deadline)
        for rank, index in enumerate(order):
            tasks[index] = replace(tasks[index], priority=len(tasks) - rank)
    else:
        priorities = [task.priority for task in tasks]
        if any(p <= 0 for p in priorities) or len(set(priorities)) != len(priorities):
            raise ModelError("supplied task priorities must be positive and distinct")

    locks = []
    for lock in task_set.locks:
        users = [task for task in tasks if any(u.lock.casefold() == lock.name.casefold() for u in task.uses)]
        required = max((task.priority for task in users), default=0)
        if options.compute_ceilings:
            lock = replace(lock, ceiling=required)
        elif lock.ceiling < required:
            raise ModelError(f"{lock.name}: supplied ceiling {lock.ceiling} is below highest user priority {required}")
        if not users:
            warnings.append(Diagnostic("UNUSED_LOCK", f"{lock.name}: no task uses this lock"))
        locks.append(lock)
    ceilings = {lock.name.casefold(): lock.ceiling for lock in locks}
    if options.compute_blocking:
        for owner in tasks:
            for use in owner.uses:
                if use.duration is None:
                    raise ModelError(f"{owner.name}: critical-section duration missing for {use.lock}; "
                                     "supply uses Lock(duration), or supply blocking times with -b")
        for i, task in enumerate(tasks):
            # Eq. (3.1): ONLY critical sections executed by lower-priority tasks.
            blocking = 0
            if options.protocol == "PIP":
                # Resources used by this task or any higher-priority task.
                # Derive relevance from actual users, not configured ceilings.
                relevant_locks = {
                    use.lock.casefold()
                    for user in tasks
                    if user.priority >= task.priority
                    for use in user.uses
                }

                # Longest critical section per resource among lower-priority tasks.
                blocking_by_lock: dict[str, Fraction] = {}

                for owner in tasks:
                    if owner.priority >= task.priority:
                        continue

                    for use in owner.uses:
                        lock_name = use.lock.casefold()

                        if lock_name in relevant_locks:
                            blocking_by_lock[lock_name] = max(
                                blocking_by_lock.get(lock_name, Fraction(0)),
                                use.duration,
                            )

                # PIP: sum one maximum per relevant resource.
                blocking = sum(blocking_by_lock.values(), Fraction(0))

            else:
                blocking = max((
                    use.duration
                    for owner in tasks if owner.priority < task.priority
                    for use in owner.uses if ceilings[use.lock.casefold()] >= task.priority
                ), default=Fraction(0))
            tasks[i] = replace(task, blocking=blocking)
    elif tasks:
        warnings.append(Diagnostic("MANUAL_BLOCKING", "supplied blocking bounds are assumed valid; "
                                   "they have not been derived or proved by this tool"))
    return TaskSet(task_set.name, tuple(tasks), tuple(locks)), tuple(warnings)


def interference_at(time: Fraction, higher_priority: tuple[TaskSpec, ...]) -> Fraction:
    """Eq. (3.2); higher-priority jitter enters for all activation patterns."""
    return sum((ceil_fraction((time + t.jitter) / t.period) * t.wcet for t in higher_priority), Fraction(0))


def _analyze_task(task: TaskSpec, task_id: int, hp: tuple[TaskSpec, ...], options: AnalysisOptions) -> TaskResult:
    worst: JobResult | None = None
    trace: list[JobResult] = []
    total_iterations = 0
    own_jitter = task.jitter if task.activation == Activation.PERIODIC else Fraction(0)
    for q in range(options.max_jobs):
        base = (q + 1) * task.wcet + task.blocking             # Eq. (3.6)
        window = base
        steps = [window] if options.capture_trace else []
        for iteration in range(1, options.max_iterations + 1):
            new_window = base + interference_at(window, hp)  # Eq. (3.5)
            if options.capture_trace:
                steps.append(new_window)
            if new_window == window:
                break
            window = new_window
        else:
            raise AnalysisLimitError(task.name, f"fixed point did not converge within "
                                     f"{options.max_iterations} iterations at q={q}; increase --max-iterations")
        total_iterations += iteration
        response = window - q * task.period + own_jitter     # Eqs. (3.7), (3.8)
        current = JobResult(q, window, response, window - base, iteration, tuple(steps))
        if worst is None or current.response > worst.response:
            worst = current
        if options.capture_trace:
            trace.append(current)
        if response <= task.period:                         # Guide's stated stopping rule
            solved = replace(task, response=worst.response, interference=worst.interference)
            return TaskResult(solved, task_id, worst.response <= task.deadline,
                              worst.q, q + 1, total_iterations, tuple(trace))
    raise AnalysisLimitError(task.name, f"the guide's R(q) <= T stopping condition was not reached "
                             f"within {options.max_jobs} jobs; increase --max-jobs or review the model")


def analyze(task_set: TaskSet, options: AnalysisOptions | None = None) -> AnalysisResult:
    """Compute the guide's response bound, without early exit on a missed deadline.

    A budget exhaustion raises AnalysisLimitError, never a false 'unschedulable'
    verdict or a partial result labelled as a completed WCRT calculation.
    """
    options = options or AnalysisOptions()
    prepared, diagnostics = prepare(task_set, options)
    if prepared.utilization > 1:
        raise OverloadError(prepared.utilization)
    by_priority = sorted(enumerate(prepared.tasks), key=lambda pair: -pair[1].priority)
    hp: list[TaskSpec] = []
    results: dict[int, TaskResult] = {}
    for index, task in by_priority:
        results[index] = _analyze_task(task, index + 1, tuple(hp), options)
        hp.append(task)
    ordered = tuple(results[i] for i in range(len(prepared.tasks)))
    solved_set = TaskSet(prepared.name, tuple(t.task for t in ordered), prepared.locks)
    return AnalysisResult(solved_set, ordered, diagnostics, options)
