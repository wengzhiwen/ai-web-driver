"""
LLM测试分析器 - 使用LLM分析测试需求，判断测试类型和断言需求
"""

import json
import re
from typing import List, Dict, Any, Optional
from test_types import (
    TestCase, TestStep, Assertion, TestType, AssertionType
)
from test_parser import ParsedTestCase
from browser_use.llm import ChatOpenAI
from zhipuai import ZhipuAI

class LLMTestAnalyzer:
    """LLM测试分析器"""

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm  # browser-use 用的 LLM（保持不变）
        # 初始化智谱AI官方SDK用于分析工作
        self.zhipu_client = None
        try:
            import os
            from dotenv import load_dotenv
            load_dotenv()

            api_key = os.getenv("API_KEY")
            if api_key:
                self.zhipu_client = ZhipuAI(api_key=api_key)
        except Exception as e:
            print(f"⚠️ 智谱AI SDK 初始化失败，将使用 browser-use LLM: {e}")

    async def _call_llm(self, prompt: str) -> str:
        """调用LLM，优先使用智谱AI SDK，失败时回退到 browser-use LLM"""
        if self.zhipu_client:
            try:
                response = self.zhipu_client.chat.completions.create(
                    model="glm-4.5",
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"⚠️ 智谱AI API 调用失败，回退到 browser-use LLM: {e}")
                # 回退到browser-use LLM
                response = self.llm(prompt)
                if hasattr(response, 'content'):
                    return response.content
                elif isinstance(response, str):
                    return response
                else:
                    return str(response)
        else:
            # 直接使用 browser-use LLM
            response = self.llm(prompt)
            if hasattr(response, 'content'):
                return response.content
            elif isinstance(response, str):
                return response
            else:
                return str(response)

    async def analyze_test_case(self, parsed_case: ParsedTestCase) -> TestCase:
        """分析测试用例，转换为结构化测试用例"""
        # 1. 分析测试类型
        test_type = await self._analyze_test_type(parsed_case)

        # 2. 提取测试步骤
        test_steps = await self._extract_test_steps(parsed_case)

        # 3. 生成断言
        await self._generate_assertions(parsed_case, test_steps)

        # 4. 设置元数据
        priority = parsed_case.metadata.get('priority', 'medium')
        tags = self._parse_tags(parsed_case.metadata.get('tags', ''))
        url = parsed_case.metadata.get('url', '')

        # 添加URL相关的设置动作
        setup_actions = []
        if url:
            setup_actions.append(f"navigate_to_url: {url}")

        return TestCase(
            id=parsed_case.metadata.get('case_id', f"test_{hash(parsed_case.title)}"),
            title=parsed_case.title,
            description=parsed_case.description,
            test_type=test_type,
            priority=priority,
            tags=tags,
            preconditions=self._extract_preconditions(parsed_case),
            steps=test_steps,
            setup_actions=setup_actions,
            teardown_actions=[],  # 可以后续扩展
            timeout=300,
            retry_count=3
        )

    async def _analyze_test_type(self, parsed_case: ParsedTestCase) -> TestType:
        """分析测试类型"""
        prompt = f"""
请分析以下测试需求，判断它属于哪种测试类型。

测试标题: {parsed_case.title}
测试描述: {parsed_case.description}

测试类型包括：
- functional: 功能测试（验证功能是否正常工作）
- ui: UI测试（验证用户界面元素）
- navigation: 导航测试（验证页面跳转和导航）
- content: 内容测试（验证页面内容）
- performance: 性能测试（验证加载速度等性能指标）
- accessibility: 可访问性测试（验证无障碍访问）
- security: 安全测试（验证安全性）
- regression: 回归测试（验证修改后是否影响原有功能）

请只返回测试类型名称（例如：functional），不要返回其他内容。
"""

        try:
            # 使用新的LLM调用方法
            result_text = await self._call_llm(prompt)
            result = result_text.strip().lower()

            # 映射可能的回答到标准类型
            type_mapping = {
                '功能测试': 'functional',
                'ui测试': 'ui',
                '界面测试': 'ui',
                '导航测试': 'navigation',
                '页面测试': 'navigation',
                '内容测试': 'content',
                '性能测试': 'performance',
                '可访问性测试': 'accessibility',
                '安全测试': 'security',
                '回归测试': 'regression'
            }

            # 标准化结果
            for key, value in type_mapping.items():
                if key in result or result == value:
                    return TestType(value)

            # 默认返回functional
            return TestType.FUNCTIONAL

        except Exception as e:
            print(f"分析测试类型时出错: {e}")
            return TestType.FUNCTIONAL

    async def _extract_test_steps(self, parsed_case: ParsedTestCase) -> List[TestStep]:
        """提取测试步骤"""
        # 尝试多种可能的section key
        steps_text = (
            parsed_case.sections.get('steps', '') or
            parsed_case.sections.get('test_steps', '') or
            parsed_case.sections.get('test steps', '') or
            parsed_case.sections.get('测试步骤', '')
        )

        expected_text = (
            parsed_case.sections.get('expected', '') or
            parsed_case.sections.get('expected_results', '') or
            parsed_case.sections.get('expected results', '') or
            parsed_case.sections.get('期望结果', '')
        )

        if not steps_text:
            # 如果没有明确的步骤，从描述中生成
            print(f"未找到测试步骤，尝试从描述生成: {parsed_case.title}")
            print(f"可用的 sections: {list(parsed_case.sections.keys())}")
            steps_text = await self._generate_steps_from_description(parsed_case)
        else:
            print(f"成功解析到测试步骤: {len(steps_text.split(chr(10)))} 个步骤")

        # 解析步骤
        step_descriptions = self._parse_steps_text(steps_text)
        expected_results = self._parse_expected_results(expected_text)

        test_steps = []
        for i, step_desc in enumerate(step_descriptions):
            step_id = f"step_{i+1}"
            expected_result = expected_results[i] if i < len(expected_results) else ""

            test_step = TestStep(
                id=step_id,
                description=step_desc,
                action=step_desc,  # 目前步骤描述和操作相同
                expected_result=expected_result,
                assertions=[]  # 后续会添加断言
            )
            test_steps.append(test_step)

        return test_steps

    async def _generate_steps_from_description(self, parsed_case: ParsedTestCase) -> str:
        """从描述生成测试步骤"""
        prompt = f"""
请根据以下测试描述，生成详细的测试步骤。

测试标题: {parsed_case.title}
测试描述: {parsed_case.description}

请生成3-5个具体的测试步骤，每个步骤占一行，以数字开头。
步骤应该是具体可执行的操作，例如：
1. 打开网页
2. 点击某个按钮
3. 验证某个元素

只返回步骤列表，不要包含其他内容。
"""

        try:
            # 使用新的LLM调用方法
            return await self._call_llm(prompt)
        except Exception as e:
            print(f"生成测试步骤时出错: {e}")
            # 根据测试描述生成基础步骤，包含具体URL
            title = parsed_case.title.lower()
            description = parsed_case.description.lower()
            url = parsed_case.metadata.get('url', '')

            if '客服' in title or 'qq' in description:
                if url:
                    return f"1. 访问 {url}\n2. 点击客服中心链接\n3. 查找并验证客服QQ号码"
                else:
                    return "1. 访问 https://www.9you.com/\n2. 点击客服中心链接\n3. 查找并验证客服QQ号码"
            elif '充值' in title or '充值' in description:
                if url:
                    return f"1. 访问 {url}\n2. 查找充值相关链接\n3. 进入充值中心页面"
                else:
                    return "1. 访问 https://www.9you.com/\n2. 查找充值相关链接\n3. 进入充值中心页面"
            else:
                if url:
                    return f"1. 访问 {url}\n2. 执行主要操作\n3. 验证结果"
                else:
                    return "1. 访问 https://www.9you.com/\n2. 执行主要操作\n3. 验证结果"

    async def _generate_assertions(self, parsed_case: ParsedTestCase, test_steps: List[TestStep]) -> None:
        """生成断言"""
        prompt = f"""
请分析以下测试需求，为每个测试步骤生成相应的断言。

测试标题: {parsed_case.title}
测试描述: {parsed_case.description}
期望结果: {parsed_case.sections.get('expected', '')}

测试步骤：
{chr(10).join(f"{i+1}. {step.description}" for i, step in enumerate(test_steps))}

断言类型包括：
- element_exists: 元素存在
- element_not_exists: 元素不存在
- text_equals: 文本相等
- text_contains: 文本包含
- url_equals: URL相等
- url_contains: URL包含
- page_title: 页面标题
- element_visible: 元素可见

请为每个步骤生成1-2个断言，以JSON格式返回，格式如下：
{{
  "assertions": [
    {{
      "step_index": 0,
      "assertions": [
        {{
          "type": "element_exists",
          "target": "选择器或目标",
          "expected": "期望值"
        }}
      ]
    }}
  ]
}}

只返回JSON，不要包含其他内容。
"""

        try:
            # 使用新的LLM调用方法
            result_text = await self._call_llm(prompt)

            # 清理可能的markdown标记
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]

            data = json.loads(result_text)

            for i, step in enumerate(test_steps):
                step_assertions = []

                # 从LLM响应中获取该步骤的断言
                for assertion_data in data.get('assertions', []):
                    if assertion_data.get('step_index') == i:
                        for assert_info in assertion_data.get('assertions', []):
                            assertion = self._create_assertion_from_dict(assert_info)
                            if assertion:
                                step_assertions.append(assertion)

                # 如果没有生成断言，基于期望结果生成默认断言
                if not step_assertions and step.expected_result:
                    default_assertion = self._generate_default_assertion(step.expected_result)
                    if default_assertion:
                        step_assertions.append(default_assertion)

                step.assertions = step_assertions

        except Exception as e:
            print(f"生成断言时出错: {e}")
            # 生成默认断言
            self._generate_default_assertions(test_steps)

    def _create_assertion_from_dict(self, assert_info: Dict[str, Any]) -> Optional[Assertion]:
        """从字典创建断言对象"""
        try:
            type_str = assert_info.get('type', '')
            target = assert_info.get('target', '')
            expected = assert_info.get('expected', '')

            # 映射断言类型
            type_mapping = {
                'element_exists': AssertionType.ELEMENT_EXISTS,
                'element_not_exists': AssertionType.ELEMENT_NOT_EXISTS,
                'text_equals': AssertionType.TEXT_EQUALS,
                'text_contains': AssertionType.TEXT_CONTAINS,
                'url_equals': AssertionType.URL_EQUALS,
                'url_contains': AssertionType.URL_CONTAINS,
                'page_title': AssertionType.PAGE_TITLE,
                'element_visible': AssertionType.ELEMENT_VISIBLE,
                'element_enabled': AssertionType.ELEMENT_ENABLED,
            }

            assertion_type = type_mapping.get(type_str, AssertionType.TEXT_CONTAINS)

            return Assertion(
                type=assertion_type,
                target=target,
                expected=expected
            )
        except Exception as e:
            print(f"创建断言对象时出错: {e}")
            return None

    def _generate_default_assertion(self, expected_result: str) -> Optional[Assertion]:
        """生成默认断言"""
        if not expected_result:
            return None

        # 简单的启发式规则
        if 'QQ' in expected_result or any(char.isdigit() for char in expected_result):
            return Assertion(
                type=AssertionType.TEXT_CONTAINS,
                target="body",
                expected=expected_result
            )
        elif '页面' in expected_result or '标题' in expected_result:
            return Assertion(
                type=AssertionType.PAGE_TITLE,
                target="title",
                expected=expected_result
            )
        else:
            return Assertion(
                type=AssertionType.TEXT_CONTAINS,
                target="body",
                expected=expected_result
            )

    def _generate_default_assertions(self, test_steps: List[TestStep]) -> None:
        """为所有步骤生成默认断言"""
        for step in test_steps:
            if step.expected_result:
                assertion = self._generate_default_assertion(step.expected_result)
                if assertion:
                    step.assertions.append(assertion)

    def _parse_steps_text(self, steps_text: str) -> List[str]:
        """解析步骤文本"""
        if not steps_text:
            return []

        steps = []
        lines = steps_text.split('\n')

        for line in lines:
            line = line.strip()
            # 匹配数字开头的步骤
            match = re.match(r'^\d+[\.\.\s]*\s*(.+)', line)
            if match:
                steps.append(match.group(1))
            # 匹配列表标记
            elif line.startswith(('-', '*', '•')):
                steps.append(line[1:].strip())
            elif line and not line.startswith('#'):
                steps.append(line)

        return steps

    def _parse_expected_results(self, expected_text: str) -> List[str]:
        """解析期望结果"""
        if not expected_text:
            return []

        results = []
        lines = expected_text.split('\n')

        for line in lines:
            line = line.strip()
            # 匹配数字开头
            match = re.match(r'^\d+[\.\.\s]*\s*(.+)', line)
            if match:
                results.append(match.group(1))
            # 匹配列表标记
            elif line.startswith(('-', '*', '•')):
                results.append(line[1:].strip())
            elif line and not line.startswith('#'):
                results.append(line)

        return results

    def _parse_tags(self, tags_text: str) -> List[str]:
        """解析标签"""
        if not tags_text:
            return []

        # 支持多种分隔符
        tags = re.split(r'[,，\s]+', tags_text.strip())
        return [tag.strip() for tag in tags if tag.strip()]

    def _extract_preconditions(self, parsed_case: ParsedTestCase) -> List[str]:
        """提取前置条件"""
        preconditions_text = parsed_case.sections.get('preconditions', '')
        if not preconditions_text:
            return []

        preconditions = []
        lines = preconditions_text.split('\n')

        for line in lines:
            line = line.strip()
            match = re.match(r'^\d+[\.\.\s]*\s*(.+)', line)
            if match:
                preconditions.append(match.group(1))
            elif line.startswith(('-', '*', '•')):
                preconditions.append(line[1:].strip())
            elif line:
                preconditions.append(line)

        return preconditions