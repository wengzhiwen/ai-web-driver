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
                      "6. **根据 role 字段选择正确的元素（关键）**：\n"
                      "   - 站点Profile中每个元素都标注了 role 字段（如：文本、按钮、链接、输入框等）\n"
                      "   - **fill 操作**：必须选择 role=\"输入框\" 的元素，切勿选择按钮或链接\n"
                      "   - **click 操作**：必须选择 role=\"按钮\" 或 role=\"链接\" 的元素，切勿选择 role=\"文本\" 的元素\n"
                      "   - **assert 操作**：可选择 role=\"文本\"、role=\"标题\" 等显示元素，用于验证内容\n"
                      "7. **常见错误模式及修正**：\n"
                      "   - ✗ 错误：点击商品名称（role=\"文本\"） → 元素不可点击或点击无效\n"
                      "   - ✓ 正确：点击购买按钮（role=\"按钮\"） → 成功进入详情页\n"
                      "   - **识别方法**：在别名中查找包含 'button'、'btn'、'link' 关键字且 role 为按钮/链接的元素\n"
                      "8. **图片验证规则（HTML标准）**：\n"
                      "   - img 元素不包含文本内容，仅能验证其可见性\n"
                      "   - ✗ 错误：img:has-text('xxx') - HTML标准中img元素不包含文本子节点\n"
                      "   - ✓ 正确：img 配合 kind=\"visible\" - 验证图片元素存在且可见\n"
                      "   - 图片验证步骤不应包含value字段，kind只能是 \"visible\"\n"
                      "9. **标准测试流程示例**：\n"
                      "   - 搜索商品：fill (role=\"输入框\") → click 搜索按钮(role=\"按钮\")\n"
                      "   - 验证商品存在：assert 商品名称(role=\"文本\")，kind=\"text_contains\"\n"
                      "   - 进入详情页：click 购买/详情按钮(role=\"按钮\")，而非点击商品名称\n"
                      "   - 验证详情页：assert 商品标题(role=\"文本\") + assert 商品图片(role=\"图片\"，kind=\"visible\")\n")

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
            role_info = f", role=\"{alias.role}\"" if hasattr(alias, 'role') and alias.role else ""
            grouped.setdefault(alias.page_id, []).append(f"- `{alias.name}` → `{alias.selector}`{role_info} ({alias.description or '无描述'})")
        lines = ["站点 Profile 摘要（请特别注意每个元素的 role 字段）："]
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
