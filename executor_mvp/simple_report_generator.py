"""简单的测试报告生成器，不依赖LLM"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from .models import RunResult


@dataclass
class ExecutionSummary:
    """执行摘要"""

    total_cases: int
    passed_cases: int
    failed_cases: int
    total_duration_seconds: float
    started_at: datetime
    finished_at: datetime


@dataclass
class CaseDetail:
    """单个测试用例的详情"""

    case_id: str
    case_name: str
    status: str
    duration_seconds: float
    passed_steps: int
    total_steps: int
    artifacts_dir: str
    first_failure_step: int | None = None
    first_failure_message: str | None = None


class SimpleReportGenerator:
    """生成简洁的测试报告"""

    @staticmethod
    def generate_execution_report(
        run_results: List[RunResult],
        output_dir: Path,
        batch_id: str,
        started_at: datetime,
        finished_at: datetime,
    ) -> None:
        """生成执行报告"""
        report_path = output_dir / "test_report.md"

        # 计算统计信息
        total_cases = len(run_results)
        passed_cases = sum(1 for r in run_results if r.status == "passed")
        failed_cases = total_cases - passed_cases
        total_duration = (finished_at - started_at).total_seconds()

        # 准备用例详情
        passed_details = []
        failed_details = []

        for result in run_results:
            duration = (result.finished_at - result.started_at).total_seconds()
            passed_steps = sum(1 for s in result.steps if s.status == "passed")
            total_steps = len(result.steps)

            # 提取case名称（从artifacts_dir路径中）
            case_name = Path(result.artifacts_dir).name

            detail = CaseDetail(
                case_id=case_name,  # 使用case名称，便于复制粘贴执行
                case_name=case_name,
                status=result.status,
                duration_seconds=duration,
                passed_steps=passed_steps,
                total_steps=total_steps,
                artifacts_dir=result.artifacts_dir,
            )

            # 查找第一个失败步骤
            if result.status == "failed":
                for step in result.steps:
                    if step.status == "failed":
                        detail.first_failure_step = step.index
                        detail.first_failure_message = step.error or "未知错误"
                        break
                failed_details.append(detail)
            else:
                passed_details.append(detail)

        # 生成报告
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"# 测试执行报告\n\n")
            f.write(f"**批次ID**: `{batch_id}`  \n")
            f.write(f"**执行时间**: {started_at.strftime('%Y-%m-%d %H:%M:%S')} - {finished_at.strftime('%Y-%m-%d %H:%M:%S')}  \n")
            f.write(f"**总时长**: {total_duration:.2f}秒  \n\n")

            # 总体统计
            f.write("## 📊 总体统计\n\n")
            f.write("| 指标 | 数值 |\n")
            f.write("|------|------|\n")
            f.write(f"| 总测试用例数 | {total_cases} |\n")
            f.write(f"| ✅ 通过 | {passed_cases} |\n")
            f.write(f"| ❌ 失败 | {failed_cases} |\n")
            f.write(f"| 成功率 | {passed_cases/total_cases*100:.1f}% |\n")
            f.write(f"| 总执行时长 | {total_duration:.2f}秒 |\n")
            f.write(f"| 平均每用例时长 | {total_duration/total_cases:.2f}秒 |\n\n")

            # 未通过的用例
            if failed_details:
                f.write("## ❌ 未通过的用例\n\n")
                f.write("| Case ID | 结果目录 | 执行时长 | 通过步骤 | 失败步骤 | 错误信息 |\n")
                f.write("|---------|----------|----------|----------|----------|----------|\n")
                for detail in failed_details:
                    f.write(f"| `{detail.case_id}` | `{detail.artifacts_dir}` | {detail.duration_seconds:.2f}秒 | "
                            f"{detail.passed_steps}/{detail.total_steps} | "
                            f"步骤{detail.first_failure_step or 'N/A'} | {detail.first_failure_message or 'N/A'} |\n")
                f.write("\n")

            # 通过的用例
            if passed_details:
                f.write("## ✅ 通过的用例\n\n")
                f.write("| Case ID | 执行时长 | 通过步骤 |\n")
                f.write("|---------|----------|----------|\n")
                for detail in passed_details:
                    f.write(f"| `{detail.case_id}` | {detail.duration_seconds:.2f}秒 | {detail.total_steps}/{detail.total_steps} |\n")
                f.write("\n")

            f.write("---\n\n")
            f.write(f"*报告生成时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}*\n")
