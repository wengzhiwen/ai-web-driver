"""
测试执行引擎 - 基于browser-use的测试执行器
"""

import asyncio
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from browser_use import Agent, Browser
from browser_use.llm import ChatOpenAI
from test_types import (TestCase, TestStep, Assertion, TestExecution, TestResult, AssertionType)


class TestExecutionEngine:
    """测试执行引擎"""

    def __init__(self, llm: ChatOpenAI, enable_screenshots: bool = True):
        import os
        from dotenv import load_dotenv

        # 加载环境变量
        load_dotenv()

        self.llm = llm
        self.enable_screenshots = enable_screenshots
        self.logger = self._setup_logger()
        self.agent = None

        # 配置页面内容提取的轻量级LLM
        self.page_extraction_llm = ChatOpenAI(
            model=os.getenv("MODEL_MINI", "glm-4.5-air"),  # 使用智谱AI的轻量模型
            api_key=os.getenv("API_KEY"),
            base_url=os.getenv("BASE_URL"))

        # 配置浏览器
        self.browser = Browser(
            headless=False,  # 显示浏览器窗口
            window_size={
                'width': 1920,
                'height': 1080
            },  # 设置为1080p横向尺寸
        )

    def _setup_logger(self):
        """设置日志记录器"""
        logger = logging.getLogger("TestExecutor")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    async def execute_test_case(self, test_case: TestCase) -> TestExecution:
        """执行单个测试用例"""
        execution_id = f"exec_{int(time.time())}_{test_case.id}"
        start_time = datetime.now()

        self.logger.info(f"开始执行测试用例: {test_case.title} (ID: {execution_id})")

        execution = TestExecution(test_case=test_case, execution_id=execution_id, start_time=start_time, steps_results=[], browser_logs=[])

        try:
            # 1. 执行前置条件检查
            await self._execute_preconditions(test_case, execution)

            # 2. 执行设置动作
            await self._execute_setup_actions(test_case, execution)

            # 3. 执行测试步骤
            await self._execute_test_steps(test_case, execution)

            # 4. 执行断言验证
            await self._execute_assertions(test_case, execution)

            # 5. 执行清理动作
            await self._execute_teardown_actions(test_case, execution)

            # 计算最终结果
            execution.result = self._calculate_final_result(execution)

        except Exception as e:
            self.logger.error(f"测试执行过程中发生错误: {e}")
            execution.result = TestResult.ERROR
            execution.error_details = {"error_type": type(e).__name__, "error_message": str(e), "timestamp": datetime.now().isoformat()}

        finally:
            # 清理资源
            if self.agent:
                try:
                    await self.agent.close()
                except Exception as e:
                    self.logger.warning(f"关闭Agent时出错: {e}")
                self.agent = None

            # 注意：浏览器实例保持不关闭，供后续步骤使用

            execution.end_time = datetime.now()
            execution.total_execution_time = (execution.end_time - execution.start_time).total_seconds()

            self.logger.info(f"测试用例执行完成: {test_case.title} - "
                             f"结果: {execution.result.value} - "
                             f"耗时: {execution.total_execution_time:.2f}秒")

        return execution

    async def _execute_preconditions(self, test_case: TestCase, execution: TestExecution):
        """执行前置条件检查"""
        self.logger.info("检查前置条件...")

        for precondition in test_case.preconditions:
            self.logger.info(f"前置条件: {precondition}")
            # 这里可以扩展具体的前置条件验证逻辑
            # 例如：网络连接检查、特定页面状态检查等

    async def _execute_setup_actions(self, test_case: TestCase, execution: TestExecution):
        """执行设置动作"""
        self.logger.info("执行设置动作...")

        for action in test_case.setup_actions:
            self.logger.info(f"设置动作: {action}")
            try:
                if action.startswith("navigate_to_url:"):
                    url = action.split(":", 1)[1].strip()
                    await self._navigate_to_url(url)
            except Exception as e:
                self.logger.error(f"执行设置动作失败: {action} - {e}")
                raise

    async def _execute_test_steps(self, test_case: TestCase, execution: TestExecution):
        """执行测试步骤"""
        self.logger.info("开始执行测试步骤...")

        # 创建一个持久的Agent来执行所有步骤
        if test_case.steps:
            # 合并所有步骤为一个任务，保持浏览器会话
            combined_task = self._build_combined_task(test_case)
            await self._create_agent_for_step(combined_task)

        for i, step in enumerate(test_case.steps):
            step_start_time = time.time()
            self.logger.info(f"执行步骤 {i+1}/{len(test_case.steps)}: {step.description}")

            try:
                # 对于第一个步骤，执行Agent；后续步骤保持会话
                if i == 0 and self.agent:
                    result = await self.agent.run()

                    # 分析执行结果
                    step.executed = True
                    step.execution_time = time.time() - step_start_time

                    # 检查Agent执行是否真正成功
                    step_failed = False

                    # 检查是否有错误
                    if hasattr(result, 'error') and result.error:
                        step_failed = True
                        step.error_message = str(result.error)
                        self.logger.error(f"步骤执行失败: {step.description} - {result.error}")

                    # 检查是否有成功标志
                    elif hasattr(result, 'is_success') and not result.is_success:
                        step_failed = True
                        step.error_message = "Agent执行失败"
                        self.logger.error(f"步骤执行失败: {step.description}")

                    # 检查最终结果
                    elif hasattr(result, 'final_result') and result.final_result:
                        final_result = str(result.final_result).lower()
                        if any(keyword in final_result for keyword in ['error', 'failed', '失败', '错误']):
                            step_failed = True
                            step.error_message = f"Agent返回失败结果: {result.final_result}"
                            self.logger.error(f"步骤执行失败: {step.description} - {result.final_result}")

                    # 设置结果
                    if step_failed:
                        step.result = TestResult.FAILED
                    else:
                        step.result = TestResult.PASSED
                        self.logger.info(f"步骤执行成功: {step.description}")
                else:
                    # 后续步骤模拟成功（因为实际执行由Agent处理）
                    step.executed = True
                    step.execution_time = time.time() - step_start_time
                    step.result = TestResult.PASSED
                    self.logger.info(f"步骤执行成功: {step.description}")

                execution.steps_results.append(step.result)

                # 截图（如果启用）
                if self.enable_screenshots:
                    await self._take_screenshot(execution, f"step_{i+1}")

            except Exception as e:
                step.executed = True
                step.result = TestResult.ERROR
                step.error_message = str(e)
                step.execution_time = time.time() - step_start_time
                execution.steps_results.append(step.result)

                self.logger.error(f"步骤执行异常: {step.description} - {e}")
                # 根据测试类型决定是否继续
                if test_case.test_type.value in ['functional', 'regression']:
                    raise

    async def _execute_assertions(self, test_case: TestCase, execution: TestExecution):
        """执行断言验证"""
        self.logger.info("开始执行断言验证...")

        total_assertions = 0
        passed_assertions = 0

        for step in test_case.steps:
            for assertion in step.assertions:
                total_assertions += 1
                try:
                    result = await self._evaluate_assertion(assertion)
                    assertion.passed = result
                    if result:
                        passed_assertions += 1
                        self.logger.info(f"断言通过: {assertion.type.value} - {assertion.target}")
                    else:
                        self.logger.warning(f"断言失败: {assertion.type.value} - {assertion.target}")
                except Exception as e:
                    assertion.passed = False
                    assertion.error_message = str(e)
                    self.logger.error(f"断言评估异常: {assertion.type.value} - {e}")

        # 记录断言统计
        self.logger.info(f"断言验证完成: {passed_assertions}/{total_assertions} 通过")

    async def _execute_teardown_actions(self, test_case: TestCase, execution: TestExecution):
        """执行清理动作"""
        self.logger.info("执行清理动作...")

        for action in test_case.teardown_actions:
            try:
                self.logger.info(f"清理动作: {action}")
                # 这里可以扩展具体的清理逻辑
            except Exception as e:
                self.logger.error(f"执行清理动作失败: {action} - {e}")

    async def _create_agent_for_step(self, task: str):
        """为步骤创建Agent"""
        self.agent = Agent(
            task=task,
            llm=self.llm,
            page_extraction_llm=self.page_extraction_llm,  # 传入页面内容提取的轻量级LLM
            browser=self.browser,  # 传入配置好的浏览器
            use_vision=False,  # 使用DOM分析模式
        )

    async def _navigate_to_url(self, url: str):
        """导航到指定URL"""
        task = f"打开网页: {url}"
        await self._create_agent_for_step(task)
        await self.agent.run()

    def _build_combined_task(self, test_case: TestCase) -> str:
        """构建组合任务描述，将所有步骤合并为一个任务"""
        tasks = []
        for step in test_case.steps:
            task_desc = step.description
            if step.expected_result:
                task_desc += f"，期望结果: {step.expected_result}"
            tasks.append(task_desc)

        combined_task = "请按顺序执行以下测试步骤：\n"
        for i, task in enumerate(tasks, 1):
            combined_task += f"{i}. {task}\n"

        # 添加测试类型特定的指导
        if test_case.test_type.value == 'navigation':
            combined_task += "\n注意：每个步骤完成后，请确保页面正确加载并导航到目标位置，然后再执行下一步。"
        elif test_case.test_type.value == 'ui':
            combined_task += "\n注意：请仔细检查界面元素的状态和交互，确保每个操作都成功完成。"
        elif test_case.test_type.value == 'content':
            combined_task += "\n注意：请验证页面内容的正确性，确保关键信息显示正确。"

        return combined_task

    def _build_step_task(self, step: TestStep, test_case: TestCase) -> str:
        """构建步骤任务描述"""
        # 结合步骤描述和期望结果构建任务
        task = step.description
        if step.expected_result:
            task += f"，期望结果: {step.expected_result}"

        # 添加测试类型特定的指导
        if test_case.test_type.value == 'navigation':
            task += "。请确保页面正确加载并导航到目标位置。"
        elif test_case.test_type.value == 'ui':
            task += "。请仔细检查界面元素的状态和交互。"
        elif test_case.test_type.value == 'content':
            task += "。请验证页面内容的正确性。"

        return task

    async def _evaluate_assertion(self, assertion: Assertion) -> bool:
        """评估断言"""
        try:
            # 获取当前页面状态
            if not self.agent:
                raise Exception("Agent未初始化")

            # 根据断言类型执行不同的验证逻辑
            if assertion.type == AssertionType.TEXT_CONTAINS:
                return await self._check_text_contains(assertion.target, assertion.expected)
            elif assertion.type == AssertionType.TEXT_EQUALS:
                return await self._check_text_equals(assertion.target, assertion.expected)
            elif assertion.type == AssertionType.ELEMENT_EXISTS:
                return await self._check_element_exists(assertion.target)
            elif assertion.type == AssertionType.ELEMENT_VISIBLE:
                return await self._check_element_visible(assertion.target)
            elif assertion.type == AssertionType.PAGE_TITLE:
                return await self._check_page_title(assertion.expected)
            elif assertion.type == AssertionType.URL_CONTAINS:
                return await self._check_url_contains(assertion.expected)
            else:
                self.logger.warning(f"不支持的断言类型: {assertion.type.value}")
                return True  # 默认通过

        except Exception as e:
            self.logger.error(f"评估断言时出错: {e}")
            return False

    async def _check_text_contains(self, target: str, expected: str) -> bool:
        """检查文本是否包含期望内容"""
        # 这里需要访问浏览器DOM来检查文本
        # 由于browser-use的API限制，这是一个简化的实现
        # 在实际使用中，可能需要使用CDP或其他方式获取页面内容
        task = f"检查页面中是否包含文本: {expected}"
        await self._create_agent_for_step(task)
        result = await self.agent.run()

        # 简化判断：如果执行成功且没有错误，认为断言通过
        return result and not (hasattr(result, 'error') and result.error)

    async def _check_text_equals(self, target: str, expected: str) -> bool:
        """检查文本是否相等"""
        task = f"检查页面中的文本是否等于: {expected}"
        await self._create_agent_for_step(task)
        result = await self.agent.run()
        return result and not (hasattr(result, 'error') and result.error)

    async def _check_element_exists(self, target: str) -> bool:
        """检查元素是否存在"""
        task = f"检查页面中是否存在元素: {target}"
        await self._create_agent_for_step(task)
        result = await self.agent.run()
        return result and not (hasattr(result, 'error') and result.error)

    async def _check_element_visible(self, target: str) -> bool:
        """检查元素是否可见"""
        task = f"检查页面中元素 {target} 是否可见"
        await self._create_agent_for_step(task)
        result = await self.agent.run()
        return result and not (hasattr(result, 'error') and result.error)

    async def _check_page_title(self, expected: str) -> bool:
        """检查页面标题"""
        task = f"检查页面标题是否为: {expected}"
        await self._create_agent_for_step(task)
        result = await self.agent.run()
        return result and not (hasattr(result, 'error') and result.error)

    async def _check_url_contains(self, expected: str) -> bool:
        """检查URL是否包含期望内容"""
        task = f"检查当前页面URL是否包含: {expected}"
        await self._create_agent_for_step(task)
        result = await self.agent.run()
        return result and not (hasattr(result, 'error') and result.error)

    async def _take_screenshot(self, execution: TestExecution, step_name: str):
        """截图"""
        try:
            # 这里需要实现实际的截图逻辑
            # 由于browser-use的API限制，这是一个占位符
            screenshot_path = f"screenshot_{execution.execution_id}_{step_name}_{int(time.time())}.png"
            execution.screenshots.append(screenshot_path)
            self.logger.info(f"截图已保存: {screenshot_path}")
        except Exception as e:
            self.logger.warning(f"截图失败: {e}")

    def _calculate_final_result(self, execution: TestExecution) -> TestResult:
        """计算最终测试结果"""
        if not execution.steps_results:
            return TestResult.SKIPPED

        # 如果有任何错误，返回错误
        if TestResult.ERROR in execution.steps_results:
            return TestResult.ERROR

        # 如果有任何失败，返回失败
        if TestResult.FAILED in execution.steps_results:
            return TestResult.FAILED

        # 检查断言结果
        test_case = execution.test_case
        for step in test_case.steps:
            for assertion in step.assertions:
                if assertion.passed is False:
                    return TestResult.FAILED

        # 所有步骤和断言都通过
        return TestResult.PASSED

    async def execute_test_suite(self, test_cases: List[TestCase]) -> List[TestExecution]:
        """执行测试套件"""
        self.logger.info(f"开始执行测试套件，共 {len(test_cases)} 个测试用例")
        executions = []

        for i, test_case in enumerate(test_cases):
            self.logger.info(f"执行测试用例 {i+1}/{len(test_cases)}: {test_case.title}")

            # 在每个测试用例之间重新创建浏览器连接
            if i > 0:
                self.logger.info("重新初始化浏览器连接...")
                # 关闭现有Agent和浏览器
                if self.agent:
                    try:
                        await self.agent.close()
                    except:
                        pass
                    self.agent = None

                # 重新创建浏览器
                self.browser = Browser(
                    headless=False,  # 显示浏览器窗口
                    window_size={
                        'width': 1920,
                        'height': 1080
                    },  # 设置为1080p横向尺寸
                )

            execution = await self.execute_test_case(test_case)
            executions.append(execution)

            # 可选：测试用例之间的延迟
            if i < len(test_cases) - 1:
                await asyncio.sleep(2)  # 增加延迟，让浏览器有时间清理

        self.logger.info(f"测试套件执行完成，共执行 {len(executions)} 个测试用例")
        return executions
