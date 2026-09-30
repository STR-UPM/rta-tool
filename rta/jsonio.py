"""Dependency-free JSON task sets, an extension to the guide's TSF format."""
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from .errors import ModelError, ParseError
from .model import Lock, LockUse, TaskSet, TaskSpec
from .numbers import exact_string


def _object(value: Any, allowed: set[str], required: set[str], location: str) -> dict:
    if not isinstance(value, dict):
        raise ParseError(f"{location}: expected an object")
    missing, extra = required - value.keys(), value.keys() - allowed
    if missing or extra:
        raise ParseError(f"{location}: missing keys {sorted(missing)}, unknown keys {sorted(extra)}")
    return value


def _list(value: Any, location: str) -> list:
    if not isinstance(value, list):
        raise ParseError(f"{location}: expected a list")
    return value


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ParseError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ParseError(f"non-finite JSON number {value!r} is not allowed")


def loads_json(text: str, source: str = "<string>") -> TaskSet:
    try:
        value = json.loads(text, parse_float=Decimal, parse_constant=_invalid_constant, object_pairs_hook=_unique_pairs)
        obj = _object(value, {"format_version", "name", "tasks", "locks"}, {"name", "tasks"}, "task set")
        if type(obj.get("format_version", 1)) is not int or obj.get("format_version", 1) != 1:
            raise ParseError("unsupported JSON format_version; expected integer 1")
        locks = []
        for index, value in enumerate(_list(obj.get("locks", []), "locks")):
            lock = _object(value, {"name", "ceiling"}, {"name"}, f"locks[{index}]")
            locks.append(Lock(**lock))
        tasks = []
        fields = {"name", "period", "wcet", "deadline", "activation", "priority", "offset", "jitter",
                  "blocking", "interference", "response", "uses"}
        for index, value in enumerate(_list(obj["tasks"], "tasks")):
            task = dict(_object(value, fields, {"name", "period", "wcet", "deadline", "activation"}, f"tasks[{index}]"))
            uses = []
            for use in _list(task.pop("uses", []), f"tasks[{index}].uses"):
                use = _object(use, {"lock", "duration"}, {"lock"}, f"tasks[{index}].uses")
                uses.append(LockUse(**use))
            tasks.append(TaskSpec(**task, uses=tuple(uses)))
        return TaskSet(obj["name"], tuple(tasks), tuple(locks))
    except (json.JSONDecodeError, ModelError, ParseError) as exc:
        raise ParseError(f"{source}: {exc}") from exc


def load_json(path: str | Path) -> TaskSet:
    path = Path(path)
    return loads_json(path.read_text(encoding="utf-8-sig"), str(path))


def task_set_dict(task_set: TaskSet, sort: bool = True) -> dict:
    tasks = sorted(task_set.tasks, key=lambda t: -t.priority) if sort else task_set.tasks
    locks = sorted(task_set.locks, key=lambda l: -l.ceiling) if sort else task_set.locks
    result = {"format_version": 1, "name": task_set.name, "locks": [], "tasks": []}
    for lock in locks:
        result["locks"].append({"name": lock.name, "ceiling": lock.ceiling})
    for task in tasks:
        row = {"name": task.name, "activation": task.activation.value, "priority": task.priority}
        row.update({key: exact_string(getattr(task, key)) for key in (
            "period", "offset", "jitter", "wcet", "blocking", "interference", "deadline", "response")})
        row["uses"] = [{"lock": use.lock, "duration": exact_string(use.duration) if use.duration is not None else None}
                       for use in task.uses]
        result["tasks"].append(row)
    return result


def dumps_json(task_set: TaskSet, sort: bool = True) -> str:
    return json.dumps(task_set_dict(task_set, sort), indent=2, ensure_ascii=False) + "\n"
