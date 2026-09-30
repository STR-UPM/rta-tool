"""The two task sets in the supplied script, with the original object API.

Run: python -m examples.original_cases
The builders accept either this project's rta module or the archived module so
that tests can compare the two implementations on the same input objects.
"""
import rta


def case_one(api=rta):
    po1, po2, po3 = (api.Protected_Object(name) for name in ("po1", "po2", "po3"))
    tasks = [
        api.Task("Relax Vol.", 5, "periodic", 500, 30, 200).access(po2, 7),
        api.Task("Detect Vol.", 4, "periodic", 300, 20, 300).access(po1, 5),
        api.Task("Riesgos", 3, "periodic", 300, 50, 300).access(po1, 7).access(po2, 10).access(po3, 10),
        api.Task("Incli. Cabeza", 2, "periodic", 600, 100, 500).access(po1, 10).access(po2, 10),
        api.Task("Det. Pul.", 1, "sporadic", 2000, 30, 2000).access(po3, 10),
        api.Task("IRQ", 1000, "periodic", 2000, 20, 20),
    ]
    return tasks, [po1, po2, po3]


def case_two(api=rta):
    po1, po2, po3 = (api.Protected_Object(name) for name in ("Lock 1", "Lock 2", "Lock 3"))
    tasks = [
        api.Task("Task 1", 2, "periodic", 120, 25, 120).access(po2, 10).access(po3, 8),
        api.Task("Task 2", 4, "periodic", 600, 20, 40).access(po1, 7).access(po2, 5),
        api.Task("Task 3", 5, "periodic", 80, 8, 30).access(po3, 4),
        api.Task("Task 4", 3, "periodic", 50, 15, 50).access(po1, 6),
        api.Task("IRQ", 11, "periodic", 120, 2, 120),
    ]
    return tasks, [po1, po2, po3]


def main():
    for builder in (case_one, case_two):
        tasks, objects = builder()
        solver = rta.RTA_solver(tasks, objects)
        solver.solve()
        solver.print()


if __name__ == "__main__":
    main()
