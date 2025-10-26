"""Supporting agents for the LLM-driven compilation pipeline."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .models import SiteProfile, TestRequest


@dataclass
class DSLSpecification:
    """Container for DSL definition artifacts shared with the LLM."""

    schema: Dict[str, object]
    sample: Dict[str, object]

    def as_prompt(self) -> str:
        schema_json = json.dumps(self.schema, ensure_ascii=False, indent=2)
        sample_json = json.dumps(self.sample, ensure_ascii=False, indent=2)
        guidelines = ("生成 ActionPlan 时请遵循以下规则：\n"
                      "1. 所有 selector 必须使用 Playwright 支持的语法，禁止使用 :contains()、jquery 伪类或 XPath。\n"
                      "2. 文本匹配请使用 :has-text(...) 或 Playwright 的 get_by_text，例如 .card:has-text('提交').\n"
                      "3. 优先使用站点 Profile 中提供的别名 selector（aliases），如 search.input、detail.title 等。\n"
                      "4. 文本断言和点击需指向具体元素，必要时在 selector 末尾追加 :has-text('具体文本').\n"
                      "5. 断言步骤的文本与随后的点击需匹配同一条数据项。\n"
                      "6. **操作类型匹配规则**：\n"
                      "   - **fill 操作**：必须选择输入框类元素（input、textbox、search等），切勿选择按钮或链接\n"
                      "   - **click 操作**：必须选择可交互元素（button、link、buy按钮等），切勿选择纯文本元素\n"
                      "   - **assert 操作**：可选择显示元素（title、text、label等），用于验证内容\n"
                      "7. **商品操作特别规则**：\n"
                      "   - 验证商品名称时使用文本类选择器\n"
                      "   - 点击商品时必须使用购买按钮或链接类选择器\n"
                      "   - 切勿将商品名称文本作为点击目标\n"
                      "8. **图片验证规则**：\n"
                      "   - 验证图片显示时使用img选择器，但不要验证图片包含文本\n"
                      "   - 图片验证应检查图片的visible状态，而非text内容\n"
                      "   - 切勿使用img:has-text()这类无效的组合\n")

        return ("你需要按照以下 JSON Schema 生成 ActionPlan DSL。\n"
                "### JSON Schema\n"
                f"```json\n{schema_json}\n```\n"
                "### 生成规则\n"
                f"{guidelines}\n"
                "### 示例\n"
                f"```json\n{sample_json}\n```\n"
                "务必输出符合 Schema 的 JSON，且只返回 JSON，不要添加多余说明。")


class SiteProfileSummarizer:
    """Agent responsible for turning a site profile into LLM-friendly text."""

    @staticmethod
    def summarize(profile: SiteProfile) -> str:
        grouped: Dict[str, List[str]] = {}
        for alias in profile.aliases.values():
            grouped.setdefault(alias.page_id, []).append(f"- `{alias.name}` → `{alias.selector}` ({alias.description or '无描述'})")
        lines = ["站点 Profile 摘要："]
        for page_id, items in grouped.items():
            lines.append(f"页面 `{page_id}`:")
            lines.extend(items)
        return "\n".join(lines)


class TestRequestSummarizer:
    """Agent to format the natural language request for the LLM."""

    @staticmethod
    def summarize(request: TestRequest) -> str:
        lines = [f"测试用例：{request.title}"]
        if request.base_url:
            lines.append(f"基准 URL：{request.base_url}")
        lines.append("详细步骤：")
        for step in request.steps:
            lines.append(f"{step.index}. {step.text}")
        return "\n".join(lines)


def load_dsl_specification(schema_path: Path) -> DSLSpecification:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    sample = {
        "meta": {
            "testId": "SAMPLE-001",
            "baseUrl": "https://example.com"
        },
        "steps": [
            {
                "t": "goto",
                "url": "/"
            },
            {
                "t": "fill",
                "selector": "input#search",
                "value": "关键词"
            },
            {
                "t": "click",
                "selector": "button.search-btn",
                "value": "搜索"
            },
            {
                "t": "assert",
                "selector": ".result-item .title",
                "kind": "visible"
            },
            {
                "t": "click",
                "selector": ".result-item .buy-btn",
                "value": "购买按钮"
            },
            {
                "t": "assert",
                "selector": ".product-title",
                "kind": "text_contains",
                "value": "商品详情",
            },
        ],
    }
    return DSLSpecification(schema=schema, sample=sample)
