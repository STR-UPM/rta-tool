"""Compatible guide flags plus optional JSON reports and bounded tracing."""
import argparse
from pathlib import Path
import sys
from typing import Sequence

from .analysis import analyze
from .errors import AnalysisLimitError, ModelError, OverloadError, RTAError
from .io import atomic_write_many, file_format, load_task_set, same_path, serialize_task_set
from .model import AnalysisOptions
from .report import render_json, render_text

VERSION = "1.0.0"


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_help(sys.stderr)
        self.exit(2, f"\nError: {message}\n")


def make_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="rta", add_help=False, allow_abbrev=False,
        description="Response-time analysis for a fixed-priority, preemptive uniprocessor task set.",
        epilog=("Guide flags may be grouped: rta -vpcb input.tsf -s solved.tsf -o report.txt. "
                "Exit codes: 0 schedulable/help, 1 deadline miss/overload, 2 invalid input or I/O, "
                "3 inconclusive analysis, 130 interrupted."),
    )
    parser.add_argument("input_file", nargs="?", help="TSF task set (or JSON with the .json extension)")
    parser.add_argument("-h", "--help", action="store_true", help="print help to standard error")
    parser.add_argument("--version", action="store_true", help="print version to standard error")
    parser.add_argument("-v", "--verbose", action="store_true", help="progress messages; alone, print version")
    parser.add_argument("-p", "--manual-priorities", action="store_true", help="use supplied distinct task priorities")
    parser.add_argument("-c", "--manual-ceilings", action="store_true", help="use supplied lock ceilings")
    parser.add_argument("-b", "--manual-blocking", action="store_true", help="use supplied blocking bounds")
    parser.add_argument("-u", "--update", action="store_true", help="replace input with analyzed task set (comments reformatted)")
    parser.add_argument("-n", "--no-sort", action="store_true", help="retain input order in reports and saved task sets")
    parser.add_argument("-s", "--save", metavar="FILE", help="save analyzed task set; .json selects JSON, otherwise TSF")
    parser.add_argument("-o", "--output", metavar="FILE", help="write report to FILE rather than standard output")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="report format (default: text)")
    parser.add_argument("--input-format", choices=("auto", "tsf", "json"), default="auto")
    parser.add_argument("--save-format", choices=("auto", "tsf", "json"), default="auto")
    parser.add_argument("--protocol", type=str.upper, choices=("PCP", "ICPP", "IPCP", "HLP", "PIP"), default="ICPP",
                        help="PIP requires -b and externally justified bounds; others use guide Eq. (3.1)")
    parser.add_argument("--max-iterations", type=int, default=100_000, help="fixed-point updates per job (default: 100000)")
    parser.add_argument("--max-jobs", type=int, default=10_000, help="jobs examined per task (default: 10000)")
    parser.add_argument("--trace", action="store_true", help="include per-job and fixed-point traces in the report")
    parser.add_argument("--precision", type=int, choices=range(19), default=3, metavar="0..18",
                        help="decimal places in text report; analysis remains exact")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = make_parser()
    args = parser.parse_args(raw)
    if args.help:
        parser.print_help(sys.stderr)
        return 0
    if args.version or raw in (["-v"], ["--verbose"]):
        print(f"rta-guide4 {VERSION}", file=sys.stderr)
        return 0
    if args.input_file is None:
        parser.error("an input file is required")

    def progress(message: str) -> None:
        if args.verbose:
            print(f"Info: {message}", file=sys.stderr)

    try:
        input_path = Path(args.input_file)
        save_path = Path(args.save) if args.save else None
        output_path = Path(args.output) if args.output else None
        if save_path is not None and same_path(input_path, save_path):
            raise ModelError("-s cannot overwrite the input file; use -u explicitly")
        if output_path is not None and same_path(input_path, output_path):
            raise ModelError("the report output cannot overwrite the input task set")
        if save_path is not None and output_path is not None and same_path(save_path, output_path):
            raise ModelError("save file and report output must be different files")
        options = AnalysisOptions(not args.manual_priorities, not args.manual_ceilings, not args.manual_blocking,
                                  args.protocol, args.max_iterations, args.max_jobs, args.trace)
        progress(f"reading {input_path}")
        task_set = load_task_set(input_path, args.input_format)
        progress("assigning priorities, resolving ceilings and blocking, and computing response times")
        result = analyze(task_set, options)
        for diagnostic in result.diagnostics:
            print(f"Warning [{diagnostic.code}]: {diagnostic.message}", file=sys.stderr)
        report = render_json(result, not args.no_sort) if args.format == "json" else render_text(result, not args.no_sort, args.precision)
        outputs = []
        if save_path is not None:
            outputs.append((save_path, serialize_task_set(result.task_set, file_format(save_path, args.save_format), not args.no_sort)))
        if output_path is not None:
            outputs.append((output_path, report))
        if args.update:
            outputs.append((input_path, serialize_task_set(result.task_set, file_format(input_path, args.input_format), not args.no_sort)))
        if outputs:
            progress("writing output files (input updates are committed last)")
            atomic_write_many(outputs)
        if output_path is None:
            sys.stdout.write(report)
        progress("analysis complete")
        return 0 if result.schedulable else 1
    except OverloadError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except AnalysisLimitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 3
    except (RTAError, OSError, UnicodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Error: analysis interrupted", file=sys.stderr)
        return 130
