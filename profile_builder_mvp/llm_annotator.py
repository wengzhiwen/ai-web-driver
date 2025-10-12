"""LLM-based annotation pipeline for Site Profile drafts."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from compiler_mvp.llm_client import LLMClient, LLMClientError

from .models import AliasDefinition, AnnotationRequest, AnnotatedPage

LOGGER = logging.getLogger("profile_builder.annotator")


def _insert_missing_commas(snippet: str) -> str:
    """为常见的缺失逗号场景增加逗号。"""

    lines = snippet.splitlines()
    for idx in range(len(lines) - 1):
        current = lines[idx]
        following = lines[idx + 1].lstrip()
        if not following.startswith("\""):
            continue
        stripped = current.rstrip()
        if not stripped:
            continue
        if stripped.endswith((',', ':')) or stripped[-1] in "[{(":
            continue
        lines[idx] = stripped + ',' + current[len(stripped):]
    return "\n".join(lines)


def _remove_trailing_commas(snippet: str) -> str:
    """移除在 JSON 结尾常见的多余逗号。"""

    return re.sub(r',(?=\s*[}\]])', '', snippet)


def _append_missing_closing(snippet: str) -> str:
    """根据括号计数补齐可能缺失的收尾括号。"""

    balanced = snippet
    brace_gap = balanced.count('{') - balanced.count('}')
    bracket_gap = balanced.count('[') - balanced.count(']')
    if brace_gap > 0:
        balanced += '}' * brace_gap
    if bracket_gap > 0:
        balanced += ']' * bracket_gap
    return balanced


def _strip_json_comments(snippet: str) -> str:
    """移除常见的 `//` 与 `/* ... */` 注释行。"""

    cleaned = re.sub(r'/\*.*?\*/', '', snippet, flags=re.S)
    cleaned = re.sub(r'^\s*//.*$', '', cleaned, flags=re.MULTILINE)
    return '\n'.join(line for line in cleaned.splitlines())


def _extract_json(payload: str) -> Dict[str, Any]:
    """Try to parse JSON from the LLM response."""

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass

    start = payload.find("{")
    end = payload.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"LLM 返回的内容不是 JSON: {payload[:2000]}")

    snippet = payload[start:end + 1].strip()

    try:
        return json.loads(snippet)
    except json.JSONDecodeError as exc:
        last_exc = exc

    repaired = _strip_json_comments(snippet)
    if repaired != snippet:
        try:
            result = json.loads(repaired)
        except json.JSONDecodeError as exc:  # pragma: no cover - 依赖 LLM 行为
            last_exc = exc
        else:
            LOGGER.warning("自动修复 LLM JSON：移除注释")
            return result
        snippet = repaired

    repaired = _insert_missing_commas(snippet)
    if repaired != snippet:
        try:
            result = json.loads(repaired)
        except json.JSONDecodeError as exc:  # pragma: no cover - 依赖 LLM 行为
            last_exc = exc
        else:
            LOGGER.warning("自动修复 LLM JSON：补全缺失逗号")
            return result
        snippet = repaired

    repaired = _remove_trailing_commas(snippet)
    if repaired != snippet:
        try:
            result = json.loads(repaired)
        except json.JSONDecodeError as exc:  # pragma: no cover - 依赖 LLM 行为
            last_exc = exc
        else:
            LOGGER.warning("自动修复 LLM JSON：移除尾随逗号")
            return result
        snippet = repaired

    repaired = _append_missing_closing(snippet)
    if repaired != snippet:
        try:
            result = json.loads(repaired)
        except json.JSONDecodeError as exc:  # pragma: no cover - 依赖 LLM 行为
            last_exc = exc
        else:
            LOGGER.warning("自动修复 LLM JSON：补齐收尾括号")
            return result

    raise ValueError(f"LLM 返回的 JSON 无法解析: {last_exc}\n原始片段: {snippet[:2000]}", ) from last_exc


def _normalise_aliases(raw_aliases: Any) -> List[AliasDefinition]:
    results: List[AliasDefinition] = []
    if isinstance(raw_aliases, dict):
        iterator = raw_aliases.items()
    elif isinstance(raw_aliases, list):
        iterator = []
        for item in raw_aliases:
            if isinstance(item, dict):
                name = item.get("alias") or item.get("name")
                if name:
                    iterator.append((name, item))
    else:
        iterator = []

    for alias_name, payload in iterator:
        if not isinstance(payload, dict):
            continue
        selector = payload.get("selector")
        if not selector:
            continue
        description = payload.get("description")
        role = payload.get("role")
        confidence = payload.get("confidence")
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except ValueError:
                confidence = None
        notes = payload.get("notes")
        results.append(
            AliasDefinition(
                name=alias_name,
                selector=selector,
                description=description,
                role=role,
                confidence=confidence if isinstance(confidence, (int, float)) else None,
                notes=notes,
            ), )
    return results


class LLMAnnotator:
    """Annotates DOM snapshots via LLM prompts."""

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self.client = client or LLMClient()

    def annotate(self, request: AnnotationRequest) -> AnnotatedPage:
        dom_json = json.dumps(request.dom_summary, ensure_ascii=False, indent=2)
        LOGGER.debug("DOM 摘要 token 约 %s 字符", len(dom_json))

        if request.is_detail_page:
            label = request.detail_label or "详情页"
            detail_hint = (f"这是{label}，请以更抽象、更概括的方式描述板块和元素，不要逐字复述长文本。"
                           "请明确详情页主标题所在元素，并列出页面展示的核心数据项目，逐项说明用途与定位线索。")
        else:
            detail_hint = ""
        detail_line = f"页面类型提示: {detail_hint}\n" if detail_hint else ""

        messages = [
            {
                "role": "system",
                "content": ("你是前端测试工程专家，需要从页面 DOM 摘要中提取可用于 UI 自动化的元素别名。先理解页面的大致功能，再逐功能区块进行解析和抽取。"
                            "输出严格符合 JSON 格式，包含页面元信息、别名和推荐选择器。"),
            },
            {
                "role":
                "user",
                "content": ("请根据以下上下文生成页面标定草稿。\n\n"
                            f"URL: {request.url}\n"
                            f"页面标题: {request.title or '未知'}\n"
                            f"站点名称: {request.site_name or '未提供'}\n"
                            f"站点 BaseURL: {request.base_url or '未提供'}\n"
                            f"{detail_line}"
                            "请输出 JSON，字段示例如下：\n"
                            "{\n  \"page\": {\n    \"id\": \"page_id\",\n    \"name\": \"页面名称\",\n"
                            "    \"url_pattern\": \"/path\",\n    \"summary\": \"页面用途概述\",\n    \"aliases\": {\n"
                            "      \"alias.name\": {\n        \"selector\": \"data-test=example\",\n"
                            "        \"description\": \"元素作用说明\",\n        \"role\": \"按钮\",\n        \"confidence\": 0.8\n"
                            "      }\n    }\n  },\n  \"warnings\": []\n}\n"
                            "DOM 摘要 (JSON 字符串):\n"
                            f"```json\n{dom_json}\n```"),
            },
        ]

        try:
            response = self.client.chat_completion(
                messages,
                model=request.model,
                temperature=request.temperature,
            )
        except LLMClientError as exc:
            raise RuntimeError(f"调用 LLM 失败: {exc}") from exc

        payload = _extract_json(response)
        page_payload = payload.get("page") if isinstance(payload, dict) else None
        if not isinstance(page_payload, dict):
            raise ValueError("LLM 返回结果缺少 page 字段")

        page_id = page_payload.get("id") or page_payload.get("page_id")
        if not page_id:
            raise ValueError("LLM 返回结果缺少 page.id")

        page_name = page_payload.get("name") or page_payload.get("title") or page_id
        url_pattern = page_payload.get("url_pattern") or page_payload.get("path") or request.url
        summary = page_payload.get("summary") or page_payload.get("description")

        aliases_payload = page_payload.get("aliases") or page_payload.get("elements")
        aliases = _normalise_aliases(aliases_payload)
        if not aliases:
            LOGGER.warning("LLM 未识别任何别名，后续可能需要人工补充")

        warnings: List[str] = []
        raw_warnings = payload.get("warnings") if isinstance(payload, dict) else None
        if isinstance(raw_warnings, list):
            warnings = [str(item) for item in raw_warnings if item]

        return AnnotatedPage(
            page_id=str(page_id),
            page_name=str(page_name),
            url_pattern=str(url_pattern),
            summary=summary if isinstance(summary, str) else None,
            aliases=aliases,
            warnings=warnings,
            dom_summary=request.dom_summary,
        )
