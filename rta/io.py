"""Input selection and individually atomic file replacement."""
import os
from pathlib import Path
import stat
import tempfile

from .errors import ModelError
from .jsonio import dumps_json, load_json
from .model import TaskSet
from .tsf import dumps_tsf, load_tsf


def file_format(path: str | Path, requested: str = "auto") -> str:
    if requested not in {"auto", "tsf", "json"}:
        raise ModelError(f"unknown file format {requested!r}")
    return ("json" if Path(path).suffix.lower() == ".json" else "tsf") if requested == "auto" else requested


def load_task_set(path: str | Path, format: str = "auto") -> TaskSet:
    return load_json(path) if file_format(path, format) == "json" else load_tsf(path)


def serialize_task_set(task_set: TaskSet, format: str = "tsf", sort: bool = True) -> str:
    if format not in {"tsf", "json"}:
        raise ModelError(f"unknown serialization format {format!r}")
    return dumps_json(task_set, sort) if format == "json" else dumps_tsf(task_set, sort)


def same_path(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    try:
        return os.path.samefile(left, right)
    except (FileNotFoundError, OSError):
        return False


def atomic_write_many(outputs: list[tuple[Path, str]]) -> None:
    """Stage every output before replacing any target; input update is staged last.

    Each replacement is atomic, not a transaction across multiple files. A failure
    during replacement can leave some output files committed; callers must report it.
    Symlinks are resolved so an input update does not destroy the symlink itself.
    """
    pending: list[tuple[Path, Path]] = []
    try:
        for path, text in outputs:
            destination = path.resolve()
            fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
            tmp_path = Path(temporary)
            pending.append((tmp_path, destination))
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            if destination.exists():
                os.chmod(tmp_path, stat.S_IMODE(destination.stat().st_mode))
        for temporary, destination in pending:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in pending:
            temporary.unlink(missing_ok=True)


def save_task_set(task_set: TaskSet, path: str | Path, *, format: str = "auto", sort: bool = True) -> None:
    path = Path(path)
    atomic_write_many([(path, serialize_task_set(task_set, file_format(path, format), sort))])
