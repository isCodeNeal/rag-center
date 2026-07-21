"""知识库树形 schema 单元测试。"""
from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.knowledge_base import (
    KnowledgeTreeDoc,
    KnowledgeTreeKb,
    KnowledgeTreeTenant,
)


def test_tree_schema_nests_tenant_kb_doc():
    doc = KnowledgeTreeDoc(
        document_id="doc-1",
        title="backend_engineer.md",
        status=1,
        chunk_count=12,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    kb = KnowledgeTreeKb(
        kb_id="kb-1",
        name="技术岗位知识库",
        description="d",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        documents=[doc],
    )
    tenant = KnowledgeTreeTenant(tenant_id="tech_position", knowledge_bases=[kb])
    assert tenant.knowledge_bases[0].documents[0].chunk_count == 12
    assert tenant.knowledge_bases[0].description == "d"
