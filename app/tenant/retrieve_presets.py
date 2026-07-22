"""检索预设（retrieve profile）四档：speed / balanced / quality / custom。

服务端按 profile 展开成具体的 retrieval_options / rerank_options / query_options。
custom 不展开默认值，直接使用请求里已有的 options（仍受 plan 约束）。
未传 profile 时服务端默认 balanced。
"""
from __future__ import annotations

PROFILE_SPEED = "speed"
PROFILE_BALANCED = "balanced"
PROFILE_QUALITY = "quality"
PROFILE_CUSTOM = "custom"

DEFAULT_PROFILE = PROFILE_BALANCED
VALID_PROFILES = (PROFILE_SPEED, PROFILE_BALANCED, PROFILE_QUALITY, PROFILE_CUSTOM)

# 每档展开成的 options bundle。custom 无 bundle（用请求里已有 options）。
RETRIEVE_PROFILE_PRESETS: dict[str, dict] = {
    PROFILE_SPEED: {
        "mode": "vector",
        "top_k": 3,
        "rerank_enabled": False,
        "query_rewrite_enabled": False,
    },
    PROFILE_BALANCED: {
        "mode": "hybrid",
        "top_k": 5,
        "rerank_enabled": False,
        "query_rewrite_enabled": False,
    },
    PROFILE_QUALITY: {
        "mode": "hybrid",
        "top_k": 8,
        "rerank_enabled": True,
        "query_rewrite_enabled": True,
    },
}
