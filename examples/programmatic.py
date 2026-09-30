"""Run from the project root: python -m examples.programmatic"""
from rta import AnalysisOptions, Lock, LockUse, TaskSet, TaskSpec, analyze, render_text


def main() -> None:
    tasks = TaskSet("PythonExample", (
        TaskSpec("Fast", period="10", wcet="2", deadline="10", uses=(LockUse("Bus", "0.2"),)),
        TaskSpec("Slow", period="25", wcet="5", deadline="25", uses=(LockUse("Bus", "0.8"),)),
    ), (Lock("Bus"),))
    result = analyze(tasks, AnalysisOptions(capture_trace=True))
    print(render_text(result), end="")
    assert result.task("Fast").blocking == result.task_set.tasks[1].uses[0].duration


if __name__ == "__main__":
    main()
