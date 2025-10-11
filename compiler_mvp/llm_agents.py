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
        return ("你需要按照以下 JSON Schema 生成 ActionPlan DSL。\n"
                "### JSON Schema\n"
                f"```json\n{schema_json}\n```\n"
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
                "selector": "input#username",
                "value": "tester"
            },
            {
                "t": "click",
                "selector": "button#submit"
            },
            {
                "t": "assert",
                "selector": "h1.page-title",
                "kind": "text_contains",
                "value": "欢迎",
            },
        ],
    }
    return DSLSpecification(schema=schema, sample=sample)
