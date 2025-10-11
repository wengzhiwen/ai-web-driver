"""LLM client implemented via the OpenAI Chat Completions API."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

DEFAULT_TIMEOUT = 60.0


class LLMClientError(RuntimeError):
    """Raised when the LLM API returns an error."""


class LLMClient:
    """Wrapper around the OpenAI chat completions endpoint."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        env_api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
        if not env_api_key:
            raise ValueError("OPENAI_API_KEY (或 API_KEY) 未配置，无法调用 LLM")

        env_base_url = base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("BASE_URL") or "https://api.openai.com/v1"
        env_model = default_model or os.getenv("OPENAI_MODEL") or os.getenv("MODEL_STD")
        if not env_model:
            raise ValueError("OPENAI_MODEL (或 MODEL_STD) 未配置，无法确定默认模型")

        timeout_env = os.getenv("LLM_TIMEOUT")
        self.timeout = timeout or (float(timeout_env) if timeout_env else DEFAULT_TIMEOUT)
        self.model = env_model
        self.client = OpenAI(api_key=env_api_key, base_url=env_base_url)

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        target_model = model or self.model
        try:
            response = self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
                timeout=self.timeout,
            )
        except Exception as exc:  # pragma: no cover - SDK 提供的异常层级
            raise LLMClientError(f"LLM API 调用失败：{exc}") from exc

        if not response.choices:
            raise LLMClientError("LLM 返回结果为空")

        message = response.choices[0].message
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content

        # ChatCompletionMessage content 可能是列表
        if isinstance(content, list):
            texts = [item.get("text") for item in content if isinstance(item, dict) and item.get("text")]
            if texts:
                return "".join(texts)

        raise LLMClientError("LLM 返回结果不包含文本内容")
