from fractions import Fraction
from .model import TaskSpec

def compute_blocking_PIP(task : TaskSpec, tasks: list[TaskSpec]) -> Fraction:
    """_summary_

    Args:
        task  : Task for which to compute blocking
        tasks : List of all tasks in the system

    Returns:
        Fraction : Blocking time
    """
    
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
    return blocking

def compute_blocking_ICPP(task: TaskSpec, tasks: list[TaskSpec], ceilings: dict[str, int]) -> Fraction:
    blocking = max((
        use.duration
        for owner in tasks if owner.priority < task.priority
        for use in owner.uses if ceilings[use.lock.casefold()] >= task.priority
    ), default=Fraction(0))
    return blocking