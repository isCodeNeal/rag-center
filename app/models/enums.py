"""Document / retrieval status enums shared across models and schemas."""
from __future__ import annotations

from enum import IntEnum


class DocumentStatus(IntEnum):
    """Document indexing status (integer enum stored in DB and returned via API)."""

    SUCCESS = 1
    FAILED = 2
    PROCESSING = 3  # reserved for future async indexing
