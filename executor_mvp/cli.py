"""Command-line interface for the executor MVP."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(*_args, **_kwargs):
        return False


from .executor import Executor, ExecutorSettings
from .loader import load_plan_from_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an ActionPlan DSL using the executor MVP")
    parser.add_argument(
        "--plan-dir",
        required=True,
        help="Directory containing a cases subdirectory",
    )
    parser.add_argument(
        "--case",
        help="Case directory name under <plan-dir>/cases (optional if only one case exists)",
    )
    parser.add_argument(
        "--output",
        default="results",
        help="Directory where run artifacts will be stored (default: results)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (default is headless)",
    )
    parser.add_argument(
        "--screenshots",
        choices=["none", "on-failure", "all"],
        default="on-failure",
        help="Screenshot capture policy",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10_000,
        help="Default Playwright timeout in milliseconds",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print the run.json payload to stdout upon completion",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    settings = ExecutorSettings(
        headless=not args.headed,
        default_timeout_ms=args.timeout,
        output_root=Path(args.output),
        screenshots=args.screenshots,
    )

    executor = Executor(settings=settings)
    plan = load_plan_from_directory(args.plan_dir, case_name=args.case)

    result = executor.run(plan)

    print(f"Run {result.run_id} finished with status {result.status}")
    print(f"Artifacts: {result.artifacts_dir}")

    if args.summary:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
