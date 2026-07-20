"""OpenAI 兼容的 LLMProvider 实现。

调用符合 OpenAI chat completions API 格式的 POST {base_url}/chat/completions 接口。
DeepSeek、百炼（DashScope 的 OpenAI-compatible 模式）等厂商只要遵循该协议，
切换时只需要改 LLM_BASE_URL / LLM_MODEL 配置，不需要新增代码。

每次调用都会记录 LLM 交互日志（LLM_REQUEST / LLM_RESPONSE / LLM_ERROR），并将
HTTP 失败、超时、非法 JSON 等场景映射为细化的错误码。
"""
from __future__ import annotations

import json
import time

import httpx

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import LLMProviderError
from app.core.logging import get_logger, log_llm_error, log_llm_request, log_llm_response
from app.providers.llm.base import LLMProvider

logger = get_logger(__name__)


class OpenAICompatibleLLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ):
        self._base_url = (base_url or settings.llm_base_url).rstrip("/")
        self._api_key = api_key or settings.llm_api_key
        self._model = model or settings.llm_model
        self._default_timeout = timeout_seconds or settings.llm_timeout_seconds

    @property
    def model(self) -> str:
        return self._model

    async def chat_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict,
        temperature: float = 0.0,
        timeout_seconds: int | None = None,
    ) -> dict:
        timeout = timeout_seconds or self._default_timeout
        user_content = json.dumps(user_payload, ensure_ascii=False)
        payload = {
            "model": self._model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            # 尽量要求模型直接返回 JSON；并不是所有 OpenAI-compatible 厂商都支持
            # response_format，这里只是"尽力而为"，下面解析阶段仍会做容错处理。
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"

        # LLM 交互日志：请求
        log_llm_request(self._model, user_content, system_prompt=system_prompt)
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                body = resp.json()
        except httpx.TimeoutException as exc:
            cost = (time.perf_counter() - start) * 1000
            log_llm_error(self._model, exc, cost_ms=cost)
            raise LLMProviderError(f"llm timeout: {exc}", error_code=ErrorCode.LLM_TIMEOUT)
        except httpx.HTTPStatusError as exc:
            cost = (time.perf_counter() - start) * 1000
            status = exc.response.status_code if exc.response is not None else "?"
            detail = exc.response.text[:500] if exc.response is not None else str(exc)
            log_llm_error(self._model, f"HTTP {status}: {detail}", cost_ms=cost)
            # 429 -> 限流；其它按通用 LLM 调用失败处理
            code = ErrorCode.LLM_RATE_LIMIT if status == 429 else ErrorCode.LLM_ERROR
            raise LLMProviderError(f"llm request failed: HTTP {status}", error_code=code)
        except httpx.HTTPError as exc:
            cost = (time.perf_counter() - start) * 1000
            log_llm_error(self._model, exc, cost_ms=cost)
            raise LLMProviderError(f"llm request error: {exc}")

        cost = (time.perf_counter() - start) * 1000
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            log_llm_error(self._model, f"bad response shape: {exc}", cost_ms=cost)
            raise LLMProviderError(
                f"unexpected chat completion response shape: {exc}",
                error_code=ErrorCode.LLM_NO_RESPONSE,
            )

        try:
            result = json.loads(_strip_markdown_fence(content))
        except (json.JSONDecodeError, TypeError) as exc:
            log_llm_error(self._model, f"invalid json: {str(content)[:200]!r}", cost_ms=cost)
            raise LLMProviderError(
                f"llm did not return valid json: {exc}",
                error_code=ErrorCode.LLM_INVALID_JSON,
            )

        if not isinstance(result, dict):
            log_llm_error(self._model, f"json is not an object: {str(content)[:200]!r}", cost_ms=cost)
            raise LLMProviderError(
                "llm returned json but it is not an object",
                error_code=ErrorCode.LLM_INVALID_JSON,
            )

        # LLM 交互日志：响应
        log_llm_response(self._model, content, cost_ms=cost)
        return result


def _strip_markdown_fence(text: str) -> str:
    """兼容处理：即便要求了 json_object，个别模型仍会套一层 ```json ... ``` 代码块。"""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
