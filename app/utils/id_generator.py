"""Centralized ID generation for RAG-center-internal resources.

Business-supplied identifiers (tenant_id, user_id) are NOT generated here — they are
passed in by the caller. Everything the platform owns (kb_id, document_id, chunk_id,
retrieval_log_id) gets a UUID from these helpers so generation is consistent and never
hand-rolled inside services.
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
