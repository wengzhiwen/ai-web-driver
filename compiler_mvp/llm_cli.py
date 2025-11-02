"""CLI entry for LLM-based compilation pipeline."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency

    def load_dotenv(*_args, **_kwargs):
        return False


from .data_driven_compiler import (CompilationErrorReporter,
                                   CompilationOutputWriter, DataDrivenCompiler,
                                   DataSetLoader)
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

    parser.add_argument(
        "--dataset",
        help="Path to dataset JSON file for data-driven compilation",
    )
    parser.add_argument(
        "--dataset-category",
        help="Category key in dataset to use for compilation",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM compilation, use existing template for data-driven replacement only",
    )
    parser.add_argument(
        "--output-stats",
        action="store_true",
        help="Output replacement statistics and detailed error log",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    parser = build_parser()
    args = parser.parse_args(argv)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"Compiler run at: {timestamp}")

    has_dataset = args.dataset and args.dataset_category

    if has_dataset:
        try:
            result = _compile_with_dataset(
                request_path=Path(args.request),
                profile_path=Path(args.profile),
                dataset_path=Path(args.dataset),
                dataset_category=args.dataset_category,
                output_root=Path(args.output_root),
                schema_path=Path(args.schema),
                plan_name=args.plan_name,
                case_name=args.case_name,
                max_attempts=args.attempts,
                temperature=args.temperature,
                api_timeout=args.api_timeout,
                skip_llm=args.skip_llm,
                output_stats=args.output_stats,
                summary=args.summary,
            )
            return result
        except Exception as exc:
            logging.error("数据驱动编译流程失败: %s", exc)
            return 1
    else:
        try:
            request = parse_markdown(Path(args.request))
            profile = load_site_profile(Path(args.profile))

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


def _compile_with_dataset(
    request_path: Path,
    profile_path: Path,
    dataset_path: Path,
    dataset_category: str,
    output_root: Path,
    schema_path: Path,
    plan_name: str | None,
    case_name: str | None,
    max_attempts: int,
    temperature: float,
    api_timeout: float | None,
    skip_llm: bool,
    output_stats: bool,
    summary: bool,
) -> int:
    """Execute data-driven compilation pipeline."""

    profile = load_site_profile(profile_path)

    if skip_llm:
        logging.info("使用已有的模板进行数据驱动替换")
        if not plan_name:
            raise ValueError("--skip-llm 模式下必须提供 --plan-name")
        template_path = output_root / plan_name / "action_plan_template.json"
        if not template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_path}")
        with open(template_path, encoding="utf-8") as f:
            template_plan = json.load(f)
    else:
        logging.info("执行 LLM 编译生成模板")
        request = parse_markdown(request_path)
        result = run_pipeline(
            request=request,
            profile=profile,
            plan_root=output_root,
            schema_path=schema_path,
            plan_name=plan_name,
            case_name=case_name,
            max_attempts=max_attempts,
            temperature=temperature,
            api_timeout=api_timeout,
        )
        template_plan_path = result.case_dir / "action_plan.json"
        with open(template_plan_path, encoding="utf-8") as f:
            template_plan = json.load(f)

    logging.info("加载数据集")
    raw_dataset = DataSetLoader.load_from_file(dataset_path)
    dataset = DataSetLoader.extract_category(raw_dataset, dataset_category)
    logging.info(f"已加载 {len(dataset.items)} 个数据项")

    logging.info("执行数据驱动编译")
    compiler = DataDrivenCompiler()
    result = compiler.compile(
        template_plan=template_plan,
        test_id_base=template_plan.get("meta", {}).get("testId", "TEST"),
        base_url=template_plan.get("meta", {}).get("baseUrl", ""),
        dataset=dataset,
    )

    logging.info("输出编译结果")
    plan_dir, case_dir = CompilationOutputWriter.write_results(
        result,
        output_root=output_root,
        plan_name=plan_name,
        case_name=case_name,
    )

    if result.stats.errors:
        CompilationErrorReporter.write_error_report(result.stats, plan_dir)

    if output_stats:
        CompilationErrorReporter.print_summary(result.stats)

    print("\n数据驱动编译完成!")
    print(f"  模板: {plan_dir}")
    print(f"  输出目录: {case_dir}")
    print(f"  生成的测试用例数: {len(result.cases)}")

    if summary:
        print("\n首个测试用例示例:")
        if result.cases:
            print(json.dumps(result.cases[0], ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
