"""LLM-driven compilation pipeline."""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from jsonschema import Draft7Validator, ValidationError

from .llm_agents import (SiteProfileSummarizer, TestRequestSummarizer,
                         load_dsl_specification)
from .llm_client import LLMClient, LLMClientError
from .models import CompilationResult, CompiledStep, SiteProfile, TestRequest

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


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
        result = self._materialize_plan(enriched_payload, plan_root, plan_name, case_name)
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
    ) -> CompilationResult:
        test_id = payload["meta"]["testId"]
        base_url = payload["meta"]["baseUrl"]

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
