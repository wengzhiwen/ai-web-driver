"""Command-line interface for the executor MVP."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(*_args, **_kwargs):
        return False


from .batch_executor import BatchExecutor
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
        "--batch",
        type=int,
        help="Run multiple test cases in batch (specify number of cases, or 0 for all)",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        help="Random seed for case selection in batch mode (for reproducibility)",
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

    # 批量执行模式
    if args.batch is not None:
        return _run_batch_mode(args, settings)

    # 单个用例执行模式（也使用统一的结果目录结构）
    from .simple_report_generator import SimpleReportGenerator

    executor = Executor(settings=settings)
    plan = load_plan_from_directory(args.plan_dir, case_name=args.case)

    # 创建统一的结果目录结构
    batch_id = datetime.now().strftime("%Y%m%dT%H%M%SZ") + "_run"
    batch_dir = settings.output_root / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    # 提取case名称
    case_name = Path(args.plan_dir) / "cases"
    if args.case:
        # 从文件名或目录名提取case名称
        case_name = args.case.replace('.json', '')
    else:
        # 从test_id提取
        case_name = f"case_{plan.test_id}"

    # 创建case子目录
    case_dir = batch_dir / case_name

    # 执行测试
    started_at = datetime.utcnow()
    result = executor.run(plan, artifacts_dir=case_dir)
    finished_at = datetime.utcnow()

    # 生成简单报告
    report_gen = SimpleReportGenerator()
    report_gen.generate_execution_report(
        run_results=[result],
        output_dir=batch_dir,
        batch_id=batch_id,
        started_at=started_at,
        finished_at=finished_at,
    )

    # 输出结果
    print("")
    print("=" * 80)
    print("执行完成")
    print("=" * 80)
    print(f"批次ID: {batch_id}")
    print(f"状态: {result.status}")
    print(f"通过步骤: {sum(1 for s in result.steps if s.status == 'passed')}/{len(result.steps)}")
    print(f"执行时长: {(finished_at - started_at).total_seconds():.2f}秒")
    print("")
    print(f"结果目录: {batch_dir}")
    print(f"  - test_report.md: 测试报告")
    print(f"  - {case_name}/: 测试用例结果")
    print("")

    if args.summary:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    return 0 if result.status == "passed" else 1


def _run_batch_mode(args, settings: ExecutorSettings) -> int:
    """Execute batch mode."""
    batch_executor = BatchExecutor(settings=settings)

    case_count = args.batch if args.batch > 0 else None

    print("=" * 80)
    print("批量执行模式")
    print("=" * 80)
    if case_count:
        print(f"随机选择: {case_count} 个测试用例")
    else:
        print("执行: 所有测试用例")
    if args.random_seed is not None:
        print(f"随机种子: {args.random_seed}")
    print("")

    try:
        result = batch_executor.run_batch(
            plan_dir=Path(args.plan_dir),
            case_count=case_count,
            random_seed=args.random_seed,
        )
    except Exception as exc:
        logging.error("批量执行失败: %s", exc)
        return 1

    print("\n" + "=" * 80)
    print("批量执行完成")
    print("=" * 80)
    print(f"批次 ID: {result.batch_id}")
    print(f"总测试数: {result.total_cases}")
    print(f"✓ 通过: {result.passed_cases}")
    print(f"✗ 失败: {result.failed_cases}")
    print(f"⚠ 错误: {result.error_cases}")

    if result.total_cases > 0:
        success_rate = result.passed_cases / result.total_cases * 100
        print(f"成功率: {success_rate:.1f}%")

    print(f"\n结果目录: {result.artifacts_dir}")
    print("  - test_report.md: 测试报告")
    print("  - batch_summary.json: 批量执行摘要")
    print("  - <case_name>/: 各测试用例结果")

    if args.summary:
        summary_path = Path(result.artifacts_dir) / "batch_summary.json"
        if summary_path.exists():
            summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
            print("\n" + json.dumps(summary_data, ensure_ascii=False, indent=2))

    return 0 if result.passed_cases == result.total_cases else 1


if __name__ == "__main__":
    sys.exit(main())
