"""词表扩展：纯函数逻辑，不调 LLM。

词表存在 kb.settings.synonyms，由运维脚本维护，不进平台代码。
匹配规则：中文 term 精确子串匹配；英文 term 忽略大小写。命中组的 expand
追加到 effective_query 末尾（空格分隔），多组命中去重（保持首次出现顺序）。
未命中时 search_query 等于 effective_query。词表仅对当前 kb 生效，不跨库、不跨租户。
"""
from __future__ import annotations

from app.providers.query.base import QueryProcessor, QueryProcessResult


def _term_hit(term: str, query: str) -> bool:
    # 英文 term 忽略大小写；中文精确子串。统一用 lower 比较即可覆盖两者
    # （中文 lower 无副作用）。
    return term.lower() in query.lower()


class SynonymExpander(QueryProcessor):
    async def process(
        self,
        result: QueryProcessResult,
        *,
        kb_name: str,
        kb_description: str | None,
        kb_settings: dict,
    ) -> QueryProcessResult:
        groups = (kb_settings or {}).get("synonyms") or []
        base = result.effective_query
        expansions: list[str] = []
        for group in groups:
            terms = group.get("terms") or []
            if any(_term_hit(t, base) for t in terms):
                for w in group.get("expand") or []:
                    if w not in expansions:
                        expansions.append(w)
        if expansions:
            result.synonym_applied = True
            result.synonym_expansions = expansions
            result.search_query = base + " " + " ".join(expansions)
        else:
            result.search_query = base
        return result
