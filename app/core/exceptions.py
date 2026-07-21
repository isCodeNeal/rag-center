"""统一异常体系。

设计要点：
- 一个统一异常基类 `AppException`，携带 `ErrorCode`（对外 code + msg）与 `detail`（对内上下文）。
- `msg` 用于返回给调用方（安全、简洁）；`detail` 只进日志，不对外暴露。
- 提供快速抛错工具函数 `raise_error(...)`，以及若干语义化子类，业务层直接抛。
- `BizError` 作为 `AppException` 的兼容别名保留。
"""
from __future__ import annotations

from typing import Any, NoReturn

from app.core.error_codes import ErrorCode


class AppException(Exception):
    """所有可预期业务异常的基类。"""

    def __init__(
        self,
        error_code: ErrorCode = ErrorCode.SERVER_ERROR,
        *,
        msg: str | None = None,
        detail: Any = None,
    ):
        self.error_code = error_code
        self.code = error_code.code
        # 对外提示：默认用错误码自带的安全文案，允许覆盖。
        self.msg = msg or error_code.msg
        # 对内细节：仅用于日志排查，不返回给调用方。
        self.detail = detail
        super().__init__(self.detail if self.detail is not None else self.msg)


# 兼容别名：历史代码以 BizError 作为业务异常基类。
BizError = AppException


def raise_error(
    error_code: ErrorCode,
    *,
    msg: str | None = None,
    detail: Any = None,
) -> NoReturn:
    """快速抛错工具函数：raise_error(ErrorCode.KB_NOT_FOUND, detail=f"kb_id={kb_id}")。"""
    raise AppException(error_code, msg=msg, detail=detail)


# ---- 语义化子类（业务层直接抛，可读性更好）----
class KnowledgeBaseNotFound(AppException):
    def __init__(self, kb_id: str | None = None):
        super().__init__(ErrorCode.KB_NOT_FOUND, detail=f"kb_id={kb_id}" if kb_id else None)


class DocumentNotFound(AppException):
    def __init__(self, document_id: str | None = None):
        super().__init__(
            ErrorCode.DOCUMENT_NOT_FOUND,
            detail=f"document_id={document_id}" if document_id else None,
        )


class UnsupportedSourceType(AppException):
    def __init__(self, detail: str | None = None):
        super().__init__(ErrorCode.UNSUPPORTED_SOURCE_TYPE, detail=detail)


class EmbeddingError(AppException):
    def __init__(self, detail: str | None = None, *, error_code: ErrorCode = ErrorCode.EMBEDDING_ERROR):
        super().__init__(error_code, detail=detail)


class VectorStoreError(AppException):
    def __init__(self, detail: str | None = None):
        super().__init__(ErrorCode.VECTOR_STORE_ERROR, detail=detail)


class IndexingError(AppException):
    def __init__(self, detail: str | None = None):
        super().__init__(ErrorCode.INDEXING_ERROR, detail=detail)


class LLMProviderError(AppException):
    """通用大模型调用异常（LLMProvider 实现统一抛出这个类型）。

    覆盖调用失败、超时、返回内容不是合法 JSON 等场景。RerankProvider 等上层
    捕获这个异常做降级处理，而不是让整个请求失败。
    """

    def __init__(self, detail: str | None = None, *, error_code: ErrorCode = ErrorCode.LLM_ERROR):
        super().__init__(error_code, detail=detail)


class RerankError(AppException):
    """重排调用异常。仅用于内部识别/日志，RagService 会捕获它并降级为原向量排序。"""

    def __init__(self, detail: str | None = None):
        super().__init__(ErrorCode.RERANK_ERROR, detail=detail)


class KeywordSearchError(AppException):
    """关键词检索（Elasticsearch BM25）异常。

    hybrid 模式下若 BM25 检索失败，RagService 捕获此异常并降级为纯向量结果，
    而不是让整个检索接口失败。
    """

    def __init__(self, detail: str | None = None):
        super().__init__(ErrorCode.KEYWORD_SEARCH_ERROR, detail=detail)
