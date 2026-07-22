"""提问语义优化：QueryProcessResult / noop / synonym / llm_rewrite / pipeline。"""
import pytest

from app.core.exceptions import LLMProviderError
from app.providers.query.base import QueryProcessResult
from app.providers.query.llm_rewrite import LLMRewriteProcessor
from app.providers.query.noop import NoopProcessor
from app.providers.query.pipeline import QueryPipeline
from app.providers.query.synonym_expander import SynonymExpander

_SYN = {
    "synonyms": [
        {"terms": ["背调"], "expand": ["背景调查", "标准问题清单"]},
        {"terms": ["薪酬", "薪资"], "expand": ["职级", "薪酬定级"]},
    ]
}


class _FakeLLM:
    def __init__(self, ret=None, exc=None):
        self._ret, self._exc = ret, exc
        self.calls = []

    async def chat_json(self, *, system_prompt, user_payload, temperature=0.0, timeout_seconds=None):
        self.calls.append(user_payload)
        if self._exc:
            raise self._exc
        return self._ret


# ---- base / noop ----

def test_result_from_raw_initializes_all_stages():
    r = QueryProcessResult.from_raw("背调要问啥")
    assert r.raw_query == "背调要问啥"
    assert r.effective_query == "背调要问啥"
    assert r.search_query == "背调要问啥"
    assert r.strategy == "noop"
    assert r.degraded is False
    assert r.synonym_applied is False
    assert r.synonym_expansions == []


async def test_noop_processor_is_passthrough():
    r = QueryProcessResult.from_raw("hi")
    out = await NoopProcessor().process(r, kb_name="k", kb_description=None, kb_settings={})
    assert out.effective_query == "hi"
    assert out.search_query == "hi"
    assert out.strategy == "noop"


# ---- synonym ----

async def test_synonym_hit_appends_dedup_expansions():
    r = QueryProcessResult.from_raw("背调要问啥")
    out = await SynonymExpander().process(r, kb_name="hr", kb_description=None, kb_settings=_SYN)
    assert out.synonym_applied is True
    assert out.synonym_expansions == ["背景调查", "标准问题清单"]
    assert out.search_query == "背调要问啥 背景调查 标准问题清单"


async def test_synonym_multi_group_dedup_and_english_case_insensitive():
    settings = {"synonyms": [
        {"terms": ["KPI"], "expand": ["考核", "指标"]},
        {"terms": ["okr"], "expand": ["指标", "目标"]},
    ]}
    r = QueryProcessResult.from_raw("聊聊 kpi 和 OKR")
    out = await SynonymExpander().process(r, kb_name="hr", kb_description=None, kb_settings=settings)
    assert out.synonym_applied is True
    assert out.synonym_expansions == ["考核", "指标", "目标"]


async def test_synonym_miss_keeps_effective_query():
    r = QueryProcessResult.from_raw("今天天气")
    out = await SynonymExpander().process(r, kb_name="hr", kb_description=None, kb_settings=_SYN)
    assert out.synonym_applied is False
    assert out.search_query == "今天天气"


async def test_synonym_no_settings_is_noop():
    r = QueryProcessResult.from_raw("背调要问啥")
    out = await SynonymExpander().process(r, kb_name="hr", kb_description=None, kb_settings={})
    assert out.synonym_applied is False
    assert out.search_query == "背调要问啥"


# ---- llm_rewrite ----

async def test_rewrite_success_sets_effective_query():
    llm = _FakeLLM(ret={"rewritten_query": "背景调查标准问题有哪些"})
    r = QueryProcessResult.from_raw("背调要问啥")
    out = await LLMRewriteProcessor(llm).process(r, kb_name="HR库", kb_description="招聘制度", kb_settings={})
    assert out.effective_query == "背景调查标准问题有哪些"
    assert out.strategy == "rewrite"
    assert out.degraded is False
    assert llm.calls[0]["kb_description"] == "招聘制度"


async def test_rewrite_uses_rewrite_hint():
    llm = _FakeLLM(ret={"rewritten_query": "x"})
    r = QueryProcessResult.from_raw("q")
    await LLMRewriteProcessor(llm).process(
        r, kb_name="k", kb_description="领域说明", kb_settings={"rewrite_hint": "SB=背调"}
    )
    assert llm.calls[0]["kb_description"] == "领域说明\nSB=背调"


async def test_rewrite_degrades_on_error():
    llm = _FakeLLM(exc=LLMProviderError("boom"))
    r = QueryProcessResult.from_raw("背调要问啥")
    out = await LLMRewriteProcessor(llm).process(r, kb_name="k", kb_description=None, kb_settings={})
    assert out.effective_query == "背调要问啥"
    assert out.degraded is True
    assert out.degraded_reason


async def test_rewrite_degrades_on_empty():
    llm = _FakeLLM(ret={"rewritten_query": "  "})
    r = QueryProcessResult.from_raw("背调要问啥")
    out = await LLMRewriteProcessor(llm).process(r, kb_name="k", kb_description=None, kb_settings={})
    assert out.effective_query == "背调要问啥"
    assert out.degraded is True


# ---- pipeline ----

async def test_pipeline_rewrite_off_synonym_still_runs():
    llm = _FakeLLM(ret={"rewritten_query": "SHOULD_NOT_BE_USED"})
    p = QueryPipeline(llm)
    out = await p.run("背调要问啥", rewrite_enabled=False, kb_name="hr", kb_description=None, kb_settings=_SYN)
    assert out.effective_query == "背调要问啥"
    assert out.strategy == "noop"
    assert out.synonym_applied is True
    assert "背景调查" in out.search_query
    assert llm.calls == []


async def test_pipeline_rewrite_on_then_synonym():
    llm = _FakeLLM(ret={"rewritten_query": "背调标准问题"})
    p = QueryPipeline(llm)
    out = await p.run("背调要问啥", rewrite_enabled=True, kb_name="hr", kb_description="招聘", kb_settings=_SYN)
    assert out.effective_query == "背调标准问题"
    assert out.synonym_applied is True
    assert out.search_query.startswith("背调标准问题 ")
