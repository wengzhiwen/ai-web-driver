"""Batch execution support for running multiple test cases."""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .executor import Executor, ExecutorSettings
from .loader import load_action_plan
from .models import ActionPlan, RunResult
from .simple_report_generator import SimpleReportGenerator

# pylint: disable=too-many-instance-attributes

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Result of batch execution."""

    batch_id: str
    total_cases: int
    passed_cases: int = 0
    failed_cases: int = 0
    error_cases: int = 0
    case_results: List[RunResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    artifacts_dir: Optional[str] = None


class BatchExecutor:
    """Executes multiple test cases in batch."""

    def __init__(self, settings: Optional[ExecutorSettings] = None):
        self.settings = settings or ExecutorSettings()
        self.logger = logging.getLogger("executor_mvp.batch")

    def discover_cases(self, plan_dir: Path) -> List[tuple[str, Path]]:
        """Discover all test cases in a plan directory.

        Args:
            plan_dir: Plan directory containing a 'cases' subdirectory.

        Returns:
            List of tuples (case_name, case_path).
            case_path can be a directory with action_plan.json or a JSON file directly.
        """
        cases_dir = plan_dir / "cases"
        if not cases_dir.is_dir():
            raise FileNotFoundError(f"Cases directory not found: {cases_dir}")

        case_items = []
        for item in cases_dir.iterdir():
            if item.is_dir():
                plan_file = item / "action_plan.json"
                if plan_file.exists():
                    case_items.append((item.name, item, plan_file))
            elif item.is_file() and item.suffix == '.json':
                case_name = item.stem
                case_items.append((case_name, item, item))

        return [(name, path) for name, path, _ in sorted(case_items)]

    def select_random_cases(self, case_items: List[tuple[str, Path]], count: int, seed: Optional[int] = None) -> List[tuple[str, Path]]:
        """Randomly select test cases.

        Args:
            case_items: List of all case (name, path) tuples.
            count: Number of cases to select.
            seed: Random seed for reproducibility.

        Returns:
            List of selected case (name, path) tuples.
        """
        if seed is not None:
            random.seed(seed)

        if count >= len(case_items):
            return case_items

        return random.sample(case_items, count)

    def run_batch(
        self,
        plan_dir: Path,
        case_count: Optional[int] = None,
        random_seed: Optional[int] = None,
    ) -> BatchResult:
        """Run multiple test cases in batch.

        Args:
            plan_dir: Plan directory containing test cases.
            case_count: Number of cases to run (None = all cases).
            random_seed: Random seed for case selection.

        Returns:
            BatchResult with execution summary and individual results.
        """
        batch_id = self._build_batch_id()
        batch_dir = self._prepare_batch_artifacts(batch_id)

        result = BatchResult(
            batch_id=batch_id,
            total_cases=0,
            artifacts_dir=str(batch_dir),
            started_at=datetime.utcnow(),
        )

        case_items = self.discover_cases(plan_dir)

        if case_count is not None and case_count > 0:
            case_items = self.select_random_cases(case_items, case_count, random_seed)
            self.logger.info("随机选择 %d 个测试用例", len(case_items))

        result.total_cases = len(case_items)

        self.logger.info("开始批量执行 %d 个测试用例", result.total_cases)

        for i, (case_name, case_path) in enumerate(case_items, 1):
            self.logger.info("[%d/%d] 运行: %s", i, result.total_cases, case_name)

            try:
                if case_path.is_file():
                    plan = load_action_plan(case_path)
                else:
                    plan = load_action_plan(case_path / "action_plan.json")

                case_result = self._run_single_case(plan, batch_dir, case_name)

                result.case_results.append(case_result)

                if case_result.status == "passed":
                    result.passed_cases += 1
                elif case_result.status == "failed":
                    result.failed_cases += 1
                else:
                    result.error_cases += 1

            except Exception as exc:
                self.logger.error("测试用例 %s 执行异常: %s", case_name, exc)
                result.error_cases += 1

        result.finished_at = datetime.utcnow()

        self._write_batch_summary(result, batch_dir)

        # 使用简单报告生成器
        report_gen = SimpleReportGenerator()
        report_gen.generate_execution_report(
            run_results=result.case_results,
            output_dir=batch_dir,
            batch_id=result.batch_id,
            started_at=result.started_at,
            finished_at=result.finished_at,
        )

        return result

    def _run_single_case(self, plan: ActionPlan, batch_dir: Path, case_name: str) -> RunResult:
        """Run a single test case within batch execution.

        Args:
            plan: The action plan to execute.
            batch_dir: Batch artifacts directory.
            case_name: Case name for organization.

        Returns:
            RunResult for this case.
        """
        temp_settings = ExecutorSettings(
            headless=self.settings.headless,
            default_timeout_ms=self.settings.default_timeout_ms,
            output_root=batch_dir.parent,
            screenshots=self.settings.screenshots,
            generate_report=False,
        )

        # 直接指定case子目录作为artifacts_dir
        case_output_dir = batch_dir / case_name

        case_executor = Executor(settings=temp_settings)
        result = case_executor.run(plan, artifacts_dir=case_output_dir)

        return result

    @staticmethod
    def _build_batch_id() -> str:
        """Build a unique batch ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}_batch_run"

    def _prepare_batch_artifacts(self, batch_id: str) -> Path:
        """Prepare batch artifacts directory."""
        batch_dir = self.settings.output_root / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        return batch_dir

    def _write_batch_summary(self, result: BatchResult, batch_dir: Path) -> None:
        """Write batch execution summary."""
        summary = {
            "batch_id":
            result.batch_id,
            "total_cases":
            result.total_cases,
            "passed_cases":
            result.passed_cases,
            "failed_cases":
            result.failed_cases,
            "error_cases":
            result.error_cases,
            "success_rate":
            result.passed_cases / result.total_cases * 100 if result.total_cases > 0 else 0,
            "started_at":
            result.started_at.isoformat() if result.started_at else None,
            "finished_at":
            result.finished_at.isoformat() if result.finished_at else None,
            "cases": [{
                "test_id": r.test_id,
                "status": r.status,
                "steps_passed": sum(1 for s in r.steps if s.status == "passed"),
                "steps_total": len(r.steps),
                "artifacts_dir": r.artifacts_dir,
            } for r in result.case_results],
        }

        summary_path = batch_dir / "batch_summary.json"
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        self.logger.info("批量执行摘要已保存: %s", summary_path)
