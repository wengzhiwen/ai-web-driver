"""CLI entry for LLM-based compilation pipeline."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency

    def load_dotenv(*_args, **_kwargs):
        return False


from .llm_pipeline import run_pipeline
from .site_profile_loader import load_site_profile
from .test_request_parser import parse_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Use LLM to compile TestRequest into ActionPlan DSL")
    parser.add_argument("--request", required=True, help="Path to test request Markdown file")
    parser.add_argument("--profile", required=True, help="Path to site profile JSON file")
    parser.add_argument(
        "--schema",
        default="dsl/action_plan.schema.json",
        help="Path to the ActionPlan JSON Schema (default: dsl/action_plan.schema.json)",
    )
    parser.add_argument(
        "--output-root",
        default="action_plans",
        help="Root directory for generated plans (default: action_plans)",
    )
    parser.add_argument("--plan-name", help="Optional plan directory name")
    parser.add_argument("--case-name", help="Optional case directory name")
    parser.add_argument(
        "--attempts",
        type=int,
        default=3,
        help="Maximum number of correction attempts when validation fails (default: 3)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="LLM temperature (default: 0.2)",
    )
    parser.add_argument(
        "--api-timeout",
        type=float,
        help="HTTP timeout in seconds for LLM requests (default: env LLM_TIMEOUT or 60)",
    )
    parser.add_argument("--summary", action="store_true", help="Print the generated ActionPlan JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    parser = build_parser()
    args = parser.parse_args(argv)

    request = parse_markdown(Path(args.request))
    profile = load_site_profile(Path(args.profile))

    try:
        result = run_pipeline(
            request=request,
            profile=profile,
            plan_root=Path(args.output_root),
            schema_path=Path(args.schema),
            plan_name=args.plan_name,
            case_name=args.case_name,
            max_attempts=args.attempts,
            temperature=args.temperature,
            api_timeout=args.api_timeout,
        )
    except Exception as exc:
        logging.error("LLM 编译流程失败: %s", exc)
        return 1

    print(f"LLM plan generated for {result.test_id} at {result.case_dir}")

    if args.summary:
        payload_path = result.case_dir / "action_plan.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
