"""LLM-powered test report generator for human-readable test summaries."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from compiler_mvp.llm_client import LLMClient, LLMClientError
from .models import ActionPlan, RunResult


class TestReportGenerator:
    """Generates human-readable test reports using LLM analysis."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        """Initialize the report generator.

        Args:
            llm_client: Optional LLM client for generating reports. If None, creates a default client.
        """
        self.llm_client = llm_client or LLMClient()
        self.logger = logging.getLogger(__name__)

    def generate_report(
        self,
        plan: ActionPlan,
        result: RunResult,
        output_path: Optional[Path] = None
    ) -> str:
        """Generate a human-readable test report.

        Args:
            plan: The original ActionPlan that was executed
            result: The execution result from the executor
            output_path: Optional path to save the report

        Returns:
            The generated report as a string
        """
        try:
            # Prepare analysis context
            analysis_context = self._prepare_analysis_context(plan, result)

            # Generate report using LLM
            report = self._generate_llm_report(analysis_context)

            # Save report if path provided
            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(report, encoding="utf-8")
                self.logger.info("Test report saved to %s", output_path)

            return report

        except LLMClientError as exc:
            self.logger.warning("LLM report generation failed, falling back to template: %s", exc)
            return self._generate_fallback_report(plan, result)
        except Exception as exc:
            self.logger.error("Unexpected error generating report: %s", exc)
            return self._generate_fallback_report(plan, result)

    def _prepare_analysis_context(self, plan: ActionPlan, result: RunResult) -> Dict[str, object]:
        """Prepare context data for LLM analysis."""

        # Categorize steps by status
        passed_steps = [step for step in result.steps if step.status == "passed"]
        failed_steps = [step for step in result.steps if step.status == "failed"]

        # Extract key actions
        navigation_steps = []
        interaction_steps = []
        assertion_steps = []
        verification_points = []

        for i, step in enumerate(plan.steps):
            if step.t == "goto":
                navigation_steps.append(f"步骤{i+1}: 导航到 {step.url}")
            elif step.t in ["fill", "click"]:
                action_desc = f"步骤{i+1}: {self._describe_action(step)}"
                interaction_steps.append(action_desc)
            elif step.t == "assert":
                assertion_desc = f"步骤{i+1}: {self._describe_assertion(step)}"
                assertion_steps.append(assertion_desc)
                # Also collect verification points for detailed listing
                verification_point = self._describe_assertion(step)
                verification_points.append(verification_point)

        # Calculate execution metrics
        total_duration = (result.finished_at - result.started_at).total_seconds()
        passed_count = len(passed_steps)
        failed_count = len(failed_steps)
        success_rate = (passed_count / len(result.steps)) * 100 if result.steps else 0

        # Extract page flow information
        page_flow = self._extract_page_flow(result)

        # Identify test objectives
        test_objectives = self._infer_test_objectives(plan)

        return {
            "test_info": {
                "test_id": result.test_id,
                "run_id": result.run_id,
                "status": result.status,
                "success_rate": f"{success_rate:.1f}%",
                "total_duration": f"{total_duration:.2f}秒",
                "total_steps": len(result.steps),
                "passed_steps": passed_count,
                "failed_steps": failed_count,
                "base_url": plan.base_url or "未知",
                "executed_at": result.started_at.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "test_objectives": test_objectives,
            "page_flow": page_flow,
            "navigation_actions": navigation_steps,
            "interaction_actions": interaction_steps,
            "verification_points": assertion_steps,
            "detailed_verification_list": verification_points,
            "execution_summary": {
                "key_achievements": self._extract_key_achievements(plan, result),
                "failure_analysis": self._analyze_failures(failed_steps) if failed_steps else [],
                "performance_metrics": self._calculate_performance_metrics(result),
            },
            "detailed_steps": self._format_detailed_steps(plan, result),
        }

    def _describe_action(self, step) -> str:
        """Describe an action step in natural language."""
        if step.t == "fill":
            return f"在 {step.selector} 中输入 '{step.value}'"
        elif step.t == "click":
            return f"点击 {step.selector}"
        else:
            return f"执行 {step.t} 操作"

    def _describe_assertion(self, step) -> str:
        """Describe an assertion step in natural language."""
        if step.kind == "visible":
            return f"验证 {step.selector} 可见"
        elif step.kind == "text_contains":
            return f"验证 {step.selector} 包含文本 '{step.value}'"
        elif step.kind == "text_equals":
            return f"验证 {step.selector} 文本等于 '{step.value}'"
        elif step.kind == "count_equals":
            return f"验证 {step.selector} 数量等于 {step.value}"
        elif step.kind == "count_at_least":
            return f"验证 {step.selector} 数量至少 {step.value}"
        else:
            return f"验证 {step.selector} {step.kind}"

    def _extract_page_flow(self, result: RunResult) -> List[str]:
        """Extract page navigation flow from execution results."""
        page_flow = []
        current_url = None

        for step in result.steps:
            if step.current_url and step.current_url != current_url:
                current_url = step.current_url
                page_title = step.page_title or "未知页面"
                page_flow.append(f"{page_title} ({current_url})")

        return page_flow

    def _infer_test_objectives(self, plan: ActionPlan) -> List[str]:
        """Infer test objectives from the action plan."""
        objectives = []

        # Look for search functionality
        has_search = any(step.t == "fill" and "search" in step.selector.lower()
                        for step in plan.steps)
        if has_search:
            objectives.append("验证搜索功能")

        # Look for navigation
        has_navigation = any(step.t == "goto" for step in plan.steps)
        if has_navigation:
            objectives.append("验证页面导航")

        # Look for form interactions
        has_form = any(step.t == "fill" for step in plan.steps)
        if has_form:
            objectives.append("验证表单交互")

        # Extract specific verification points
        verification_points = []
        for step in plan.steps:
            if step.t == "assert":
                verification_point = self._describe_assertion(step)
                verification_points.append(verification_point)

        if verification_points:
            objectives.append(f"验证{len(verification_points)}个具体检查点")

        return objectives

    def _extract_key_achievements(self, plan: ActionPlan, result: RunResult) -> List[str]:
        """Extract key achievements from successful execution."""
        achievements = []

        if result.status == "passed":
            achievements.append("✅ 所有测试步骤执行成功")

            # Check specific achievements
            if any(step.t == "fill" for step in plan.steps):
                achievements.append("✅ 表单填写功能正常")

            if any(step.t == "click" for step in plan.steps):
                achievements.append("✅ 页面交互功能正常")

            assertion_count = sum(1 for step in plan.steps if step.t == "assert")
            if assertion_count > 0:
                achievements.append(f"✅ {assertion_count}个验证点全部通过")

        return achievements

    def _analyze_failures(self, failed_steps: List) -> List[str]:
        """Analyze failed steps and provide insights."""
        failure_analysis = []

        for step in failed_steps:
            if step.error:
                if "未能找到指定的DOM元素" in step.error:
                    failure_analysis.append(f"页面元素定位失败: {step.selector}")
                elif "timeout" in step.error.lower():
                    failure_analysis.append(f"操作超时: {step.t} {step.selector}")
                else:
                    failure_analysis.append(f"执行错误: {step.error}")

        return failure_analysis

    def _calculate_performance_metrics(self, result: RunResult) -> Dict[str, str]:
        """Calculate performance metrics from execution results."""
        total_duration = (result.finished_at - result.started_at).total_seconds()

        if result.steps:
            avg_step_time = total_duration / len(result.steps)
        else:
            avg_step_time = 0

        return {
            "总执行时间": f"{total_duration:.2f}秒",
            "平均每步时间": f"{avg_step_time:.2f}秒",
            "总步骤数": str(len(result.steps)),
        }

    def _format_detailed_steps(self, plan: ActionPlan, result: RunResult) -> List[Dict[str, object]]:
        """Format detailed step information for the report."""
        detailed_steps = []

        for i, (plan_step, result_step) in enumerate(zip(plan.steps, result.steps), start=1):
            step_info = {
                "step_number": i,
                "action_type": plan_step.t,
                "selector": plan_step.selector or "N/A",
                "status": result_step.status,
                "duration": f"{(result_step.finished_at - result_step.started_at).total_seconds():.3f}秒",
                "page_url": result_step.current_url or "N/A",
                "page_title": result_step.page_title or "N/A",
            }

            if result_step.status == "failed" and result_step.error:
                step_info["error"] = result_step.error

            if plan_step.t in ["fill", "assert"] and plan_step.value:
                step_info["value"] = plan_step.value

            detailed_steps.append(step_info)

        return detailed_steps

    def _generate_llm_report(self, analysis_context: Dict[str, object]) -> str:
        """Generate report using LLM analysis."""

        system_prompt = """你是一个专业的软件测试工程师，负责生成清晰、专业的测试执行报告。

