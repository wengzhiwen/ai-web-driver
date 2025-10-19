# -*- coding: UTF-8 -*-
#!/usr/bin/env python3
"""
NL驱动测试代理 - 直接使用Claude Code MCP版本
极简设计：直接调用Claude Code执行浏览器自动化测试
"""

import asyncio
import argparse
import logging
import subprocess
import json
import time
import shutil
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


class ClaudeCodeMCPDriver:
    """Claude Code MCP驱动器 - 直接调用Claude Code执行测试"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def execute_test_command(self, command: str, timeout: int = 60) -> Dict[str, Any]:
        """执行Claude Code测试命令"""
        try:
            # 直接使用Claude Code执行命令，授予权限
            cmd = ['claude', '-p', command, '--output-format', 'json', '--dangerously-skip-permissions']

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=Path.cwd(), check=False)

            if result.returncode == 0:
                # 尝试解析JSON输出
                try:
                    output_data = json.loads(result.stdout)
                    return {'success': True, 'output': output_data, 'raw_output': result.stdout.strip(), 'error': result.stderr.strip()}
                except json.JSONDecodeError:
                    return {'success': True, 'output': result.stdout.strip(), 'raw_output': result.stdout.strip(), 'error': result.stderr.strip()}
            else:
                return {'success': False, 'error': result.stderr.strip(), 'output': result.stdout.strip()}

        except subprocess.TimeoutExpired:
            return {'success': False, 'error': f'命令执行超时 ({timeout}秒)'}
        except Exception as e:
            return {'success': False, 'error': f'执行异常: {str(e)}'}

    async def run_test_case(self, test_file: str) -> Dict[str, Any]:
        """运行单个测试用例"""
        start_time = time.time()

        try:
            # 读取测试用例文件
            with open(test_file, 'r', encoding='utf-8') as f:
                test_content = f.read()

            self.logger.info(f"🚀 开始执行测试: {test_file}")

            # 构建Claude Code命令 - 直接让Claude Code执行完整的测试
            command = f"""
你是一个专业的Web测试工程师。请按照以下测试需求执行测试，并使用Playwright MCP进行浏览器自动化：

测试需求文件内容：
```markdown
{test_content}
```

请执行以下任务：
1. 使用Playwright MCP打开浏览器
2. 根据测试步骤执行浏览器操作
3. 验证所有断言条件
4. 生成详细的测试报告

执行要求：
- 使用mcp__playwright__browser_navigate打开页面
- 使用mcp__playwright__browser_click点击元素
- 使用mcp__playwright__browser_type输入文本
- 使用mcp__playwright__browser_snapshot获取页面状态
- 使用mcp__playwright__browser_take_screenshot保存截图
- 每个步骤都要确认执行成功
- 如遇到错误，立即停止并报告

