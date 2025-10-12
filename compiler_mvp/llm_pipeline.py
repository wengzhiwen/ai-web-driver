"""LLM-driven compilation pipeline."""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from jsonschema import Draft7Validator, ValidationError

from .llm_agents import (SiteProfileSummarizer, TestRequestSummarizer, load_dsl_specification)
from .llm_client import LLMClient, LLMClientError
from .models import CompilationResult, CompiledStep, SiteAlias, SiteProfile, TestRequest

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
CONTAINS_SELECTOR_PATTERN = re.compile(r":contains\((['\"])\s*(.*?)\s*\1\)")


def extract_json_block(text: str) -> str:
    match = JSON_BLOCK_RE.search(text)
    if match:
        return match.group(1)
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace:last_brace + 1]
    raise ValueError("LLM output did not contain a JSON object")


def derive_base_url(request: TestRequest) -> str:
    if request.base_url:
        return request.base_url.rstrip("/")
    raise ValueError("Test request does not contain a base URL")


def derive_test_id(title: str) -> str:
    import hashlib
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
    if slug:
        return f"REQ-{slug.upper()}"
    digest = hashlib.md5(title.encode("utf-8")).hexdigest()[:8].upper()
    return f"REQ-{digest}"


class LLMCompilationPipeline:
    """Coordinates multiple LLM interactions to produce a valid ActionPlan."""

    def __init__(
        self,
        *,
        client: LLMClient,
        schema_path: Path,
        max_attempts: int = 3,
        temperature: float = 0.2,
    ) -> None:
        self.client = client
        self.spec = load_dsl_specification(schema_path)
        self.validator = Draft7Validator(self.spec.schema)
        self.max_attempts = max_attempts
        self.temperature = temperature

    def run(
        self,
        request: TestRequest,
        profile: SiteProfile,
        plan_root: Path,
        *,
        plan_name: Optional[str] = None,
        case_name: Optional[str] = None,
    ) -> CompilationResult:
        messages = self._initial_messages(request, profile)
        response_payload: Dict[str, object] | None = None
        validation_error: Optional[str] = None

        for _ in range(1, self.max_attempts + 1):
            try:
                completion = self.client.chat_completion(messages, temperature=self.temperature)
            except LLMClientError as exc:
                raise RuntimeError(f"LLM 调用失败: {exc}") from exc

            try:
                raw_json = extract_json_block(completion)
                response_payload = json.loads(raw_json)
            except json.JSONDecodeError as exc:
                validation_error = f"JSON 解析失败：{exc}"
            except ValueError as exc:
                validation_error = str(exc)
            else:
                try:
                    self._validate_payload(response_payload)
                    validation_error = None
                    break
                except ValidationError as exc:
                    validation_error = self._format_validation_error(exc)

            messages.append({
                "role": "user",
                "content": ("上一步生成的 JSON 存在问题：\n"
                            f"{validation_error}\n"
                            "请根据错误信息重新输出完整且符合 Schema 的 JSON，仍然只输出 JSON。"),
            })

        if validation_error is not None or response_payload is None:
            raise RuntimeError(f"多次尝试后仍未得到合法的 DSL：{validation_error}")

        enriched_payload = self._ensure_metadata(response_payload, request)
        result = self._materialize_plan(
            enriched_payload,
            plan_root,
            plan_name,
            case_name,
            profile,
        )
        self._validate_against_profile(result, profile)
        return result

    def _initial_messages(self, request: TestRequest, profile: SiteProfile) -> List[Dict[str, str]]:
        system_prompt = {
            "role": "system",
            "content": ("你是一名资深的 UI 自动化 DSL 编译专家。"
                        "请严格遵守提供的 JSON Schema，并只输出 JSON。"),
        }
        spec_prompt = {"role": "user", "content": self.spec.as_prompt()}
        scenario_prompt = {
            "role": "user",
            "content": (f"{TestRequestSummarizer.summarize(request)}\n\n"
                        f"{SiteProfileSummarizer.summarize(profile)}\n\n"
                        "请基于上述需求生成完整的 ActionPlan JSON。"),
        }
        return [system_prompt, spec_prompt, scenario_prompt]

    def _validate_payload(self, payload: Dict[str, object]) -> None:
        errors = sorted(self.validator.iter_errors(payload), key=lambda e: e.path)
        if errors:
            messages = [self._format_validation_error(error) for error in errors]
            raise ValidationError("; ".join(messages))

    @staticmethod
    def _format_validation_error(error: ValidationError) -> str:
        path = "->".join(str(part) for part in error.path)
        location = f"在 `{path}` " if path else ""
        return f"{location}{error.message}"

    def _ensure_metadata(self, payload: Dict[str, object], request: TestRequest) -> Dict[str, object]:
        payload = dict(payload)
        meta = dict(payload.get("meta") or {})
        meta.setdefault("testId", derive_test_id(request.title))
        try:
            base_url = derive_base_url(request)
        except ValueError:
            base_url = meta.get("baseUrl")
        if base_url:
            meta["baseUrl"] = base_url.rstrip("/")
        payload["meta"] = meta
        return payload

    def _materialize_plan(
        self,
        payload: Dict[str, object],
        plan_root: Path,
        plan_name: Optional[str],
        case_name: Optional[str],
        profile: SiteProfile,
    ) -> CompilationResult:
        test_id = payload["meta"]["testId"]
        base_url = payload["meta"]["baseUrl"]

        sanitized_steps: List[Dict[str, object]] = []
        matched_aliases: List[Optional[SiteAlias]] = []
        alias_list = list(profile.aliases.values())
        for step in payload.get("steps", []):
            step_dict = dict(step)
            selector = step_dict.get("selector")
            matched_alias: Optional[SiteAlias] = None
            if isinstance(selector, str):
                sanitized = self._sanitize_selector(selector)
                sanitized, matched_alias = self._fallback_selector_to_profile(
                    sanitized,
                    step_dict,
                    alias_list,
                )
                step_dict["selector"] = sanitized
            sanitized_steps.append(step_dict)
            matched_aliases.append(matched_alias)

        self._post_process_steps(sanitized_steps, matched_aliases, alias_list)
        payload["steps"] = sanitized_steps

        now_gmt8 = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
        timestamp = now_gmt8.strftime("%Y%m%dT%H%M%S")
        generated_plan_name = plan_name or f"{timestamp}_llm_plan"
        plan_dir = plan_root / generated_plan_name
        plan_dir.mkdir(parents=True, exist_ok=True)

        generated_case_name = case_name or f"case_{test_id.lower()}"
        case_dir = plan_dir / "cases" / generated_case_name
        case_dir.mkdir(parents=True, exist_ok=True)

        output_path = case_dir / "action_plan.json"
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

        steps = [CompiledStep(**dict(step.items())) for step in payload["steps"]]
        return CompilationResult(
            test_id=test_id,
            base_url=base_url,
            steps=steps,
            plan_dir=plan_dir,
            case_dir=case_dir,
        )

    def _post_process_steps(
        self,
        steps: List[Dict[str, object]],
        matched_aliases: List[Optional[SiteAlias]],
        aliases: List[SiteAlias],
    ) -> None:
        value_by_alias: Dict[str, str] = {}

        last_value: Optional[str] = None

        for index, step in enumerate(steps):
            selector = step.get("selector")
            if not isinstance(selector, str):
                continue
            step_type = (step.get("t") or "").lower()
            alias = matched_aliases[index]

            if step.get("kind") == "text_contains" and isinstance(step.get("value"), str):
                value = str(step["value"])
                step["selector"] = self._append_has_text(selector, value)
                last_value = value
                if alias:
                    value_by_alias[alias.selector] = value
                    value_by_alias[alias.name] = value
                continue

            if step_type == "assert":
                value = step.get("value")
                if not value and alias:
                    value = value_by_alias.get(alias.selector) or value_by_alias.get(alias.name)
                if not value:
                    value = last_value
                if value:
                    step["kind"] = step.get("kind") or "text_contains"
                    step["value"] = value
                    step["selector"] = self._append_has_text(selector, value)
                    last_value = value
                    if alias:
                        value_by_alias[alias.selector] = value
                        value_by_alias[alias.name] = value
                continue

            if step_type == "click":
                value = step.get("value")
                if not value and alias:
                    value = value_by_alias.get(alias.selector) or value_by_alias.get(alias.name)
                    if not value and "list" in alias.name.lower():
                        related = self._find_related_item_alias(alias, aliases)
                        if related:
                            alias = related
                            selector = related.selector
                            value = value_by_alias.get(related.selector) or value_by_alias.get(related.name)
                if not value:
                    value = last_value
                if value:
                    step["selector"] = self._append_has_text(selector, value)
                    step.setdefault("value", value)
                    if alias:
                        value_by_alias[alias.selector] = value
                        value_by_alias[alias.name] = value

    @staticmethod
    def _append_has_text(selector: str, value: str) -> str:
        if ":has-text(" in selector:
            return selector
        escaped = value.replace('"', '\"')
        return f'{selector}:has-text("{escaped}")'

    @staticmethod
    def _find_related_item_alias(list_alias: SiteAlias, aliases: List[SiteAlias]) -> Optional[SiteAlias]:
        for alias in aliases:
            if alias is list_alias:
                continue
            name_lower = alias.name.lower()
            if "item" in name_lower and ("university" in name_lower or "result" in name_lower):
                if list_alias.selector.rstrip(' >') in alias.selector:
                    return alias
        return None

    @staticmethod
    def _sanitize_selector(selector: str) -> str:

        def replace(match: re.Match[str]) -> str:
            text = match.group(2)
            text = text.replace('"', '\\"')
            return f':has-text("{text}")'

        return CONTAINS_SELECTOR_PATTERN.sub(replace, selector)

    @staticmethod
    def _fallback_selector_to_profile(
        selector: str,
        step: Dict[str, object],
        aliases: List[SiteAlias],
    ) -> Tuple[str, Optional[SiteAlias]]:
        if not aliases:
            return selector, None

        alias_by_selector = {alias.selector: alias for alias in aliases}
        if selector in alias_by_selector:
            return selector, alias_by_selector[selector]

        lowered_selector = selector.lower()
        for alias in aliases:
            if alias.selector.lower() in lowered_selector:
                return alias.selector, alias

        title_aliases = [
            alias for alias in aliases if "title" in alias.name.lower() or "heading" in alias.name.lower() or (
                alias.description and "标题" in alias.description) or (alias.description and "title" in alias.description.lower())
        ]
        if title_aliases and ("site-title" in lowered_selector or "page-title" in lowered_selector
                              or lowered_selector.strip() in {".site-title", "h1", "header"}):
            alias = title_aliases[0]
            return alias.selector, alias

        if "university-list" in lowered_selector or "nav-link" in lowered_selector:
            for alias in aliases:
                name_lower = alias.name.lower()
                desc_lower = (alias.description or "").lower()
                if (("results" in name_lower and "item" in name_lower) or ("university" in name_lower and ("item" in name_lower or "list" in name_lower))
                        or ("sidebar" in name_lower and "university" in name_lower) or ("大学" in desc_lower and ("列表" in desc_lower or "选项" in desc_lower))):
                    return alias.selector, alias

        best_alias: Optional[SiteAlias] = None
        best_score = 0
        selector_tokens = LLMCompilationPipeline._extract_tokens(selector)
        step_type = (step.get("t") or "").lower()

        for alias in aliases:
            score = 0
            alias_selector_tokens = LLMCompilationPipeline._extract_tokens(alias.selector)
            alias_name_tokens = LLMCompilationPipeline._extract_tokens(alias.name)
            alias_desc_tokens = LLMCompilationPipeline._extract_tokens(alias.description)

            score += 3 * len(selector_tokens & alias_selector_tokens)
            score += 2 * len(selector_tokens & alias_name_tokens)
            score += len(selector_tokens & alias_desc_tokens)

            if step_type == "fill" and any(keyword in alias_name_tokens or keyword in alias_selector_tokens for keyword in {"input", "field", "textbox"}):
                score += 4
            if step_type == "click" and any(keyword in alias_name_tokens or keyword in alias_selector_tokens
                                            for keyword in {"button", "btn", "item", "link", "list"}):
                score += 3
            if step_type == "assert" and step.get("kind") == "text_contains" and step.get("value"):
                value = str(step["value"])
                if alias.description and value in alias.description:
                    score += 3
                if alias.selector.lower().endswith("h1") or "title" in alias.name.lower():
                    score += 1
                if alias.description and any(keyword in alias.description.lower() for keyword in ("大学", "列表", "list")):
                    score += 2
                if any(keyword in alias.name.lower() for keyword in ("university", "results", "sidebar")):
                    score += 2
                if any(token in alias_name_tokens for token in {"list", "panel", "section"}):
                    score += 2
                if alias.description and any(keyword in alias.description for keyword in ("列表", "list", "容器")):
                    score += 2
                if any(token in alias_name_tokens for token in {"item", "link"}):
                    score -= 2

            if score > best_score:
                best_score = score
                best_alias = alias

        if best_alias and best_score >= 3:
            return best_alias.selector, best_alias

        for alias in aliases:
            tokens = [token for token in re.split(r"[._\-]+", alias.name.lower()) if len(token) >= 3]
            if tokens and all(token in lowered_selector for token in tokens):
                return alias.selector, alias
            if alias.description:
                desc_tokens = [token for token in alias.description.lower().split() if len(token) >= 3]
                if desc_tokens and all(token in lowered_selector for token in desc_tokens):
                    return alias.selector, alias

        return selector, None

    def _validate_against_profile(
        self,
        result: CompilationResult,
        profile: SiteProfile,
    ) -> None:
        disallowed_patterns = [":contains", "::", "contains(", "[text()"]
        allowed_step_kinds = {
            "visible",
            "text_contains",
            "text_equals",
            "text_regex",
            "invisible",
        }
        errors: List[str] = []

        for index, step in enumerate(result.steps, start=1):
            selector = step.selector
            step_type = step.t
            if selector:
                if any(pattern in selector for pattern in disallowed_patterns):
                    errors.append(f"步骤{index} selector {selector} 使用了不支持的伪类/语法")
            if step_type == "fill" and not step.value:
                errors.append(f"步骤{index} 缺少填充的 value 值")
            if step.kind and step.kind not in allowed_step_kinds:
                errors.append(f"步骤{index} 使用了未支持的断言类型 {step.kind}")

        if errors:
            raise ValueError("; ".join(errors))

    @staticmethod
    def _extract_tokens(text: Optional[str]) -> Set[str]:
        tokens: Set[str] = set()
        if not text:
            return tokens
        lowered = text.lower()
        for part in re.split(r"[^a-z0-9]+", lowered):
            if len(part) >= 2:
                tokens.add(part)
        for part in re.split(r"[\s._#:\-]+", lowered):
            if len(part) >= 2:
                tokens.add(part)
        return tokens


def run_pipeline(
    *,
    request: TestRequest,
    profile: SiteProfile,
    plan_root: Path,
    schema_path: Path,
    plan_name: Optional[str] = None,
    case_name: Optional[str] = None,
    max_attempts: int = 3,
    temperature: float = 0.2,
    api_timeout: Optional[float] = None,
) -> CompilationResult:
    client = LLMClient(timeout=api_timeout)
    pipeline = LLMCompilationPipeline(
        client=client,
        schema_path=schema_path,
        max_attempts=max_attempts,
        temperature=temperature,
    )
    return pipeline.run(
        request=request,
        profile=profile,
        plan_root=plan_root,
        plan_name=plan_name,
        case_name=case_name,
    )