请基于提供的测试执行数据，生成一份人类可读的简明测试报告。报告应该：

1. **结构清晰**：使用适当的标题和分段
2. **语言简洁**：用专业但易懂的语言描述测试结果
3. **重点突出**：突出测试的成功点和关键发现
4. **实用性强**：让读者能够快速了解测试是否成功完成
5. **详细验证**：必须列出所有具体的验证点，不要只给出计数

**重要要求**：
- 必须在报告中专门列出所有验证检查点，让读者清楚知道具体验证了什么
- 不要只说"验证了10个检查点"，而要列出这10个检查点具体是什么
- 用清晰的语言描述每个验证点的具体内容和验证结果

报告格式要求：
- 使用Markdown格式
- 包含适当的表情符号增强可读性
- 语气积极但客观
- 重点信息加粗显示
- 适当时使用列表展示信息
- 验证点部分使用编号列表详细列出

请生成一份让测试负责人能够安心确认测试完成质量的详细报告。"""

        user_prompt = f"""请基于以下测试执行数据生成简明测试报告：

## 测试基本信息
- 测试ID: {analysis_context['test_info']['test_id']}
- 运行ID: {analysis_context['test_info']['run_id']}
- 执行状态: {analysis_context['test_info']['status']}
- 成功率: {analysis_context['test_info']['success_rate']}
- 执行时间: {analysis_context['test_info']['total_duration']}
- 执行开始时间: {analysis_context['test_info']['executed_at']}

