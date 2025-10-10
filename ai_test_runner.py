"""
AI驱动的Web测试工具主程序
整合所有组件，提供完整的测试执行流程
"""

import asyncio
import os
import argparse
from datetime import datetime
from typing import List, Optional

from browser_use.llm import ChatOpenAI
from dotenv import load_dotenv

# 导入自定义模块
from test_parser import TestRequirementParser
from llm_analyzer import LLMTestAnalyzer
from test_executor import TestExecutionEngine
from result_analyzer import LLMResultAnalyzer
from report_generator import TestReportGenerator
from test_types import TestExecution, TestCase


class AITestRunner:
    """AI测试运行器 - 主要的测试工具类"""

    def __init__(self):
        # 加载环境变量
        load_dotenv()

        # 初始化LLM
        self.llm = self._init_llm()

        # 初始化组件
        self.parser = TestRequirementParser()
        self.analyzer = LLMTestAnalyzer(self.llm)
        self.executor = TestExecutionEngine(self.llm, enable_screenshots=True)
        self.result_analyzer = LLMResultAnalyzer(self.llm)
        self.report_generator = TestReportGenerator(self.result_analyzer)

        print("🤖 AI驱动的Web测试工具已初始化")

    def _init_llm(self) -> ChatOpenAI:
        """初始化LLM"""
        api_key = os.getenv("API_KEY")
        base_url = os.getenv("BASE_URL")
        model = os.getenv("MODEL_STD", "glm-4-flash")

        if not api_key:
            raise ValueError("未找到API_KEY环境变量，请检查配置文件")

        return ChatOpenAI(model=model, api_key=api_key, base_url=base_url)

    async def run_tests_from_file(self, test_file: str, suite_name: Optional[str] = None) -> List[TestExecution]:
        """从文件运行测试"""
        print(f"📁 开始解析测试文件: {test_file}")

        # 解析测试需求
        try:
            parsed_cases = self.parser.parse_markdown_file(test_file)
            print(f"✅ 成功解析 {len(parsed_cases)} 个测试用例")
        except Exception as e:
            print(f"❌ 解析测试文件失败: {e}")
            return []

        if not parsed_cases:
            print("⚠️ 未找到有效的测试用例")
            return []

        # 分析测试用例
        print("🧠 使用LLM分析测试用例...")
        test_cases = []
        for i, parsed_case in enumerate(parsed_cases):
            try:
                print(f"  分析测试用例 {i+1}/{len(parsed_cases)}: {parsed_case.title}")
                test_case = await self.analyzer.analyze_test_case(parsed_case)
                test_cases.append(test_case)
            except Exception as e:
                print(f"❌ 分析测试用例失败: {parsed_case.title} - {e}")

        if not test_cases:
            print("❌ 没有成功分析的测试用例")
            return []

        # 设置套件名称
        if not suite_name:
            suite_name = f"测试套件_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 执行测试
        print(f"🚀 开始执行测试套件: {suite_name}")
        print(f"   共 {len(test_cases)} 个测试用例")

        executions = await self.executor.execute_test_suite(test_cases)

        # 分析执行结果
        print("📊 分析执行结果...")
        for i, execution in enumerate(executions):
            try:
                # 使用LLM进行智能结果分析
                analyzed_result = await self.result_analyzer.analyze_execution_result(execution)
                execution.result = analyzed_result

                # 生成测试摘要
                summary = await self.result_analyzer.generate_test_summary(execution)
                print(f"  测试用例 {i+1}: {execution.test_case.title}")
                print(f"    结果: {execution.result.value}")
                print(f"    摘要: {summary}")
            except Exception as e:
                print(f"⚠️ 结果分析失败: {e}")

        return executions

    async def run_single_test(self, test_description: str) -> TestExecution:
        """运行单个测试（从描述）"""
        print(f"🎯 运行单个测试: {test_description}")

        # 创建临时解析的测试用例
        from test_parser import ParsedTestCase
        from test_types import TestType
        import re

        # 从描述中提取URL
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, test_description)
        url = urls[0] if urls else ""

        temp_parsed = ParsedTestCase(title="临时测试用例",
                                     description=test_description,
                                     raw_content=test_description,
                                     sections={"description": test_description},
                                     metadata={
                                         "case_id": f"temp_{int(datetime.now().timestamp())}",
                                         "url": url
                                     })

        # 分析测试用例
        test_case = await self.analyzer.analyze_test_case(temp_parsed)

        # 执行测试
        execution = await self.executor.execute_test_case(test_case)

        # 分析结果
        analyzed_result = await self.result_analyzer.analyze_execution_result(execution)
        execution.result = analyzed_result

        # 生成摘要
        summary = await self.result_analyzer.generate_test_summary(execution)
        print(f"  结果: {execution.result.value}")
        print(f"  摘要: {summary}")

        return execution

    async def generate_reports(self, executions: List[TestExecution], suite_name: str = "Test Suite") -> dict:
        """生成测试报告"""
        print("📋 生成测试报告...")

        if not executions:
            print("⚠️ 没有测试执行结果，无法生成报告")
            return {}

        try:
            # 生成所有格式的报告
            report_paths = await self.report_generator.generate_all_formats(executions, suite_name)

            print("✅ 测试报告生成完成:")
            for format_type, path in report_paths.items():
                print(f"  {format_type.upper()}: {path}")

            # 生成套件分析
            try:
                suite_analysis = await self.result_analyzer.analyze_test_suite_results(executions)
                print(f"📈 测试套件分析:")
                print(f"  通过率: {suite_analysis['summary']['pass_rate']:.1f}%")
                print(f"  总耗时: {suite_analysis['execution_time']['total']:.2f}秒")
            except Exception as e:
                print(f"⚠️ 套件分析失败: {e}")
                # 提供默认分析
                total = len(executions)
                passed = sum(1 for e in executions if e.result.value == "passed")
                failed = sum(1 for e in executions if e.result.value == "failed")
                error = sum(1 for e in executions if e.result.value == "error")
                total_time = sum(e.total_execution_time or 0 for e in executions)
                print(f"📈 测试套件分析:")
                print(f"  通过率: {(passed/total*100):.1f}%" if total > 0 else "  通过率: 0%")
                print(f"  总耗时: {total_time:.2f}秒")

            return report_paths

        except Exception as e:
            print(f"❌ 生成报告失败: {e}")
            return {}


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="AI驱动的Web测试工具")
    parser.add_argument("--file", "-f", help="测试需求文件路径（Markdown格式）")
    parser.add_argument("--test", "-t", help="单个测试描述")
    parser.add_argument("--suite", "-s", help="测试套件名称")
    parser.add_argument("--no-report", action="store_true", help="不生成测试报告")

    args = parser.parse_args()

    async def run():
        test_runner = AITestRunner()
        executions = []

        try:
            if args.file:
                # 从文件运行测试
                executions = await test_runner.run_tests_from_file(args.file, args.suite)

            elif args.test:
                # 运行单个测试
                execution = await test_runner.run_single_test(args.test)
                executions = [execution]

            else:
                print("❌ 请指定测试文件或测试描述")
                print("使用 --help 查看帮助信息")
                return

            # 生成报告
            if not args.no_report and executions:
                suite_name = args.suite or f"测试套件_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                await test_runner.generate_reports(executions, suite_name)

            # 显示最终统计
            if executions:
                total = len(executions)
                passed = sum(1 for e in executions if e.result.value == "passed")
                failed = sum(1 for e in executions if e.result.value == "failed")
                error = sum(1 for e in executions if e.result.value == "error")

                print(f"\n🎉 测试完成!")
                print(f"   总计: {total}")
                print(f"   通过: {passed}")
                print(f"   失败: {failed}")
                print(f"   错误: {error}")
                print(f"   通过率: {(passed/total*100):.1f}%" if total > 0 else "   通过率: 0%")

        except KeyboardInterrupt:
            print("\n⚠️ 测试被用户中断")
        except Exception as e:
            print(f"❌ 测试执行失败: {e}")
            import traceback
            traceback.print_exc()

    # 运行主程序
    asyncio.run(run())


if __name__ == "__main__":
    main()
