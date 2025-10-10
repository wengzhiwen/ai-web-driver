"""
测试报告生成器 - 生成详细的测试报告
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any
from jinja2 import Template, Environment, BaseLoader
from test_types import TestExecution, TestSuite, TestReport, TestResult
from result_analyzer import LLMResultAnalyzer

class TestReportGenerator:
    """测试报告生成器"""

    def __init__(self, llm_analyzer: LLMResultAnalyzer = None):
        self.llm_analyzer = llm_analyzer
        self.report_dir = "test_reports"
        self._ensure_report_dir()

    def _ensure_report_dir(self):
        """确保报告目录存在"""
        if not os.path.exists(self.report_dir):
            os.makedirs(self.report_dir)

    async def generate_report(self, executions: List[TestExecution],
                            suite_name: str = "Test Suite",
                            suite_description: str = "AI驱动的Web测试报告") -> TestReport:
        """生成测试报告"""
        # 创建测试套件
        test_suite = TestSuite(
            name=suite_name,
            description=suite_description,
            test_cases=[exec.test_case for exec in executions],
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        # 生成报告
        report = TestReport(
            test_suite=test_suite,
            executions=executions,
            generated_at=datetime.now(),
            summary={}
        )

        # 生成摘要统计
        report.summary = report.get_summary()

        return report

    async def save_html_report(self, report: TestReport, filename: str = None) -> str:
        """保存HTML报告"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_report_{timestamp}.html"

        filepath = os.path.join(self.report_dir, filename)

        # 生成HTML内容
        html_content = await self._generate_html_content(report)

        # 保存文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"HTML报告已保存: {filepath}")
        return filepath

    async def save_json_report(self, report: TestReport, filename: str = None) -> str:
        """保存JSON报告"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_report_{timestamp}.json"

        filepath = os.path.join(self.report_dir, filename)

        # 转换为可序列化的格式
        report_data = self._serialize_report(report)

        # 保存文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)

        print(f"JSON报告已保存: {filepath}")
        return filepath

    async def save_markdown_report(self, report: TestReport, filename: str = None) -> str:
        """保存Markdown报告"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_report_{timestamp}.md"

        filepath = os.path.join(self.report_dir, filename)

        # 生成Markdown内容
        md_content = await self._generate_markdown_content(report)

        # 保存文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)

        print(f"Markdown报告已保存: {filepath}")
        return filepath

    async def _generate_html_content(self, report: TestReport) -> str:
        """生成HTML报告内容"""
        html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report.test_suite.name }} - 测试报告</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 8px 8px 0 0;
        }
        .header h1 {
            margin: 0;
            font-size: 2.5em;
        }
        .header p {
            margin: 10px 0 0 0;
            opacity: 0.9;
        }
        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #fafafa;
        }
        .summary-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .summary-card h3 {
            margin: 0 0 10px 0;
            color: #333;
        }
        .summary-card .number {
            font-size: 2em;
            font-weight: bold;
            margin: 10px 0;
        }
        .passed { color: #28a745; }
        .failed { color: #dc3545; }
        .error { color: #fd7e14; }
        .skipped { color: #6c757d; }
        .content {
            padding: 30px;
        }
        .test-case {
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 20px;
            overflow: hidden;
        }
        .test-case-header {
            padding: 20px;
            background: #f8f9fa;
            border-bottom: 1px solid #ddd;
            cursor: pointer;
        }
        .test-case-header:hover {
            background: #e9ecef;
        }
        .test-case-content {
            padding: 20px;
            display: none;
        }
        .test-case.active .test-case-content {
            display: block;
        }
        .status-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
            text-transform: uppercase;
        }
        .status-passed {
            background: #d4edda;
            color: #155724;
        }
        .status-failed {
            background: #f8d7da;
            color: #721c24;
        }
        .status-error {
            background: #ffeaa7;
            color: #856404;
        }
        .status-skipped {
            background: #e2e3e5;
            color: #383d41;
        }
        .step {
            margin: 10px 0;
            padding: 10px;
            border-left: 4px solid #ddd;
        }
        .step.passed {
            border-left-color: #28a745;
            background: #f8fff9;
        }
        .step.failed {
            border-left-color: #dc3545;
            background: #fff8f8;
        }
        .step.error {
            border-left-color: #fd7e14;
            background: #fffdf7;
        }
        .assertions {
            margin-top: 10px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 4px;
        }
        .assertion {
            margin: 5px 0;
            padding: 5px;
            border-radius: 3px;
        }
        .assertion.passed {
            background: #d4edda;
        }
        .assertion.failed {
            background: #f8d7da;
        }
        .error-message {
            color: #dc3545;
            font-family: monospace;
            background: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
        }
        .metadata {
            font-size: 0.9em;
            color: #666;
        }
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
            margin: 20px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #28a745, #20c997);
            transition: width 0.3s ease;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ report.test_suite.name }}</h1>
            <p>{{ report.test_suite.description }}</p>
            <p>生成时间: {{ report.generated_at.strftime('%Y-%m-%d %H:%M:%S') }}</p>
        </div>

        <div class="summary">
            <div class="summary-card">
                <h3>总测试数</h3>
                <div class="number">{{ report.summary.total_tests }}</div>
            </div>
            <div class="summary-card">
                <h3>通过</h3>
                <div class="number passed">{{ report.summary.passed }}</div>
            </div>
            <div class="summary-card">
                <h3>失败</h3>
                <div class="number failed">{{ report.summary.failed }}</div>
            </div>
            <div class="summary-card">
                <h3>错误</h3>
                <div class="number error">{{ report.summary.error }}</div>
            </div>
            <div class="summary-card">
                <h3>通过率</h3>
                <div class="number">{{ "%.1f"|format(report.summary.pass_rate) }}%</div>
            </div>
            <div class="summary-card">
                <h3>总耗时</h3>
                <div class="number">{{ "%.2f"|format(report.summary.execution_time) }}s</div>
            </div>
        </div>

        <div class="content">
            <div class="progress-bar">
                <div class="progress-fill" style="width: {{ report.summary.pass_rate }}%"></div>
            </div>

            <h2>测试用例详情</h2>
            {% for execution in report.executions %}
            <div class="test-case" id="test-{{ loop.index }}">
                <div class="test-case-header" onclick="toggleTestCase({{ loop.index }})">
                    <h3>{{ execution.test_case.title }}</h3>
                    <p>{{ execution.test_case.description }}</p>
                    <div class="metadata">
                        <span class="status-badge status-{{ execution.result.value }}">{{ execution.result.value }}</span>
                        <span>执行时间: {{ "%.2f"|format(execution.total_execution_time or 0) }}s</span>
                        <span>测试类型: {{ execution.test_case.test_type.value }}</span>
                        <span>优先级: {{ execution.test_case.priority }}</span>
                    </div>
                </div>
                <div class="test-case-content">
                    <h4>测试步骤</h4>
                    {% for step in execution.test_case.steps %}
                    <div class="step {{ step.result.value }}">
                        <strong>步骤 {{ loop.index }}:</strong> {{ step.description }}
                        {% if step.expected_result %}
                        <br><em>期望: {{ step.expected_result }}</em>
                        {% endif %}
                        <div class="metadata">
                            状态: {{ step.result.value }}
                            {% if step.execution_time %}
                            | 耗时: {{ "%.2f"|format(step.execution_time) }}s
                            {% endif %}
                        </div>
                        {% if step.error_message %}
                        <div class="error-message">{{ step.error_message }}</div>
                        {% endif %}

                        {% if step.assertions %}
                        <div class="assertions">
                            <strong>断言:</strong>
                            {% for assertion in step.assertions %}
                            <div class="assertion {% if assertion.passed %}passed{% else %}failed{% endif %}">
                                {{ assertion.type.value }}: {{ assertion.target }}
                                {% if assertion.expected %}
                                = "{{ assertion.expected }}"
                                {% endif %}
                                {% if assertion.passed == true %}
                                ✅ 通过
                                {% elif assertion.passed == false %}
                                ❌ 失败
                                {% endif %}
                            </div>
                            {% endfor %}
                        </div>
                        {% endif %}
                    </div>
                    {% endfor %}

                    {% if execution.error_details %}
                    <h4>错误详情</h4>
                    <div class="error-message">
                        {{ execution.error_details | tojson_pretty }}
                    </div>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
    </div>

    <script>
        function toggleTestCase(index) {
            const testCase = document.getElementById(`test-${index}`);
            testCase.classList.toggle('active');
        }
    </script>
</body>
</html>
        """

        template = Template(html_template)
        return template.render(report=report)

    async def _generate_markdown_content(self, report: TestReport) -> str:
        """生成Markdown报告内容"""
        md_lines = [
            f"# {report.test_suite.name}",
            "",
            f"**描述:** {report.test_suite.description}",
            f"**生成时间:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 测试摘要",
            "",
            f"- **总测试数:** {report.summary.total_tests}",
            f"- **通过:** {report.summary.passed}",
            f"- **失败:** {report.summary.failed}",
            f"- **错误:** {report.summary.error}",
            f"- **跳过:** {report.summary.skipped}",
            f"- **通过率:** {report.summary.pass_rate:.1f}%",
            f"- **总耗时:** {report.summary.execution_time:.2f}秒",
            "",
            "## 测试用例详情",
            ""
        ]

        for i, execution in enumerate(report.executions, 1):
            status_emoji = {
                "passed": "✅",
                "failed": "❌",
                "error": "⚠️",
                "skipped": "⏭️"
            }

            md_lines.extend([
                f"### {i}. {execution.test_case.title} {status_emoji.get(execution.result.value, '❓')}",
                "",
                f"**描述:** {execution.test_case.description}",
                f"**状态:** {execution.result.value}",
                f"**执行时间:** {execution.total_execution_time or 0:.2f}秒",
                f"**测试类型:** {execution.test_case.test_type.value}",
                f"**优先级:** {execution.test_case.priority}",
                ""
            ])

            if execution.test_case.tags:
                md_lines.append(f"**标签:** {', '.join(execution.test_case.tags)}")
                md_lines.append("")

            # 测试步骤
            md_lines.extend(["**测试步骤:**", ""])
            for j, step in enumerate(execution.test_case.steps, 1):
                step_status = status_emoji.get(step.result.value, "❓")
                md_lines.append(f"{j}. {step.description} {step_status}")

                if step.expected_result:
                    md_lines.append(f"   - 期望: {step.expected_result}")

                if step.error_message:
                    md_lines.append(f"   - 错误: `{step.error_message}`")

                # 断言
                if step.assertions:
                    md_lines.append("   - 断言:")
                    for assertion in step.assertions:
                        assert_status = "✅" if assertion.passed else "❌"
                        md_lines.append(f"     - {assertion.type.value}: {assertion.target} {assert_status}")

                md_lines.append("")

            # 错误详情
            if execution.error_details:
                md_lines.extend(["**错误详情:**", ""])
                md_lines.append("```json")
                md_lines.append(json.dumps(execution.error_details, indent=2, ensure_ascii=False))
                md_lines.append("```")
                md_lines.append("")

            md_lines.append("---")
            md_lines.append("")

        return "\n".join(md_lines)

    def _serialize_report(self, report: TestReport) -> Dict[str, Any]:
        """序列化报告为字典"""
        return {
            "test_suite": {
                "name": report.test_suite.name,
                "description": report.test_suite.description,
                "created_at": report.test_suite.created_at.isoformat(),
                "updated_at": report.test_suite.updated_at.isoformat(),
                "test_cases": [
                    {
                        "id": tc.id,
                        "title": tc.title,
                        "description": tc.description,
                        "test_type": tc.test_type.value,
                        "priority": tc.priority,
                        "tags": tc.tags,
                        "steps": [
                            {
                                "id": step.id,
                                "description": step.description,
                                "expected_result": step.expected_result,
                                "result": step.result.value,
                                "executed": step.executed,
                                "execution_time": step.execution_time,
                                "error_message": step.error_message,
                                "assertions": [
                                    {
                                        "type": assertion.type.value,
                                        "target": assertion.target,
                                        "expected": assertion.expected,
                                        "actual": assertion.actual,
                                        "passed": assertion.passed,
                                        "error_message": assertion.error_message
                                    }
                                    for assertion in step.assertions
                                ]
                            }
                            for step in tc.steps
                        ]
                    }
                    for tc in report.test_suite.test_cases
                ]
            },
            "executions": [
                {
                    "execution_id": exec.execution_id,
                    "test_case_id": exec.test_case.id,
                    "start_time": exec.start_time.isoformat(),
                    "end_time": exec.end_time.isoformat() if exec.end_time else None,
                    "result": exec.result.value,
                    "total_execution_time": exec.total_execution_time,
                    "browser_logs": exec.browser_logs,
                    "screenshots": exec.screenshots,
                    "error_details": exec.error_details
                }
                for exec in report.executions
            ],
            "generated_at": report.generated_at.isoformat(),
            "summary": report.summary
        }

    async def generate_all_formats(self, executions: List[TestExecution],
                                 suite_name: str = "Test Suite",
                                 suite_description: str = "AI驱动的Web测试报告") -> Dict[str, str]:
        """生成所有格式的报告"""
        report = await self.generate_report(executions, suite_name, suite_description)

        # 生成各种格式的报告
        html_path = await self.save_html_report(report)
        json_path = await self.save_json_report(report)
        md_path = await self.save_markdown_report(report)

        return {
            "html": html_path,
            "json": json_path,
            "markdown": md_path
        }