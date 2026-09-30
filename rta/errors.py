"""Expected failures; inconclusive analysis is not a deadline miss."""
from fractions import Fraction


class RTAError(Exception):
    """Base class for errors that can be presented without a traceback."""


class ModelError(RTAError, ValueError):
    """An invalid or inconsistent task model."""


class UnsupportedModelError(ModelError):
    """The requested analysis is not defined by the supported model."""


class ParseError(RTAError, ValueError):
    """Invalid TSF/JSON syntax, with source location when available."""


class OverloadError(RTAError):
    """Utilization exceeds one: do not run a divergent iteration."""

    def __init__(self, utilization: Fraction) -> None:
        self.utilization = utilization
        super().__init__(
            f"total processor utilization exceeds 100% ({utilization}); "
            "the task set is not schedulable"
        )


class AnalysisLimitError(RTAError):
    """A numerical search budget was exhausted; no WCRT is asserted."""

    def __init__(self, task: str, detail: str) -> None:
        self.task = task
        super().__init__(f"analysis inconclusive for task {task!r}: {detail}")