## 测试目标
{chr(10).join(f"- {obj}" for obj in analysis_context['test_objectives'])}

## 页面访问流程
{chr(10).join(f"{i+1}. {page}" for i, page in enumerate(analysis_context['page_flow']))}

## 关键操作
- 导航操作: {len(analysis_context['navigation_actions'])}个
- 交互操作: {len(analysis_context['interaction_actions'])}个
- 验证检查: {len(analysis_context['verification_points'])}个

## 具体验证点清单
{chr(10).join(f"- {point}" for point in analysis_context['detailed_verification_list'])}

## 执行摘要
- 主要成就: {chr(10).join(f"- {achievement}" for achievement in analysis_context['execution_summary']['key_achievements'])}
- 性能指标: {chr(10).join(f"- {k}: {v}" for k, v in analysis_context['execution_summary']['performance_metrics'].items())}

请生成一份专业、清晰的测试报告。"""

        try:
            response = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            return response.strip()
        except Exception as exc:
            self.logger.error("LLM request failed: %s", exc)
            raise LLMClientError(f"LLM request failed: {exc}")

    def _generate_fallback_report(self, plan: ActionPlan, result: RunResult) -> str:
        """Generate a fallback report without LLM assistance."""

        total_duration = (result.finished_at - result.started_at).total_seconds()
        passed_count = len([s for s in result.steps if s.status == "passed"])
        failed_count = len([s for s in result.steps if s.status == "failed"])

        report = f"""# 🧪 测试执行报告

## 📊 测试概览
- **测试ID**: {result.test_id}
- **运行状态**: {'✅ 通过' if result.status == 'passed' else '❌ 失败'}
- **执行时间**: {total_duration:.2f}秒
- **步骤统计**: {passed_count}通过 / {failed_count}失败

## 🎯 执行摘要
{'所有测试步骤成功执行完成。' if result.status == 'passed' else '测试执行过程中遇到失败步骤。'}

## 📈 性能指标
- 总执行时间: {total_duration:.2f}秒
- 平均每步时间: {total_duration/len(result.steps):.2f}秒

---
*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

        return report