"""RAG-center 内部资源的统一 ID 生成入口。

业务方传入的标识符（tenant_id、user_id）不在这里生成 —— 它们由调用方传入。
凡是平台自身拥有的资源（kb_id、document_id、chunk_id、retrieval_log_id）都通过
这些 helper 生成 UUID，保证生成方式统一，不会在各个 service 内各写一套。
"""
from __future__ import annotations

import uuid


def _uuid() -> str:
    return str(uuid.uuid4())


def new_kb_id() -> str:
    return _uuid()


def new_document_id() -> str:
    return _uuid()


def new_chunk_id() -> str:
    return _uuid()


def new_retrieval_log_id() -> str:
    return _uuid()
