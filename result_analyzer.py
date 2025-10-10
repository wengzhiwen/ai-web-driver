"""
LLM结果分析器 - 使用LLM智能分析测试结果，判断测试通过/失败
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from browser_use.llm import ChatOpenAI
from test_types import TestExecution, TestResult, TestCase, TestStep, Assertion

class LLMResultAnalyzer:
    """LLM结果分析器"""

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    async def analyze_execution_result(self, execution: TestExecution) -> TestResult:
        """分析测试执行结果"""
        # 基础结果已由执行引擎计算，这里使用LLM进行智能验证和调整
        base_result = execution.result

        # 如果已经有明确的结果（错误），直接返回
        if base_result == TestResult.ERROR:
            return base_result

        # 使用LLM进行智能分析
        try:
            analyzed_result = await self._intelligent_analysis(execution)
            return analyzed_result
        except Exception as e:
            print(f"LLM结果分析失败，使用基础结果: {e}")
            return base_result

    async def _intelligent_analysis(self, execution: TestExecution) -> TestResult:
        """智能分析测试结果"""
        test_case = execution.test_case

        # 构建分析上下文
        context = self._build_analysis_context(execution)

        # 生成分析提示
        prompt = f"""
请分析以下测试执行结果，判断测试是否真正通过。

测试用例信息：
- 标题: {test_case.title}
- 描述: {test_case.description}
- 测试类型: {test_case.test_type.value}

执行上下文：
{context}

请分析以下方面：
1. 测试步骤是否真正完成
2. 期望结果是否达成
3. 是否存在潜在的UI或功能问题
4. 断言结果是否合理

请返回JSON格式的分析结果：
{{
  "result": "passed|failed|error",
  "confidence": 0.0-1.0,
  "reasoning": "详细分析原因",
  "issues": ["发现的问题列表"],
  "suggestions": ["改进建议"]
}}

只返回JSON，不要包含其他内容。
"""

        try:
            response = await self.llm.ainvoke(prompt)
            if hasattr(response, 'content'):
                result_text = response.content.strip()
            elif isinstance(response, str):
                result_text = response.strip()
            else:
                result_text = str(response).strip()

            # 清理markdown标记
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]

            analysis = json.loads(result_text)

            # 记录分析结果
            self._record_analysis(execution, analysis)

            # 根据分析结果调整测试结果
            result_str = analysis.get('result', 'failed').lower()
            if result_str == 'passed':
                return TestResult.PASSED
            elif result_str == 'error':
                return TestResult.ERROR
            else:
                return TestResult.FAILED

        except Exception as e:
            print(f"智能分析过程中出错: {e}")
            return execution.result

    def _build_analysis_context(self, execution: TestExecution) -> str:
        """构建分析上下文"""
        test_case = execution.test_case
        context_parts = []

        # 添加步骤执行情况
        context_parts.append("测试步骤执行情况：")
        for i, step in enumerate(test_case.steps):
            step_status = "✅" if step.result == TestResult.PASSED else "❌"
            context_parts.append(f"{i+1}. {step.description} {step_status}")
            if step.error_message:
                context_parts.append(f"   错误: {step.error_message}")

        # 添加断言结果
        context_parts.append("\n断言验证情况：")
        for step in test_case.steps:
            for assertion in step.assertions:
                assert_status = "✅" if assertion.passed else "❌"
                context_parts.append(f"- {assertion.type.value}: {assertion.target} {assert_status}")
                if assertion.error_message:
                    context_parts.append(f"  错误: {assertion.error_message}")

        # 添加执行统计
        total_steps = len(test_case.steps)
        passed_steps = sum(1 for step in test_case.steps if step.result == TestResult.PASSED)
        total_assertions = sum(len(step.assertions) for step in test_case.steps)
        passed_assertions = sum(
            1 for step in test_case.steps
            for assertion in step.assertions
            if assertion.passed
        )

        context_parts.append(f"\n执行统计：")
        context_parts.append(f"- 步骤通过率: {passed_steps}/{total_steps} ({passed_steps/total_steps*100:.1f}%)" if total_steps > 0 else "- 步骤通过率: 0/0 (0%)")
        context_parts.append(f"- 断言通过率: {passed_assertions}/{total_assertions} ({passed_assertions/total_assertions*100:.1f}%)" if total_assertions > 0 else "- 断言通过率: 0/0 (0%)")
        context_parts.append(f"- 执行时间: {execution.total_execution_time:.2f}秒")

        # 添加浏览器日志（如果有）
        if execution.browser_logs:
            context_parts.append("\n浏览器日志：")
            for log in execution.browser_logs[-5:]:  # 只显示最后5条
                context_parts.append(f"- {log}")

        return "\n".join(context_parts)

    def _record_analysis(self, execution: TestExecution, analysis: Dict[str, Any]):
        """记录分析结果"""
        if not execution.error_details:
            execution.error_details = {}

        execution.error_details.update({
            "llm_analysis": analysis,
            "analysis_timestamp": datetime.now().isoformat()
        })

    async def analyze_test_suite_results(self, executions: List[TestExecution]) -> Dict[str, Any]:
        """分析整个测试套件的结果"""
        total_tests = len(executions)
        passed_tests = sum(1 for e in executions if e.result == TestResult.PASSED)
        failed_tests = sum(1 for e in executions if e.result == TestResult.FAILED)
        error_tests = sum(1 for e in executions if e.result == TestResult.ERROR)
        skipped_tests = sum(1 for e in executions if e.result == TestResult.SKIPPED)

        # 按测试类型分析
        type_analysis = {}
        for execution in executions:
            test_type = execution.test_case.test_type.value
            if test_type not in type_analysis:
                type_analysis[test_type] = {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "error": 0
                }

            type_analysis[test_type]["total"] += 1
            if execution.result == TestResult.PASSED:
                type_analysis[test_type]["passed"] += 1
            elif execution.result == TestResult.FAILED:
                type_analysis[test_type]["failed"] += 1
            elif execution.result == TestResult.ERROR:
                type_analysis[test_type]["error"] += 1

        # 分析失败原因
        failure_analysis = await self._analyze_failure_patterns(executions)

        # 生成改进建议
        suggestions = await self._generate_improvement_suggestions(executions)

        return {
            "summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "error": error_tests,
                "skipped": skipped_tests,
                "pass_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0
            },
            "by_type": type_analysis,
            "failure_analysis": failure_analysis,
            "suggestions": suggestions,
            "execution_time": {
                "total": sum(e.total_execution_time or 0 for e in executions),
                "average": sum(e.total_execution_time or 0 for e in executions) / total_tests if total_tests > 0 else 0
            }
        }

    async def _analyze_failure_patterns(self, executions: List[TestExecution]) -> Dict[str, Any]:
        """分析失败模式"""
        failed_executions = [e for e in executions if e.result in [TestResult.FAILED, TestResult.ERROR]]

        if not failed_executions:
            return {"message": "没有失败的测试用例"}

        # 收集失败原因
        failure_reasons = []
        for execution in failed_executions:
            for step in execution.test_case.steps:
                if step.result in [TestResult.FAILED, TestResult.ERROR]:
                    if step.error_message:
                        failure_reasons.append(step.error_message)

            # 检查断言失败
            for step in execution.test_case.steps:
                for assertion in step.assertions:
                    if not assertion.passed:
                        failure_reasons.append(f"断言失败: {assertion.type.value} - {assertion.target}")

        # 使用LLM分析失败模式
        if failure_reasons:
            prompt = f"""
