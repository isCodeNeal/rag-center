"""RAGAS 批量检索评测脚本。

用法：
    python scripts/run_retrieval_eval.py \\
        --dataset eval/datasets/ecommerce_retrieval.json \\
        --api-key rk_live_你的key \\
        --profile balanced \\
        --output eval/reports/balanced.json

评测指标：context_precision 和 context_recall（均为检索向指标，不需要生成答案）。
ground_truth 为空的 case 自动跳过，终端打印 skipped 数量。
user_id 固定 eval_runner，可在 Langfuse 里区分评测流量和线上流量。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx


def retrieve_chunks(
    *,
    base_url: str,
    api_key: str,
    kb_id: str,
    question: str,
    profile: str,
) -> list[str]:
    """调 /api/v1/rag/retrieve，返回 chunk 正文列表。"""
    url = f"{base_url.rstrip('/')}/api/v1/rag/retrieve"
    payload = {
        "kb_id": kb_id,
        "user_id": "eval_runner",
        "query": question,
        "profile": profile,
    }
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
            trust_env=False,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(f"API error code={body.get('code')}: {body.get('msg')}")
        chunks = body["data"]["retrieved_chunks"]
        return [c["content"] for c in chunks if c.get("content")]
    except Exception as e:  # noqa: BLE001
        print(f"  [WARN] retrieve 失败：{e}", file=sys.stderr)
        return []


def run_eval(
    *,
    dataset_path: str,
    api_key: str,
    base_url: str,
    profile: str,
    output_path: str | None,
) -> None:
    ds_file = Path(dataset_path)
    if not ds_file.exists():
        print(f"[ERROR] dataset 文件不存在：{dataset_path}", file=sys.stderr)
        sys.exit(1)

    with ds_file.open(encoding="utf-8") as f:
        dataset = json.load(f)

    kb_id: str = dataset.get("kb_id", "")
    effective_profile = profile or dataset.get("default_profile", "balanced")
    cases = dataset.get("cases", [])

    # 过滤掉没有 ground_truth 的 case
    runnable = [c for c in cases if c.get("ground_truth")]
    skipped = len(cases) - len(runnable)
    if skipped:
        print(f"[INFO] 跳过 {skipped} 条 case（ground_truth 为空），剩余 {len(runnable)} 条。")

    if not runnable:
        print("[WARN] 没有可评测的 case，请先补充 ground_truth。")
        return

    # 批量 retrieve
    print(f"[INFO] 开始评测：dataset={dataset_path} | profile={effective_profile} | cases={len(runnable)}")
    samples: list[dict] = []
    for case in runnable:
        q = case["question"]
        gt = case["ground_truth"]
        print(f"  ↳ {q[:60]}…")
        contexts = retrieve_chunks(
            base_url=base_url,
            api_key=api_key,
            kb_id=kb_id,
            question=q,
            profile=effective_profile,
        )
        samples.append({
            "question": q,
            "answer": "",  # rag-center 不生成答案
            "contexts": contexts,
            "ground_truth": gt,
        })

    # RAGAS 评测
    try:
        from datasets import Dataset  # type: ignore
        from ragas import evaluate  # type: ignore
        from ragas.metrics import context_precision, context_recall  # type: ignore
    except ImportError:
        print(
            "[ERROR] 缺少 ragas/datasets 依赖，请先安装：pip install -e '.[eval]'",
            file=sys.stderr,
        )
        sys.exit(1)

    hf_dataset = Dataset.from_list(samples)
    result = evaluate(
        dataset=hf_dataset,
        metrics=[context_precision, context_recall],
    )

    scores = result.to_pandas()[["context_precision", "context_recall"]].to_dict(orient="records")

    # 汇总
    avg_cp = sum(s.get("context_precision", 0) or 0 for s in scores) / len(scores)
    avg_cr = sum(s.get("context_recall", 0) or 0 for s in scores) / len(scores)
    print(f"\n[结果] context_precision={avg_cp:.4f}  context_recall={avg_cr:.4f}")

    # 低召回 case 单独列出
    low_recall = [
        (runnable[i]["question"], s.get("context_recall", 0))
        for i, s in enumerate(scores)
        if (s.get("context_recall") or 0) < 0.5
    ]
    if low_recall:
        print("\n[低召回 case]")
        for q, cr in sorted(low_recall, key=lambda x: x[1]):
            print(f"  recall={cr:.2f}  {q[:80]}")

    # 写报告
    if output_path:
        report = {
            "dataset": dataset_path,
            "profile": effective_profile,
            "summary": {"context_precision": avg_cp, "context_recall": avg_cr},
            "details": [
                {
                    "id": runnable[i].get("id"),
                    "question": runnable[i]["question"],
                    "context_precision": scores[i].get("context_precision"),
                    "context_recall": scores[i].get("context_recall"),
                }
                for i in range(len(runnable))
            ],
        }
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[INFO] 报告已写入 {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAGAS 批量检索评测")
    parser.add_argument("--dataset", required=True, help="golden set JSON 路径")
    parser.add_argument("--api-key", required=True, help="rag-center API Key")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="服务地址")
    parser.add_argument("--profile", default=None, help="检索策略（覆盖 dataset 默认值）")
    parser.add_argument("--output", default=None, help="报告输出路径")
    args = parser.parse_args()

    run_eval(
        dataset_path=args.dataset,
        api_key=args.api_key,
        base_url=args.base_url,
        profile=args.profile,
        output_path=args.output,
    )
