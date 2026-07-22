"""套餐（plan）三档定义：free / standard / pro。

配额与功能开关写死在代码里，不支持 per-tenant 覆盖。需要调整就改代码发版。
数据结构与 plan_resolver.PlanFeatures / PlanLimits 对应。
"""
from __future__ import annotations

PLAN_FREE = "free"
PLAN_STANDARD = "standard"
PLAN_PRO = "pro"

VALID_PLANS = (PLAN_FREE, PLAN_STANDARD, PLAN_PRO)

# 每档：features（功能开关）+ limits（配额上限）。
PLAN_PRESETS: dict[str, dict] = {
    PLAN_FREE: {
        "features": {
            "allowed_profiles": ["speed"],
            "hybrid_allowed": False,
            "rerank_allowed": False,
            "query_rewrite_allowed": False,
        },
        "limits": {
            "retrieve_qps": 3,
            "retrieve_daily": 500,
            "max_kb": 1,
            "max_documents_per_kb": 30,
            "max_processing_documents": 1,
        },
    },
    PLAN_STANDARD: {
        "features": {
            "allowed_profiles": ["speed", "balanced", "custom"],
            "hybrid_allowed": True,
            "rerank_allowed": False,
            "query_rewrite_allowed": False,
        },
        "limits": {
            "retrieve_qps": 10,
            "retrieve_daily": 5000,
            "max_kb": 5,
            "max_documents_per_kb": 200,
            "max_processing_documents": 2,
        },
    },
    PLAN_PRO: {
        "features": {
            "allowed_profiles": ["speed", "balanced", "quality", "custom"],
            "hybrid_allowed": True,
            "rerank_allowed": True,
            "query_rewrite_allowed": True,
        },
        "limits": {
            "retrieve_qps": 50,
            "retrieve_daily": 100000,
            "max_kb": 50,
            "max_documents_per_kb": 5000,
            "max_processing_documents": 10,
        },
    },
}
