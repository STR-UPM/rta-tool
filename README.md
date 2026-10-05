# Response Time Analysis Tool

A Python project based on the original tool **RTA (`guide-4.pdf`)** developed by Juan Antonio de la Puente.

The project implements the fixed-priority, preemptive **uniprocessor** scheduling analysis for real-time systems.
There are **no third-party runtime or test dependencies**.

## Quick start

Requires **Python 3.10 or later**. After extracting the project:

```bash
cd rta-python
python -m rta examples/guide_sample.tsf
python -m unittest discover -v
```

No installation is necessary when running from this directory. On systems where
Python 3 is named `python3`, substitute `python3` for `python`.

Optional installation creates the `rta` command:

```bash
python -m pip install .
rta examples/guide_sample.tsf
```

For an isolated installation, create and activate a virtual environment first.
The supplied wheel can also be installed directly with `python -m pip install`
without building the project; its filename is in the delivery's `dist` directory.

### Worked example from the guide

`examples/guide_sample.tsf` reproduces the input in Figure 2.2. The computed
values match Figure 2.1:

| Task | Priority | Blocking | Response | Schedulable |
| --- | ---: | ---: | ---: | --- |
| Task_3 | 3 | 2 | 10 | Yes |
| Task_2 | 2 | 0 | 14 | Yes |
| Task_1 | 1 | 0 | 47 | Yes |

The lock ceilings are 3 and 2. Processor utilization is `239/300`, displayed as
**79.67%**. Time units are not prescribed by the guide: use one unit consistently.

## Command line

The guide-style invocation is supported, including grouped flags:

```bash
python -m rta examples/guide_sample.tsf
python -m rta -vpcb examples/manual.tsf -s solved.tsf -o report.txt
python -m rta -n examples/guide_sample.tsf
python -m rta examples/arbitrary_deadlines.tsf --format json --trace
python -m rta -h
```

| Option | Meaning |
| --- | --- |
| `-p` | Keep supplied positive, distinct task priorities. |
| `-c` | Keep supplied resource ceilings; reject ceilings below their users' priorities. |
| `-b` | Keep externally justified blocking bounds instead of deriving them. |
| `-v` | Write progress to standard error; alone, print the version. |
| `-h` | Print help to standard error. |
| `-n` | Keep input order for tasks and resources in reports and saved files. |
| `-s FILE` | Save the analyzed task set, including computed fields. |
| `-o FILE` | Write the report to a file rather than standard output. |
| `-u` | Replace the input with the analyzed task set. |

Without `-p`, `-c`, and `-b`, the tool computes priorities, ceilings, and blocking.
Higher priority numbers mean higher scheduling priorities.

`-u` is an explicit overwrite: original comments and formatting are not retained.
Files are written through temporary files and individually atomic replacements.
Report paths cannot overwrite the input or collide with the save path. Staging
all outputs happens before replacement, but multiple replacements are **not a
single transaction**. Keep version-controlled input files or backups.

Additional options include `--format text|json`, `--input-format auto|tsf|json`,
`--save-format auto|tsf|json`, `--trace`, `--precision`, `--max-iterations`,
`--max-jobs`, and `--protocol`. Run `python -m rta -h` for all options.

**Exit codes:** 0 = completed and schedulable, or help/version; 1 = deadline miss
or utilization above 100%; 2 = invalid input, unsupported model, or file error;
3 = analysis inconclusive because a search limit was reached; 130 = interrupted.
No response table or output-file update is produced for overload, invalid input,
or inconclusive analysis. A completed analysis with missed deadlines does produce
a report and may be saved.

## Task-set files

The canonical saved layout follows the guide's worked example, including its
interference field:

```text
-- priority, period, offset, jitter, wcet, blocking, interference, deadline, response
 task set Demo with 2 tasks and 1 locks is
   lock Bus;
   task Fast is periodic (0, 10, 0, 0, 2, 0, 0, 10, 0)
     uses Bus (0.2);
   task Slow is sporadic (0, 25, 0, 0, 5, 0, 0, 25, 0)
     uses Bus (0.8);
 end Demo;
```

The eight-field layout printed in the guide's grammar is also accepted, with
interference initialized to zero. The duration after a lock use is the task's
longest critical section on that lock. This execution time must already be
included in the task WCET; the analyzer does not add it to WCET again.

