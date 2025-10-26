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
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Disable LLM-powered test report generation",
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
        generate_report=not args.no_report,
    )

    executor = Executor(settings=settings)
    plan = load_plan_from_directory(args.plan_dir, case_name=args.case)

    result = executor.run(plan)

    print(f"Run {result.run_id} finished with status {result.status}")
    print(f"Artifacts: {result.artifacts_dir}")

    # Display report summary if available
    report_path = Path(result.artifacts_dir) / "test_report.md"
    if report_path.exists():
        print(f"📊 Test report generated: {report_path}")
        # Display a brief summary
        try:
            report_content = report_path.read_text(encoding="utf-8")
            lines = report_content.split('\n')
            # Find and display the first few lines of the report
            summary_lines = []
            for line in lines[:10]:  # Show first 10 lines
                if line.strip():
                    summary_lines.append(line)
                if summary_lines and line.startswith('##'):
                    break  # Stop at next major section
            if summary_lines:
                print("\n📋 Report Summary:")
                for line in summary_lines:
                    print(f"  {line}")
        except Exception as exc:
            print(f"⚠️  Could not read report: {exc}")

    if args.summary:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