请返回JSON格式的测试结果：
{{
    "success": true/false,
    "summary": "测试总结",
    "steps_executed": ["步骤1", "步骤2", ...],
    "assertions_verified": [
        {{
            "assertion": "断言描述",
            "result": "PASS/FAIL",
            "details": "详细信息"
        }}
    ],
    "screenshots": ["截图文件路径"],
    "errors": ["错误信息（如有）"],
    "execution_time": 执行时间（秒）
}}
"""

            # 执行测试命令
            result = await self.execute_test_command(command, timeout=300)

            execution_time = time.time() - start_time

            if result['success']:
                # 解析测试结果
                try:
                    parsed_result = None
                    if isinstance(result['output'], dict):
                        # 如果输出是字典，尝试从result字段中提取JSON
                        if 'result' in result['output'] and isinstance(result['output']['result'], str):
                            result_text = result['output']['result']
                            # 查找JSON代码块
                            json_match = re.search(r'```json\s*(\{.*?\})\s*```', result_text, re.DOTALL)
                            if json_match:
                                json_str = json_match.group(1)
                                test_result = self._parse_json_payload(json_str)
                                parsed_result = test_result
                            else:
                                # 如果没有代码块，尝试查找第一个JSON对象
                                json_start = result_text.find('{')
                                json_end = result_text.rfind('}') + 1
                                if json_start != -1 and json_end > json_start:
                                    json_str = result_text[json_start:json_end]
                                    test_result = self._parse_json_payload(json_str)
                                    parsed_result = test_result
                                else:
                                    raise ValueError("无法从结果中提取JSON")
                        else:
                            test_result = result['output']
                            parsed_result = test_result
                    else:
                        # 尝试从文本中提取JSON
                        json_start = result['output'].find('{')
                        json_end = result['output'].rfind('}') + 1
                        if json_start != -1 and json_end > json_start:
                            json_str = result['output'][json_start:json_end]
                            test_result = self._parse_json_payload(json_str)
                            parsed_result = test_result
                        else:
                            # 如果没有JSON，创建基本结果
                            test_result = {
                                'success': True,
                                'summary': '测试已执行',
                                'steps_executed': [],
                                'assertions_verified': [],
                                'screenshots': [],
                                'errors': [],
                                'execution_time': execution_time,
                                'raw_output': result['output']
                            }

                    # 直接使用Claude Code的result文本生成报告
                    if isinstance(result['output'], dict) and 'result' in result['output']:
                        # 创建简化的测试结果
                        claude_result_text = result['output']['result']
                        test_result = {
                            'success': True,
                            'summary': 'Claude Code执行完成',
                            'steps_executed': [],
                            'assertions_verified': [],
                            'screenshots': [],
                            'errors': [],
                            'execution_time': execution_time,
                            'claude_result': claude_result_text
                        }
                    else:
                        claude_result_text = str(result.get('output', ''))
                        test_result = {
                            'success': True,
                            'summary': 'Claude Code执行完成',
                            'steps_executed': [],
                            'assertions_verified': [],
                            'screenshots': [],
                            'errors': [],
                            'execution_time': execution_time,
                            'claude_result': claude_result_text
                        }

                    if isinstance(parsed_result, dict):
                        # 尝试保留Claude返回的详细字段
                        if isinstance(parsed_result.get('success'), bool):
                            test_result['success'] = parsed_result['success']
                        if parsed_result.get('summary'):
                            test_result['summary'] = parsed_result['summary']
                        if isinstance(parsed_result.get('steps_executed'), list):
                            test_result['steps_executed'] = parsed_result['steps_executed']
                        if isinstance(parsed_result.get('assertions_verified'), list):
                            test_result['assertions_verified'] = parsed_result['assertions_verified']
                        if isinstance(parsed_result.get('errors'), list):
                            test_result['errors'] = parsed_result['errors']
                        if parsed_result.get('execution_time') is not None:
                            normalized_execution_time = self._normalize_execution_time(parsed_result['execution_time'])
                            if normalized_execution_time is not None:
                                test_result['execution_time'] = normalized_execution_time
                            else:
                                test_result['execution_time'] = parsed_result['execution_time']
                        if isinstance(parsed_result.get('screenshots'), list):
                            test_result['screenshots'] = [s for s in parsed_result['screenshots'] if isinstance(s, str)]

                    report_dir = Path("./test_reports")
                    report_dir.mkdir(exist_ok=True)
                    test_result['screenshots'] = self.relocate_screenshots(test_result.get('screenshots', []), report_dir,
                                                                           Path(test_file).stem, claude_result_text)

                    # 保存测试报告
                    report_path = await self.save_test_report(test_file, test_result, test_content)

                    return {
                        'success': test_result.get('success', True),
                        'test_result': test_result,
                        'report_path': report_path,
                        'execution_time': execution_time,
                        'raw_output': result.get('raw_output', '')
                    }

                except Exception as e:
                    self.logger.error(f"解析测试结果失败: {e}")
                    # 创建失败时的测试结果
                    error_test_result = {
                        'success': False,
                        'summary': f'结果解析失败: {str(e)}',
                        'steps_executed': [],
                        'assertions_verified': [],
                        'screenshots': [],
                        'errors': [str(e)],
                        'execution_time': execution_time,
                        'claude_result': result.get('raw_output', '')
                    }
                    # 即使解析失败也生成报告
                    report_path = await self.save_test_report(test_file, error_test_result, test_content)
                    return {
                        'success': False,
                        'test_result': error_test_result,
                        'report_path': report_path,
                        'execution_time': execution_time,
                        'raw_output': result.get('raw_output', ''),
                        'error': error_test_result['summary']
                    }
            else:
                return {'success': False, 'error': result['error'], 'execution_time': execution_time}

        except Exception as e:
            self.logger.error(f"测试执行失败: {e}")
            return {'success': False, 'error': str(e), 'execution_time': time.time() - start_time}

    async def save_test_report(self, test_file: str, test_result: Dict[str, Any], test_content: str) -> str:
        """保存测试报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        test_name = Path(test_file).stem
        report_path = f"./test_reports/{test_name}_{timestamp}.md"

        # 确保报告目录存在
        Path("./test_reports").mkdir(exist_ok=True)

        # 生成Markdown报告
        execution_time_display = self._format_execution_time(test_result.get('execution_time'))

        report_content = f"""# 测试报告: {test_name}

## 测试概览

**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**测试文件**: {test_file}
**总体状态**: {'✅ PASS' if test_result.get('success', False) else '❌ FAIL'}
**执行时间**: {execution_time_display}

## 测试总结

{test_result.get('summary', '无总结')}

## 执行步骤

"""

        for i, step in enumerate(test_result.get('steps_executed', []), 1):
            report_content += f"{i}. {step}\n"

        report_content += "\n## 断言验证结果\n\n"

        for assertion in test_result.get('assertions_verified', []):
            status = "✅" if assertion.get('result') == 'PASS' else "❌"
            report_content += f"{status} **{assertion.get('assertion', '未知断言')}** - {assertion.get('result', 'UNKNOWN')}\n"
            if assertion.get('details'):
                report_content += f"   - 详细信息: {assertion['details']}\n"
            report_content += "\n"

        # 添加Claude Code的详细结果
        if test_result.get('claude_result'):
            report_content += "## Claude Code 测试结果详情\n\n"
            report_content += test_result['claude_result']
            report_content += "\n\n"

        if test_result.get('errors'):
            report_content += "## 错误信息\n\n"
            for error in test_result['errors']:
                report_content += f"❌ {error}\n"
            report_content += "\n"

        if test_result.get('screenshots'):
            report_content += "## 测试截图\n\n"
            for screenshot in test_result['screenshots']:
                report_content += f"📸 {screenshot}\n"
            report_content += "\n"

        report_content += f"""## 原始测试需求

```markdown
{test_content}
```

## 执行环境

- **工具**: NL驱动测试代理 v2.0
- **驱动**: Claude Code + Playwright MCP
- **执行时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---
*由NL驱动测试代理自动生成*
"""

        # 写入报告文件
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        self.logger.info(f"📊 测试报告已保存: {report_path}")
        return report_path

    def relocate_screenshots(self, screenshot_paths: List[str], target_dir: Path, test_name: str, claude_result_text: str) -> List[str]:
        """将截图移动到测试报告目录"""
        relocated_paths: List[str] = []
        base_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for index, raw_path in enumerate(screenshot_paths, start=1):
            if not raw_path:
                continue
            src_path = Path(raw_path)
            if not src_path.is_absolute():
                src_path = Path.cwd() / src_path
            if not src_path.exists():
                self.logger.debug(f"截图不存在，跳过: {raw_path}")
                continue

            suffix = src_path.suffix or ".png"
            candidate = target_dir / src_path.name
            if candidate.exists():
                candidate = target_dir / f"{test_name}_{base_timestamp}_{index}{suffix}"

            try:
                shutil.move(str(src_path), candidate)
                relocated_paths.append(str(candidate))
            except Exception as move_error:
                self.logger.error(f"移动截图失败: {raw_path} -> {move_error}")

        if not relocated_paths and claude_result_text:
            self.logger.debug("未找到可迁移的截图，保留原始结果描述")
        return relocated_paths

    def _parse_json_payload(self, json_str: str) -> Dict[str, Any]:
        """解析Claude输出的JSON，自动修复常见的非标准格式"""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            normalized = self._normalize_loose_json(json_str)
            if normalized != json_str:
                try:
                    return json.loads(normalized)
                except json.JSONDecodeError:
                    pass
            raise

    @staticmethod
    def _normalize_loose_json(json_str: str) -> str:
        """尝试为遗漏引号的取值补齐引号"""
        pattern = re.compile(r'("([^"]+)"\s*:\s*)([^"\{\[\]\},\s][^,\}\]]*)', re.UNICODE)

        def replacer(match: re.Match) -> str:
            prefix: str = match.group(1)
            raw_value: str = match.group(3).strip()
            if raw_value in {'true', 'false', 'null'}:
                return prefix + raw_value
            if re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', raw_value):
                return prefix + raw_value
            return prefix + json.dumps(raw_value, ensure_ascii=False)

        previous: Optional[str] = None
        current = json_str
        while previous != current:
            previous = current
            current = pattern.sub(replacer, current)
        return current

    @staticmethod
    def _normalize_execution_time(value: Any) -> Optional[float]:
        """尝试将执行时间转换为浮点数"""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.search(r'[\d.]+', value)
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    return None
        return None

    @staticmethod
    def _format_execution_time(value: Any) -> str:
        """格式化执行时间输出"""
        if isinstance(value, (int, float)):
            return f"{float(value):.2f}秒"
        if value:
            return str(value)
        return "未知"


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="NL驱动测试代理 - Claude Code MCP版本")
    parser.add_argument("test_file", help="测试需求文件路径")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    # 设置日志
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if not Path(args.test_file).exists():
        print(f"❌ 测试需求文件不存在: {args.test_file}")
        return

    # 创建并运行测试
    driver = ClaudeCodeMCPDriver()

    try:
        print(f"🚀 开始执行NL驱动测试: {args.test_file}")
        result = await driver.run_test_case(args.test_file)

        if result['success']:
            print("\n🎉 测试执行成功!")
            print(f"📄 报告: {result.get('report_path', '无报告')}")
            if result.get('test_result', {}).get('screenshots'):
                print(f"📸 截图: {len(result['test_result']['screenshots'])} 个")
        else:
            print(f"\n❌ 测试失败: {result.get('error', '未知错误')}")

        print(f"⏱️ 执行时间: {result['execution_time']:.2f}秒")

    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
    except Exception as e:
        print(f"\n❌ 执行异常: {e}")


if __name__ == "__main__":
    asyncio.run(main())
