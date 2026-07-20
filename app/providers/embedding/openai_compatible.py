"""OpenAI-compatible embedding provider.

Calls a POST {base_url}/embeddings endpoint that follows the OpenAI embeddings API
shape. Works with OpenAI and any compatible gateway (vLLM, Ollama's OpenAI shim,
Azure-style proxies, etc.).

Every call is wrapped with LLM interaction logs (LLM_REQUEST / LLM_RESPONSE /
LLM_ERROR) and maps HTTP failures to细化的错误码（超时 / 限流 / 其它）。
"""
from __future__ import annotations

import time

import httpx

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import EmbeddingError
from app.core.logging import get_logger, log_llm_error, log_llm_request, log_llm_response
from app.providers.embedding.base import EmbeddingProvider

logger = get_logger(__name__)


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        timeout: float = 30.0,
    ):
        self._base_url = (base_url or settings.model_base_url).rstrip("/")
        self._api_key = api_key or settings.model_api_key
        self._model = model or settings.embedding_model
        self._dimension = dimension or settings.embedding_dim
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self._model, "input": texts}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/embeddings"

        # LLM 交互日志：请求
        log_llm_request(self._model, texts[0], input_count=len(texts))
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                body = resp.json()
        except httpx.TimeoutException as exc:
            cost = (time.perf_counter() - start) * 1000
            log_llm_error(self._model, exc, cost_ms=cost)
            raise EmbeddingError(f"embedding timeout: {exc}", error_code=ErrorCode.LLM_TIMEOUT)
        except httpx.HTTPStatusError as exc:
            cost = (time.perf_counter() - start) * 1000
            status = exc.response.status_code if exc.response is not None else "?"
            detail = exc.response.text[:500] if exc.response is not None else str(exc)
            log_llm_error(self._model, f"HTTP {status}: {detail}", cost_ms=cost)
            # 429 -> 限流；其它按通用 embedding 失败
            code = ErrorCode.LLM_RATE_LIMIT if status == 429 else ErrorCode.EMBEDDING_ERROR
            raise EmbeddingError(f"embedding request failed: HTTP {status}", error_code=code)
        except httpx.HTTPError as exc:
            cost = (time.perf_counter() - start) * 1000
            log_llm_error(self._model, exc, cost_ms=cost)
            raise EmbeddingError(f"embedding request error: {exc}")

        cost = (time.perf_counter() - start) * 1000
        try:
            # Preserve input order (OpenAI returns an "index" per item).
            items = sorted(body["data"], key=lambda d: d["index"])
            vectors = [item["embedding"] for item in items]
        except (KeyError, TypeError) as exc:
            log_llm_error(self._model, f"bad response shape: {exc}", cost_ms=cost)
            raise EmbeddingError(
                f"unexpected embedding response shape: {exc}",
                error_code=ErrorCode.LLM_NO_RESPONSE,
            )

        if len(vectors) != len(texts):
            log_llm_error(self._model, "embedding count mismatch", cost_ms=cost)
            raise EmbeddingError(
                "embedding count does not match input count",
                error_code=ErrorCode.LLM_NO_RESPONSE,
            )

        # LLM 交互日志：响应
        log_llm_response(
            self._model,
            f"vectors={len(vectors)}",
            cost_ms=cost,
            dim=len(vectors[0]) if vectors else 0,
        )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]
