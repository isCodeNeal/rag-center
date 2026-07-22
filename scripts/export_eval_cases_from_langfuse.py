"""从 Langfuse 导出低分 case 到 eval dataset。

用法：
    # 导出为独立文件（待人工补 ground_truth）
    python scripts/export_eval_cases_from_langfuse.py \\
        --max-score 3 --days 30 --kb-id 939a5baf-xxxx \\
        --output eval/datasets/imported_from_feedback.json

    # 审完 ground_truth 后合并进主集
    python scripts/export_eval_cases_from_langfuse.py \\
        --max-score 3 \\
        --merge eval/datasets/ecommerce_retrieval.json \\
        --output eval/datasets/ecommerce_retrieval.json

导出格式：question 和 source 有值，ground_truth 默认留空，等待人工填写。
已有 ground_truth 的 case 在 --merge 模式下不覆盖。
httpx 访问 Langfuse 时关闭系统代理（trust_env=False），避免 localhost 502。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from dotenv import load_dotenv  # type: ignore
import os

load_dotenv()


def _langfuse_get(client: httpx.Client, host: str, path: str, **params) -> dict:
    url = f"{host.rstrip('/')}{path}"
    resp = client.get(url, params={k: v for k, v in params.items() if v is not None})
    resp.raise_for_status()
    return resp.json()


def export_cases(
    *,
    host: str,
    public_key: str,
    secret_key: str,
    max_score: float,
    days: int | None,
    kb_id: str | None,
    output: str,
    merge_path: str | None,
) -> None:
    client = httpx.Client(
        auth=(public_key, secret_key),
        trust_env=False,
        timeout=30,
    )

    # 拉 user_feedback score 列表
    params: dict = {"name": "user_feedback"}
    if days is not None:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        params["fromTimestamp"] = since

    try:
        scores_resp = _langfuse_get(client, host, "/api/public/scores", **params)
    except httpx.HTTPError as e:
        print(f"[ERROR] Langfuse 不可用：{e}", file=sys.stderr)
        sys.exit(1)

    raw_scores = scores_resp.get("data", [])
    low_scores = [s for s in raw_scores if (s.get("value") or 999) < max_score]

    if not low_scores:
        print("[INFO] 没有低于阈值的反馈记录。")
        return

    # 按 trace_id 拉 trace 详情
    cases: list[dict] = []
    for score_item in low_scores:
        trace_id = score_item.get("traceId")
        if not trace_id:
            continue
        try:
            trace = _langfuse_get(client, host, f"/api/public/traces/{trace_id}")
        except httpx.HTTPError:
            continue

        meta = trace.get("metadata") or {}
        this_kb_id = meta.get("kb_id", "")
        if kb_id and this_kb_id != kb_id:
            continue

        question = (trace.get("input") or {}).get("query") or ""
        if not question:
            # 从 trace input 顶层尝试
            question = str(trace.get("input", "")) if isinstance(trace.get("input"), str) else ""

        case = {
            "id": f"lf_{trace_id[:8]}",
            "question": question,
            "ground_truth": "",  # 待人工填写
            "source": {
                "trace_id": trace_id,
                "feedback_score": score_item.get("value"),
                "feedback_comment": score_item.get("comment"),
            },
        }
        cases.append(case)

    # 加载现有数据集（merge 模式）
    existing_dataset: dict = {}
    if merge_path:
        merge_file = Path(merge_path)
        if merge_file.exists():
            with merge_file.open(encoding="utf-8") as f:
                existing_dataset = json.load(f)
        existing_cases: list[dict] = existing_dataset.get("cases", [])
        existing_questions = {c["question"] for c in existing_cases}
        # 去重：已有 question 的 case 不覆盖
        new_cases = [c for c in cases if c["question"] not in existing_questions]
        existing_cases.extend(new_cases)
        existing_dataset["cases"] = existing_cases
        output_data = existing_dataset
    else:
        this_kb = kb_id or (cases[0]["source"]["trace_id"][:8] if cases else "unknown")
        output_data = {
            "name": f"imported_from_feedback_{this_kb}",
            "kb_id": kb_id or "",
            "default_profile": "balanced",
            "cases": cases,
        }

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    pending = sum(1 for c in output_data["cases"] if not c.get("ground_truth"))
    total = len(output_data["cases"])
    print(f"[OK] 导出 {len(cases)} 条 → {output}（共 {total} 条，待补 ground_truth: {pending} 条）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 Langfuse 导出低分 case 到 eval dataset")
    parser.add_argument("--max-score", type=float, default=3, help="导出分值低于该值的 case（默认 3）")
    parser.add_argument("--days", type=int, default=None, help="只看最近 N 天")
    parser.add_argument("--kb-id", default=None, help="只导出指定知识库")
    parser.add_argument("--output", required=True, help="输出文件路径")
    parser.add_argument("--merge", default=None, help="合并目标 dataset，追加而非覆盖")
    args = parser.parse_args()

    host = os.getenv("LANGFUSE_HOST", "http://localhost:3000")
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sk = os.getenv("LANGFUSE_SECRET_KEY", "")
    if not pk or not sk:
        print("[ERROR] 请配置 LANGFUSE_PUBLIC_KEY 和 LANGFUSE_SECRET_KEY", file=sys.stderr)
        sys.exit(1)

    export_cases(
        host=host,
        public_key=pk,
        secret_key=sk,
        max_score=args.max_score,
        days=args.days,
        kb_id=args.kb_id,
        output=args.output,
        merge_path=args.merge,
    )
