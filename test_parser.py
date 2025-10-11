"""
测试需求解析器 - 从Markdown文件解析测试需求
"""

import re
import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ParsedTestCase:
    """解析后的测试用例（尚未通过LLM分析）"""
    title: str
    description: str
    raw_content: str
    sections: Dict[str, str]
    metadata: Dict[str, Any]


class TestRequirementParser:
    """测试需求解析器"""

    def __init__(self):
        self.section_patterns = {
            'title': r'^(?:#|测试标题|Title):\s*(.+)$',
            'description': r'^(?:##|测试描述|Description):\s*(.+)$',
            'url': r'^(?:###|测试网址|URL):\s*(.+)$',
            'preconditions': r'^(?:###|前置条件|Preconditions):\s*(.+)$',
            'steps': r'^(?:###|测试步骤|Steps|Test Steps):\s*(.+)$',
            'expected': r'^(?:###|期望结果|Expected Results|Expected):\s*(.+)$',
            'priority': r'^(?:###|优先级|Priority):\s*(.+)$',
            'tags': r'^(?:###|标签|Tags):\s*(.+)$',
        }

    def parse_markdown_file(self, file_path: str) -> List[ParsedTestCase]:
        """解析Markdown文件，提取测试用例"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"测试文件不存在: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return self.parse_markdown_content(content, file_path)

    def parse_markdown_content(self, content: str, source: str = "unknown") -> List[ParsedTestCase]:
        """解析Markdown内容"""
        # 按分隔符分割测试用例
        test_cases_raw = self._split_test_cases(content)
        cases = []

        for idx, case_content in enumerate(test_cases_raw):
            if case_content.strip():
                parsed_case = self._parse_single_test_case(case_content, f"{source}_case_{idx+1}")
                if parsed_case:
                    cases.append(parsed_case)

        return cases

    def _split_test_cases(self, content: str) -> List[str]:
        """分割测试用例"""
        # 支持多种分割方式
        separators = [
            r'\n---+\n',  # ---
            r'\n===+\n',  # ===
            r'\n\n### 测试用例\d+',  # ### 测试用例1
            r'\n\n### Test Case\d+',  # ### Test Case 1
        ]

        cases = [content]
        for sep in separators:
            new_cases = []
            for case_item in cases:
                new_cases.extend(re.split(sep, case_item))
            cases = new_cases

        # 过滤空用例
        return [case_item.strip() for case_item in cases if case_item.strip()]

    def _parse_single_test_case(self, content: str, case_id: str) -> Optional[ParsedTestCase]:
        """解析单个测试用例"""
        lines = content.strip().split('\n')
        sections = {}
        metadata = {'case_id': case_id}

        current_section = None
        current_content = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检查是否是标题行
            section_match = self._match_section(line)
            if section_match:
                # 保存上一个section的内容
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()

                # 开始新的section
                current_section = section_match['type']

                # 特殊处理：如果section标题后直接有内容，将内容作为第一行
                if section_match['content']:
                    current_content = [section_match['content']]
                else:
                    current_content = []

                # 提取元数据
                if section_match['type'] in ['priority', 'tags', 'url']:
                    metadata[section_match['type']] = section_match['content']
            else:
                if current_section:
                    current_content.append(line)
                else:
                    # 如果没有明确的section，默认为description
                    if 'description' not in sections:
                        current_section = 'description'
                        current_content = [line]
                    else:
                        current_content.append(line)

        # 保存最后一个section
        if current_section and current_content:
            sections[current_section] = '\n'.join(current_content).strip()

        # 至少需要title或description
        title = sections.get('title', f"测试用例_{case_id}")
        description = sections.get('description', '')

        if not title and not description:
            return None

        return ParsedTestCase(title=title, description=description, raw_content=content, sections=sections, metadata=metadata)

    def _match_section(self, line: str) -> Optional[Dict[str, str]]:
        """匹配section标题"""
        # 先尝试匹配带冒号的格式
        colon_patterns = {
            'title': r'^(?:#|测试标题|Title)[:：]\s*(.+)$',
            'description': r'^(?:##|测试描述|Description)[:：]\s*(.+)$',
            'url': r'^(?:###|测试网址|URL)[:：]\s*(.+)$',
            'preconditions': r'^(?:###|前置条件|Preconditions)[:：]\s*(.+)$',
            'steps': r'^(?:###|测试步骤|Steps|Test Steps)[:：]\s*(.+)$',
            'expected': r'^(?:###|期望结果|Expected Results|Expected)[:：]\s*(.+)$',
            'priority': r'^(?:###|优先级|Priority)[:：]\s*(.+)$',
            'tags': r'^(?:###|标签|Tags)[:：]\s*(.+)$',
        }

        # 检查冒号格式
        for section_type, pattern in colon_patterns.items():
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                return {'type': section_type, 'content': match.group(1).strip()}

        # 再尝试原始格式
        for section_type, pattern in self.section_patterns.items():
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                return {'type': section_type, 'content': match.group(1).strip()}
        return None

    def extract_test_steps(self, steps_text: str) -> List[str]:
        """提取测试步骤"""
        if not steps_text:
            return []

        steps = []
        # 支持多种步骤格式
        step_patterns = [
            r'^\d+\.\s*(.+)',  # 1. 步骤描述
            r'^-\s*(.+)',  # - 步骤描述
            r'^\*\s*(.+)',  # * 步骤描述
            r'^\•\s*(.+)',  # • 步骤描述
        ]

        for line in steps_text.split('\n'):
            line = line.strip()
            for pattern in step_patterns:
                match = re.match(pattern, line)
                if match:
                    steps.append(match.group(1).strip())
                    break

        return steps

    def extract_expected_results(self, expected_text: str) -> List[str]:
        """提取期望结果"""
        if not expected_text:
            return []

        results = []
        for line in expected_text.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                # 清理格式标记
                cleaned = re.sub(r'^[-*•]\s*', '', line)  # 移除列表标记
                cleaned = re.sub(r'^\d+\.\s*', '', cleaned)  # 移除数字标记
                if cleaned:
                    results.append(cleaned)

        return results


# 使用示例
if __name__ == "__main__":
    parser = TestRequirementParser()

    # 解析测试文件
    try:
        cases = parser.parse_markdown_file("sample_tests.md")
        print(f"成功解析 {len(cases)} 个测试用例")

        for idx, case in enumerate(cases, 1):
            print(f"\n--- 测试用例 {idx} ---")
            print(f"标题: {case.title}")
            print(f"描述: {case.description}")
            print(f"元数据: {case.metadata}")
            print(f"sections: {list(case.sections.keys())}")

    except FileNotFoundError:
        print("测试文件不存在")