Names and keywords are case-insensitive. `--` introduces a line comment. UTF-8
and ISO-8859-1 input are accepted. Saved files use UTF-8. Grammar-style bare uses,
such as `uses Bus`, require supplied blocking bounds (`-b`), because no
critical-section duration can be inferred from that input.

## Python API

Use immutable `TaskSpec`, `LockUse`, `Lock`, and `TaskSet` objects for new code:

```python
from rta import Lock, LockUse, TaskSet, TaskSpec, analyze, render_text

system = TaskSet(
    name="Demo",
    tasks=(
        TaskSpec("Fast", period="10", wcet="2", deadline="10",
                 uses=(LockUse("Bus", "0.2"),)),
        TaskSpec("Slow", period="25", wcet="5", deadline="25",
                 activation="sporadic", uses=(LockUse("Bus", "0.8"),)),
    ),
    locks=(Lock("Bus"),),
)

result = analyze(system)
print(render_text(result), end="")
assert result.schedulable
assert str(result.task("Fast").response) == "14/5"  # Exactly 2.8.
```

The input is not mutated. Use `AnalysisOptions(assign_priorities=False)` to keep
manual priorities, and `AnalysisOptions(capture_trace=True)` to retain the
fixed-point and per-release calculations. For files:

```python
from rta import analyze, load_task_set, save_task_set

result = analyze(load_task_set("examples/guide_sample.tsf"))
save_task_set(result.task_set, "solved.tsf")
save_task_set(result.task_set, "solved.json")
```

See [API and JSON](docs/API.md) for the models, result fields, exceptions, and
numeric conventions.

## Important analysis boundaries

**Offsets:** parsed, preserved, and displayed, but not exploited by the guide's
response-time recurrence. Nonzero offsets generate `OFFSET_NOT_USED`. This is
not an exact offset-aware scheduling analysis.

**Jitter:** follows the explicit recurrence in guide section 3.2. Higher-priority
jitter contributes to interference; a periodic task's own jitter is added to its
response, while a sporadic or interrupt task's own jitter is not added. Interrupt
tasks use the sporadic equation and the normal priority ordering. That convention
is documented explicitly; no additional interrupt-handler overhead is inferred.

**Locking:** automatic blocking uses the guide's PCP/IPCP/HLP maximum-section
formula. It also supports ICPP.

**Model scope:** no multiprocessor/distributed analysis, self-suspension model,
phase-aware offsets, EDF, mixed-criticality analysis, or automatic context-switch,
clock-handler, or interrupt-handler overhead modeling. `undefined` is accepted
by the file grammar but rejected for analysis. Deadline-monotonic priority
assignment is implemented, not claimed optimal for every arbitrary-deadline model.

**Convergence:** fixed-point and job limits prevent unlimited loops. Reaching a
limit means *inconclusive*, not a proved deadline miss. The guide's stopping rule
can fail to close for some inputs even at exactly 100% utilization; the project
does not invent a WCRT in that case. Bounds depend on the supplied WCETs, locking
assumptions, release model, and the guide's equations.

## Examples and tests

```bash
python -m examples.programmatic
python -m examples.legacy_api
python -m examples.original_cases
python -m rta -p examples/original_case_1.json
python -m rta -p examples/original_case_2.json
python -m unittest discover -v
```

The delivery was tested on Python 3.13.5/Linux. The **92 tests** include the guide's
worked example, both original ICPP examples, parsing/serialization, CLI and file
safety, blocking regressions, jitter, arbitrary deadlines, exact decimal boundary
cases, and convergence limits. Two tests additionally check **280 generated task
sets** against independent exhaustive-search and scheduling-simulation oracles.
The validation record is in `TEST_REPORT.txt`; scope and limitations are in
[Testing](docs/TESTING.md).

## Project structure

```text
rta/                         Importable package and CLI
  model.py                   Immutable models and result objects
  analysis.py                Priorities, ceilings, blocking, multi-release RTA
  numbers.py                 Exact arithmetic and display formatting
  tsf.py / jsonio.py          Task-set parsing and serialization
  report.py                  Text and JSON reports, optional traces
  io.py / cli.py             File handling and command line
examples/                    Guide, edge-case, and original-script examples
tests/                       Standard-library unittest suite
docs/                        Compatibility, algorithm, API, migration, testing
legacy/rta_original.py       Supplied script, unchanged
pyproject.toml               Installable package metadata
NOTICE.md                    Source provenance and licensing status
```
