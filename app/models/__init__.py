"""ORM 模型。

在此处导入所有模型，确保它们都注册到 ``Base.metadata`` 上，
供 Alembic autogenerate 和 metadata.create_all() 使用。
"""
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.retrieval_log import RetrievalLog

__all__ = [
    "Chunk",
    "Document",
    "DocumentStatus",
    "KnowledgeBase",
    "RetrievalLog",
]
