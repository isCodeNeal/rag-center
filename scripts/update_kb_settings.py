"""维护知识库的 settings（词表 synonyms + 可选 rewrite_hint）：

    python scripts/update_kb_settings.py --kb-id <kb_id> --settings-file kb_settings.json

注意：整文件覆盖 knowledge_bases.settings 字段（不是增量合并）。
参见 examples/kb_settings.example.json 了解结构。
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.db.session import SessionLocal
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository


async def _main(kb_id: str, settings_file: str) -> None:
    with open(settings_file, "r", encoding="utf-8") as f:
        settings = json.load(f)
    if not isinstance(settings, dict):
        raise SystemExit("settings 文件顶层必须是一个 JSON 对象")

    async with SessionLocal() as session:
        repo = KnowledgeBaseRepository(session)
        if await repo.get(kb_id) is None:
            raise SystemExit(f"知识库不存在：{kb_id}")
        # 整文件覆盖，而非增量合并
        await repo.update_settings(kb_id, settings)
        await session.commit()

    synonyms = settings.get("synonyms", [])
    print("知识库 settings 已更新（整文件覆盖）：")
    print(f"  kb_id       : {kb_id}")
    print(f"  synonyms 组数: {len(synonyms) if isinstance(synonyms, list) else 0}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="覆盖式更新知识库 settings")
    parser.add_argument("--kb-id", required=True, help="已存在的知识库 id")
    parser.add_argument(
        "--settings-file", required=True, help="settings JSON 文件路径（整文件覆盖）"
    )
    args = parser.parse_args()
    asyncio.run(_main(args.kb_id, args.settings_file))
