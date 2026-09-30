"""Run from the project root: python -m examples.legacy_api"""
from rta import ICPP, Protected_Object, RTA_solver, Task


def main() -> None:
    lock = Protected_Object("Lock 1")
    fast = Task("Fast task", 2, "periodic", 10, 2, 10).access(lock, "0.2")
    slow = Task("Slow task", 1, "sporadic", 25, 5, 25).access(lock, "0.8")
    solver = RTA_solver({fast, slow}, {lock}, sync_protocol=ICPP)
    solver.solve()
    solver.print()
    assert solver.system_is_schedulable


if __name__ == "__main__":
    main()
