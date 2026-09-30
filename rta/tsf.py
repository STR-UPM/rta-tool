"""TSF parser/serializer, including both conflicting layouts in guide section 2.3.

Eight fields: P,T,O,J,C,B,D,R (printed grammar).
Nine fields:  P,T,O,J,C,B,I,D,R (worked example and canonical saved format).
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .errors import ModelError, ParseError
from .model import Activation, Lock, LockUse, TaskSet, TaskSpec
from .numbers import tsf_string

_RESERVED = {"task", "set", "with", "tasks", "and", "locks", "is", "lock", "end", "uses", "periodic", "sporadic", "interrupt", "undefined"}


def valid_identifier(name: str) -> bool:
    return (bool(name) and name[0].isalpha()
            and all(c.isalnum() or c in "_.-" for c in name[1:])
            and "--" not in name and name.casefold() not in _RESERVED)


@dataclass(frozen=True)
class _Token:
    text: str
    kind: str
    line: int
    column: int


def _tokens(text: str, source: str) -> list[_Token]:
    tokens: list[_Token] = []
    index, line, column = 0, 1, 1
    while index < len(text):
        char = text[index]
        if char.isspace():
            if char == "\n":
                line, column = line + 1, 1
            else:
                column += 1
            index += 1
            continue
        if text.startswith("--", index):
            end = text.find("\n", index)
            if end < 0:
                break
            column += end - index
            index = end
            continue
        start, start_col = index, column
        if char in "(),;":
            kind = char
            index += 1
        elif char.isalpha():
            kind = "name"
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] in "_.-"):
                if text.startswith("--", index):
                    break
                index += 1
        elif char in "0123456789" or (char == "." and index + 1 < len(text) and text[index + 1] in "0123456789"):
            kind = "number"
            while index < len(text) and text[index] in "0123456789":
                index += 1
            if index < len(text) and text[index] == ".":
                index += 1
                while index < len(text) and text[index] in "0123456789":
                    index += 1
        else:
            raise ParseError(f"{source}:{line}:{column}: unexpected character {char!r}")
        tokens.append(_Token(text[start:index], kind, line, start_col))
        column += index - start
    tokens.append(_Token("<end of file>", "eof", line, column))
    return tokens


class _Parser:
    def __init__(self, text: str, source: str) -> None:
        self.tokens = _tokens(text.lstrip("\ufeff"), source)
        self.position = 0
        self.source = source

    @property
    def current(self) -> _Token:
        return self.tokens[self.position]

    def fail(self, message: str, token: Optional[_Token] = None) -> None:
        token = token or self.current
        raise ParseError(f"{self.source}:{token.line}:{token.column}: {message}")

    def accept(self, text: str) -> bool:
        if self.current.text.casefold() == text.casefold():
            self.position += 1
            return True
        return False

    def expect(self, text: str) -> None:
        if not self.accept(text):
            self.fail(f"expected {text!r}, found {self.current.text!r}")

    def name(self) -> str:
        token = self.current
        if token.kind != "name" or not valid_identifier(token.text):
            self.fail(f"expected a non-reserved name, found {token.text!r}")
        self.position += 1
        return token.text

    def number(self, integer: bool = False) -> str:
        token = self.current
        if token.kind != "number" or (integer and not token.text.isascii()) or (integer and not token.text.isdigit()):
            self.fail("expected an unsigned integer" if integer else "expected an unsigned decimal time")
        self.position += 1
        return token.text

    def lock(self) -> Lock:
        self.expect("lock")
        name = self.name()
        ceiling = 0
        if self.accept("("):
            ceiling = int(self.number(integer=True))
            self.expect(")")
        self.expect(";")
        return Lock(name, ceiling)

    def task(self) -> TaskSpec:
        self.expect("task")
        name = self.name()
        self.expect("is")
        token = self.current
        try:
            activation = Activation(token.text.casefold())
        except ValueError:
            self.fail("expected periodic, sporadic, interrupt, or undefined", token)
        self.position += 1
        self.expect("(")
        priority = int(self.number(integer=True))
        values = []
        while self.accept(","):
            values.append(self.number())
        self.expect(")")
        if len(values) not in {7, 8}:
            self.fail("task profile needs 8 fields (P,T,O,J,C,B,D,R) or "
                      "9 fields (P,T,O,J,C,B,I,D,R)", token)
        period, offset, jitter, wcet, blocking = values[:5]
        if len(values) == 7:
            interference, deadline, response = "0", values[5], values[6]
        else:
            interference, deadline, response = values[5:]
        uses = []
        if self.accept("uses"):
            while True:
                lock_name = self.name()
                duration = None
                if self.accept("("):
                    duration = self.number()
                    self.expect(")")
                uses.append(LockUse(lock_name, duration))
                if not self.accept(","):
                    break
        self.expect(";")
        try:
            return TaskSpec(name, period, wcet, deadline, activation, priority,
                            offset, jitter, blocking, interference, response, tuple(uses))
        except ModelError as exc:
            self.fail(str(exc), token)

    def parse(self) -> TaskSet:
        self.expect("task")
        self.expect("set")
        name = self.name()
        self.expect("with")
        task_count = int(self.number(integer=True))
        self.expect("tasks")
        lock_count = 0
        if self.accept("and"):
            lock_count = int(self.number(integer=True))
            self.expect("locks")
        self.expect("is")
        tasks, locks = [], []
        # Intermixed declarations are accepted as a documented convenience.
        while self.current.text.casefold() in {"lock", "task"}:
            if self.current.text.casefold() == "lock":
                locks.append(self.lock())
            else:
                tasks.append(self.task())
        self.expect("end")
        end_name = self.name()
        if end_name.casefold() != name.casefold():
            self.fail(f"end name {end_name!r} does not match task set {name!r}")
        self.expect(";")
        if self.current.kind != "eof":
            self.fail("unexpected content after end statement")
        if len(tasks) != task_count or len(locks) != lock_count:
            self.fail(f"declared {task_count} tasks and {lock_count} locks, "
                      f"found {len(tasks)} tasks and {len(locks)} locks")
        try:
            return TaskSet(name, tuple(tasks), tuple(locks))
        except ModelError as exc:
            self.fail(str(exc))


def loads_tsf(text: str, source: str = "<string>") -> TaskSet:
    return _Parser(text, source).parse()


def load_tsf(path: str | Path) -> TaskSet:
    path = Path(path)
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("iso-8859-1")
    return loads_tsf(text, str(path))


def dumps_tsf(task_set: TaskSet, sort: bool = True) -> str:
    for name in [task_set.name, *(t.name for t in task_set.tasks), *(l.name for l in task_set.locks)]:
        if not valid_identifier(name):
            raise ModelError(f"{name!r} is not a TSF identifier; use JSON for names containing spaces")
    tasks = sorted(task_set.tasks, key=lambda task: -task.priority) if sort else task_set.tasks
    locks = sorted(task_set.locks, key=lambda lock: -lock.ceiling) if sort else task_set.locks
    canonical_locks = {lock.name.casefold(): lock.name for lock in locks}
    lines = ["-- Saved by rta-guide4. Time units are user-defined and must be consistent.",
             "-- Task fields: priority, period, offset, jitter, wcet, blocking, interference, deadline, response.",
             f"task set {task_set.name} with {len(tasks)} tasks and {len(locks)} locks is"]
    for lock in locks:
        lines.append(f"  lock {lock.name} ({lock.ceiling});")
    for task in tasks:
        fields = [str(task.priority)] + [tsf_string(getattr(task, field)) for field in (
            "period", "offset", "jitter", "wcet", "blocking", "interference", "deadline", "response")]
        line = f"  task {task.name} is {task.activation.value} ({', '.join(fields)})"
        if task.uses:
            usages = [canonical_locks[use.lock.casefold()] +
                      (f" ({tsf_string(use.duration)})" if use.duration is not None else "") for use in task.uses]
            line += "\n    uses " + ", ".join(usages)
        lines.append(line + ";")
    lines.append(f"end {task_set.name};")
    return "\n".join(lines) + "\n"
