"""Response-time analysis with guide-compatible files and a Python API.

Use TaskSpec/TaskSet/analyze for new code. Task/Protected_Object/RTA_solver preserve
the principal construction API of the supplied original implementation.
"""
from .analysis import analyze, interference_at, prepare
from .errors import AnalysisLimitError, ModelError, OverloadError, ParseError, RTAError, UnsupportedModelError
from .io import load_task_set, save_task_set
from .jsonio import dumps_json, load_json, loads_json
from .model import Activation, AnalysisOptions, AnalysisResult, Diagnostic, JobResult, Lock, LockUse, TaskResult, TaskSet, TaskSpec
from .report import render_json, render_text, result_dict
from .tsf import dumps_tsf, load_tsf, loads_tsf

__version__ = "1.0.0"
__all__ = [
    "Activation", "AnalysisOptions", "AnalysisResult", "AnalysisLimitError", "Diagnostic",
    "JobResult", "Lock", "LockUse", "ModelError", "OverloadError", "ParseError",
    "RTAError", "TaskResult", "TaskSet", "TaskSpec",
    "UnsupportedModelError", "analyze", "dumps_json", "dumps_tsf", "interference_at",
    "load_json", "load_task_set", "load_tsf", "loads_json", "loads_tsf", "prepare",
    "render_json", "render_text", "result_dict", "save_task_set",
]
