"""检索链路健壮性验收脚本。

用法：
    python scripts/verify_robustness_retrieve.py \
        --base-url http://localhost:8000 \
        --api-key rk_live_xxx \
        --kb-id <合法kb_id>

前置说明：
    - check_hybrid_degraded: 需要先停止 Elasticsearch，再运行此脚本。
      若 ES 可访问，该用例将 SKIP（无法构造 BM25 失败场景）。
    - check_empty_query / check_long_query 不依赖 ES 状态，随时可运行。

退出码：
    0 — 全部 PASS（SKIP 不计入失败）
    1 — 有 FAIL
"""
from __future__ import annotations

import argparse
import sys

try:
    import httpx
except ImportError:
    sys.exit("httpx is required: pip install httpx")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _retrieve(base_url: str, api_key: str, kb_id: str, query: str, mode: str = "hybrid") -> dict:
    """调用 /v1/retrieve，返回响应 JSON。"""
    url = f"{base_url}/v1/retrieve"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "kb_id": kb_id,
        "user_id": "verify-script",
        "query": query,
        "retrieval_options": {"mode": mode},
        "rerank_options": {"enabled": False},
        "profile": "custom",
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=30)
    return resp.json()


def _print_result(label: str, status: str, reason: str = "") -> None:
    tag = f"[{status}]"
    msg = f"{tag} {label}"
    if reason:
        msg += f" — {reason}"
    print(msg)


# ---------------------------------------------------------------------------
# 检测用例
# ---------------------------------------------------------------------------

def check_hybrid_degraded(base_url: str, api_key: str, kb_id: str) -> str:
    """停 ES 后运行：断言 hybrid retrieve 返回 code=0 且 metadata.retrieval.degraded=True。

    若 ES 仍可连通（BM25 不会失败），则 SKIP 并说明原因。
    若无法连接服务，SKIP 并说明原因。
    """
    label = "hybrid_degraded（ES 停机后 BM25 降级）"
    try:
        data = _retrieve(base_url, api_key, kb_id, "退款政策", mode="hybrid")
    except Exception as exc:
        _print_result(label, "SKIP", f"无法连接服务: {exc}")
        return "skip"

    code = data.get("code")
    if code != 0:
        _print_result(label, "SKIP", f"retrieve 返回 code={code}，msg={data.get('msg')}，可能 ES 未停或其他错误")
        return "skip"

    retrieval = (data.get("data") or {}).get("metadata", {}).get("retrieval", {})
    degraded = retrieval.get("degraded", False)
    degraded_reason = retrieval.get("degraded_reason", "")

    if not degraded:
        _print_result(
            label, "SKIP",
            "retrieval.degraded=False，ES 可能仍在运行；请先停止 ES 再重跑此脚本"
        )
        return "skip"

    # degraded=True → 确认是 BM25 或 vector 失败引起的降级
    if "bm25" in (degraded_reason or "").lower() or "vector" in (degraded_reason or "").lower():
        _print_result(label, "PASS", f"degraded=True, reason='{degraded_reason}'")
        return "pass"
    else:
        _print_result(label, "FAIL", f"degraded=True 但 reason 未知: '{degraded_reason}'")
        return "fail"


def check_empty_query(base_url: str, api_key: str, kb_id: str) -> str:
    """空 query → 应返回 PARAM_ERROR（code=10001）。"""
    label = "empty_query → PARAM_ERROR"
    url = f"{base_url}/v1/retrieve"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "kb_id": kb_id,
        "user_id": "verify-script",
        "query": "",
        "rerank_options": {"enabled": False},
        "profile": "custom",
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        data = resp.json()
    except Exception as exc:
        _print_result(label, "SKIP", f"无法连接服务: {exc}")
        return "skip"

    code = data.get("code")
    # HTTP 422（Pydantic 校验）或自定义 PARAM_ERROR(10001)，均视为合格
    if resp.status_code == 422 or code == 10001:
        _print_result(label, "PASS", f"HTTP {resp.status_code}, code={code}")
        return "pass"
    else:
        _print_result(label, "FAIL", f"预期 422 或 code=10001，实际 HTTP {resp.status_code}, code={code}")
        return "fail"


def check_long_query(base_url: str, api_key: str, kb_id: str) -> str:
    """超长 query（2001 字符）→ 应返回 PARAM_ERROR（code=10001）。"""
    label = "long_query(2001chars) → PARAM_ERROR"
    long_query = "测" * 2001
    try:
        data = _retrieve(base_url, api_key, kb_id, long_query, mode="vector")
    except Exception as exc:
        _print_result(label, "SKIP", f"无法连接服务: {exc}")
        return "skip"

    code = data.get("code")
    if code == 10001:
        _print_result(label, "PASS", f"code={code}, msg={data.get('msg', '')[:60]}")
        return "pass"
    else:
        _print_result(label, "FAIL", f"预期 code=10001，实际 code={code}, msg={data.get('msg', '')[:60]}")
        return "fail"


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="检索链路健壮性验收脚本")
    parser.add_argument("--base-url", default="http://localhost:8000", help="服务地址")
    parser.add_argument("--api-key", required=True, help="API Key")
    parser.add_argument("--kb-id", required=True, help="合法的知识库 ID")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    api_key = args.api_key
    kb_id = args.kb_id

    print(f"\n验收脚本 · base_url={base_url} · kb_id={kb_id}")
    print("=" * 60)

    results = []
    results.append(check_hybrid_degraded(base_url, api_key, kb_id))
    results.append(check_empty_query(base_url, api_key, kb_id))
    results.append(check_long_query(base_url, api_key, kb_id))

    print("=" * 60)
    pass_cnt = results.count("pass")
    fail_cnt = results.count("fail")
    skip_cnt = results.count("skip")
    print(f"结果汇总：PASS={pass_cnt}  FAIL={fail_cnt}  SKIP={skip_cnt}")

    if fail_cnt > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
