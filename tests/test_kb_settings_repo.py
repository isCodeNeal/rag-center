"""knowledge_bases.settings 字段的默认值与模型行为。

仓库暂无异步 DB fixture，故这里只覆盖 model 层默认值；
update_settings 的行为在 tests/test_rag_service.py 的集成路径中间接覆盖。
"""
from app.models.knowledge_base import KnowledgeBase


def test_kb_settings_can_hold_synonyms():
    kb = KnowledgeBase(
        id="kb-x",
        tenant_id="t1",
        name="n",
        description=None,
        settings={"synonyms": [{"terms": ["背调"], "expand": ["背景调查"]}]},
    )
    assert kb.settings["synonyms"][0]["terms"] == ["背调"]


def test_kb_settings_accepts_empty_dict():
    kb = KnowledgeBase(id="kb-y", tenant_id="t1", name="n", description=None, settings={})
    assert kb.settings == {}
