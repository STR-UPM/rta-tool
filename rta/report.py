"""Terminal and machine-readable reports; display rounding never affects analysis."""
import json

from .jsonio import task_set_dict
from .model import AnalysisResult
from .numbers import display_number, exact_string


def _table(headers: list[str], rows: list[list[str]], left: set[int]) -> str:
    widths = [max(len(header), max((len(row[i]) for row in rows), default=0)) for i, header in enumerate(headers)]

    def line(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[i]) if i in left else value.rjust(widths[i]) for i, value in enumerate(row))

    return "\n".join([line(headers), line(["-" * width for width in widths]), *(line(row) for row in rows)])


def render_text(result: AnalysisResult, sort: bool = True, precision: int = 3) -> str:
    rows = []
    for display_id, item in enumerate(result.ordered_tasks(sort), start=1):
        task = item.task
        rows.append([str(display_id), task.name, task.activation.value[0].upper(), str(task.priority),
                     *(display_number(getattr(task, key), precision) for key in (
                         "period", "offset", "jitter", "wcet", "blocking", "deadline", "response")),
                     "Yes" if item.schedulable else "No"])
    text = [f"Response time analysis for task set {result.task_set.name}", "",
            _table(["Id", "Task", "A", "PR", "Period", "Offset", "Jitter", "WCET", "Block", "Deadline", "Response", "Sch"], rows, {1, 2}),
            "", "Priority ceilings for shared resources", ""]
    indexed_locks = list(enumerate(result.task_set.locks, start=1))
    if sort:
        indexed_locks.sort(key=lambda pair: -pair[1].ceiling)
    text.append(_table(["Id", "Name", "PR"], [[str(i), l.name, str(l.ceiling)] for i, (_, l) in enumerate(indexed_locks, start=1)], {1}) if indexed_locks else "(none)")
    text.extend(["", f"Total processor utilization = {display_number(result.utilization * 100, 2)}%",
                 f"Task set schedulable = {'Yes' if result.schedulable else 'No'}"])
    if result.options.capture_trace:
        text.extend(["", "Analysis trace (q starts at zero)"])
        for item in result.ordered_tasks(sort):
            text.append(f"{item.task.name}: worst q={item.worst_job}")
            for job in item.jobs:
                text.append(f"  q={job.q}: w={exact_string(job.completion)}, R={exact_string(job.response)}, "
                            f"I={exact_string(job.interference)}, updates={job.iterations}")
                text.append("    " + " -> ".join(exact_string(v) for v in job.fixed_point_steps))
    return "\n".join(text) + "\n"


def result_dict(result: AnalysisResult, sort: bool = True) -> dict:
    rows = []
    for item in result.ordered_tasks(sort):
        row = {"source_id": item.task_id, "name": item.task.name, "priority": item.task.priority,
               "blocking": exact_string(item.blocking), "interference": exact_string(item.interference),
               "response": exact_string(item.response), "schedulable": item.schedulable,
               "worst_job": item.worst_job, "jobs_analyzed": item.jobs_analyzed, "iterations": item.iterations}
        if result.options.capture_trace:
            row["jobs"] = [
                {"q": job.q, "completion": exact_string(job.completion), "response": exact_string(job.response),
                 "interference": exact_string(job.interference), "iterations": job.iterations,
                 "fixed_point_steps": [exact_string(value) for value in job.fixed_point_steps]}
                for job in item.jobs
            ]
        rows.append(row)
    return {"report_version": 1, "tool": "rta-guide4", "status": "completed", "schedulable": result.schedulable,
            "utilization_fraction": str(result.utilization),
            "utilization_percent": display_number(result.utilization * 100, 6),
            "options": vars(result.options), "task_set": task_set_dict(result.task_set, sort), "results": rows,
            "warnings": [{"code": d.code, "message": d.message} for d in result.diagnostics]}


def render_json(result: AnalysisResult, sort: bool = True) -> str:
    return json.dumps(result_dict(result, sort), indent=2, ensure_ascii=False) + "\n"