请分析以下测试失败原因，识别主要的失败模式和问题类型：

失败原因列表：
{chr(10).join(f"- {reason}" for reason in failure_reasons[:10])}

请返回JSON格式的分析：
{{
  "common_patterns": ["常见的失败模式"],
  "root_causes": ["根本原因分析"],
  "categories": {{
    "ui_issues": ["UI相关问题"],
    "navigation_issues": ["导航相关问题"],
    "assertion_issues": ["断言相关问题"],
    "technical_issues": ["技术问题"],
    "other_issues": ["其他问题"]
  }}
}}

只返回JSON，不要包含其他内容。
"""

            try:
                response = await self.llm.ainvoke(prompt)
                result_text = response.content.strip()

                if result_text.startswith('```json'):
                    result_text = result_text[7:]
                if result_text.endswith('```'):
                    result_text = result_text[:-3]

                return json.loads(result_text)
            except Exception as e:
                print(f"分析失败模式时出错: {e}")

        return {"patterns": failure_reasons}

    async def _generate_improvement_suggestions(self, executions: List[TestExecution]) -> List[str]:
        """生成改进建议"""
        suggestions = []

        # 基础统计分析
        failed_count = sum(1 for e in executions if e.result == TestResult.FAILED)
        error_count = sum(1 for e in executions if e.result == TestResult.ERROR)

        if error_count > 0:
            suggestions.append("检查测试环境配置和浏览器兼容性")

        if failed_count > len(executions) * 0.5:
            suggestions.append("测试失败率较高，建议检查测试用例设计和期望结果")

        # 使用LLM生成针对性建议
        prompt = f"""
基于以下测试执行结果，请提供具体的改进建议：

- 总测试数: {len(executions)}
- 失败数: {failed_count}
- 错误数: {error_count}
- 平均执行时间: {sum(e.total_execution_time or 0 for e in executions) / len(executions):.2f}秒

请返回JSON格式的建议列表：
{{
  "suggestions": [
    "具体的改进建议1",
    "具体的改进建议2",
    "具体的改进建议3"
  ]
}}

只返回JSON，不要包含其他内容。
"""

        try:
            response = await self.llm.ainvoke(prompt)
            if hasattr(response, 'content'):
                result_text = response.content.strip()
            elif isinstance(response, str):
                result_text = response.strip()
            else:
                result_text = str(response).strip()

            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]

            result = json.loads(result_text)
            llm_suggestions = result.get('suggestions', [])
            suggestions.extend(llm_suggestions)

        except Exception as e:
            print(f"生成改进建议时出错: {e}")

        return suggestions

    async def generate_test_summary(self, execution: TestExecution) -> str:
        """生成测试摘要"""
        test_case = execution.test_case

        prompt = f"""
请为以下测试执行结果生成一个简洁的摘要：

测试用例: {test_case.title}
测试描述: {test_case.description}
执行结果: {execution.result.value}
执行时间: {execution.total_execution_time:.2f}秒

测试步骤:
{chr(10).join(f"- {step.description}: {step.result.value}" for step in test_case.steps)}

请生成一个2-3句话的摘要，说明测试执行的主要结果和关键发现。
"""

        try:
            response = await self.llm.ainvoke(prompt)
            if hasattr(response, 'content'):
                return response.content.strip()
            elif isinstance(response, str):
                return response.strip()
            else:
                return str(response).strip()
        except Exception as e:
            print(f"生成测试摘要时出错: {e}")
            return f"测试用例 '{test_case.title}' 执行{execution.result.value}，耗时{execution.total_execution_time:.2f}秒。"