"""PlanContext 与 resolve_plan：把租户的 plan 字符串解析成结构化的配额/功能上限。

resolve_plan 只查 PLAN_PRESETS，不涉及 Redis，也不涉及 retrieve profile 合并。
未知 plan 兜底为 free（最保守），避免脏数据放开权限。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.tenant.plan_presets import PLAN_FREE, PLAN_PRESETS


@dataclass
class PlanFeatures:
    allowed_profiles: list[str]
    hybrid_allowed: bool
    rerank_allowed: bool
    query_rewrite_allowed: bool


@dataclass
class PlanLimits:
    retrieve_qps: int
    retrieve_daily: int
    max_kb: int
    max_documents_per_kb: int
    max_processing_documents: int
    max_kb_per_retrieve: int


@dataclass
class PlanContext:
    plan: str
    features: PlanFeatures
    limits: PlanLimits


def resolve_plan(plan: str | None) -> PlanContext:
    """把 plan 字符串解析成 PlanContext。未知 plan 兜底为 free。"""
    key = plan if plan in PLAN_PRESETS else PLAN_FREE
    preset = PLAN_PRESETS[key]
    return PlanContext(
        plan=key,
        features=PlanFeatures(**preset["features"]),
        limits=PlanLimits(**preset["limits"]),
    )
