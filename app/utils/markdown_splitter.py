"""Markdown 结构化切块器。

按标题分节（# / ##），识别表格专项切，支持单节二次字符切。
heading_path 记录节的层级路径（如 "平台交易规则/退款时效"）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SplitPiece:
    text: str
    metadata: dict = field(default_factory=dict)


class MarkdownStructuredSplitter:
    """按 Markdown 结构切分文档。

    分节规则：
    - # / ## 触发 flush 当前节，开启新节
    - ### 及以下归入当前节正文
    - 独立 --- 行跳过
    - 代码块 ``` 整块保留，不从中截断
    - 表格 | 行专项切（小表整块，大表按 table_max_rows 分组）
    - 节正文超过 chunk_size 时按段落优先、字符兜底二次切
    """

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        table_max_rows: int = 10,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be in [0, chunk_size)")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.table_max_rows = table_max_rows

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def split(self, text: str) -> list[SplitPiece]:
        text = (text or "").strip()
        if not text:
            return []

        pieces: list[SplitPiece] = []
        lines = text.splitlines()

        heading_stack: list[str] = []
        section_lines: list[str] = []
        table_buffer: list[str] = []
        in_code_fence = False

        def current_path() -> str:
            return "/".join(heading_stack) if heading_stack else ""

        def flush_section() -> None:
            nonlocal section_lines
            body = "\n".join(section_lines).strip()
            section_lines = []
            if not body:
                return
            pieces.extend(self._split_section(body, current_path()))

        def flush_table() -> None:
            nonlocal table_buffer
            buf = list(table_buffer)
            table_buffer = []
            if not buf:
                return
            pieces.extend(self._split_table(buf, current_path()))

        for raw_line in lines:
            line = raw_line.rstrip()

            # ---- code fence toggle ----------------------------------------
            if line.strip().startswith("```"):
                if in_code_fence:
                    # closing fence
                    section_lines.append(line)
                    in_code_fence = False
                else:
                    # opening fence — flush pending table first
                    if table_buffer:
                        flush_table()
                    in_code_fence = True
                    section_lines.append(line)
                continue

            if in_code_fence:
                section_lines.append(line)
                continue

            # ---- table line -----------------------------------------------
            if self._is_table_line(line):
                # flush preceding section text so table stands alone
                if section_lines:
                    flush_section()
                table_buffer.append(line)
                continue

            # non-table: flush pending table
            if table_buffer:
                flush_table()

            # ---- standalone --- (horizontal rule) -------------------------
            if re.fullmatch(r'\s*-{3,}\s*', line):
                continue

            # ---- heading --------------------------------------------------
            h_match = re.match(r'^(#{1,6})\s+(.*)', line)
            if h_match:
                level = len(h_match.group(1))
                title = h_match.group(2).strip()

                if level == 1:
                    flush_section()
                    heading_stack = [title]
                    continue

                if level == 2:
                    flush_section()
                    if heading_stack:
                        heading_stack = [heading_stack[0], title]
                    else:
                        heading_stack = [title]
                    continue

                # level >= 3:归入当前节正文
                section_lines.append(line)
                continue

            # ---- everything else (paragraphs, lists, etc.) ----------------
            section_lines.append(line)

        # flush remaining state
        if table_buffer:
            flush_table()
        if section_lines:
            flush_section()

        return pieces

    # ------------------------------------------------------------------ #
    # Private helpers                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_table_line(line: str) -> bool:
        stripped = line.strip()
        return bool(stripped) and stripped.startswith("|")

    def _split_section(self, body: str, heading_path: str) -> list[SplitPiece]:
        """单节正文切分：超长时按段落优先、字符兜底。"""
        if not body:
            return []

        meta_base = {"heading_path": heading_path, "chunk_type": "section"}

        if len(body) <= self.chunk_size:
            return [SplitPiece(text=body, metadata=dict(meta_base))]

        # 按空行拆段落，尝试合并到 chunk_size
        paragraphs = re.split(r'\n\s*\n', body)
        result: list[SplitPiece] = []
        buf = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            candidate = (buf + "\n\n" + para).strip() if buf else para
            if len(candidate) <= self.chunk_size:
                buf = candidate
            else:
                if buf:
                    result.append(SplitPiece(text=buf, metadata=dict(meta_base)))
                    buf = ""

                if len(para) <= self.chunk_size:
                    buf = para
                else:
                    # 段落本身超长 → 字符切
                    for chunk in self._char_split(para):
                        result.append(SplitPiece(text=chunk, metadata=dict(meta_base)))

        if buf:
            result.append(SplitPiece(text=buf, metadata=dict(meta_base)))

        return result

    def _split_table(self, table_lines: list[str], heading_path: str) -> list[SplitPiece]:
        """表格切分：小表整块，大表按 table_max_rows 分组并重复表头。"""
        if not table_lines:
            return []

        table_text = "\n".join(table_lines)
        meta_base = {"heading_path": heading_path, "chunk_type": "table"}

        # 找分隔行（|---|...）的索引
        sep_idx: int | None = None
        for i, line in enumerate(table_lines):
            if re.match(r'^\|[\s\-:|]+\|?\s*$', line.strip()):
                sep_idx = i
                break

        # 小表：直接返回
        if len(table_text) <= self.chunk_size:
            return [SplitPiece(text=table_text, metadata=dict(meta_base))]

        # 大表但无法解析结构，按整块返回
        if sep_idx is None or sep_idx < 1:
            return [SplitPiece(text=table_text, metadata=dict(meta_base))]

        # 解析表头文本
        header_row = table_lines[0]
        raw_cols = header_row.strip()
        if raw_cols.startswith("|"):
            raw_cols = raw_cols[1:]
        if raw_cols.endswith("|"):
            raw_cols = raw_cols[:-1]
        header_display = " | ".join(c.strip() for c in raw_cols.split("|"))

        data_rows = [r for r in table_lines[sep_idx + 1:] if r.strip()]

        result: list[SplitPiece] = []
        for chunk_idx, i in enumerate(range(0, max(1, len(data_rows)), self.table_max_rows)):
            group = data_rows[i: i + self.table_max_rows]
            part_num = chunk_idx + 1
            chunk_text = f"【表头】{header_display}\n" + "\n".join(group)
            result.append(
                SplitPiece(
                    text=chunk_text.strip(),
                    metadata={**meta_base, "table_part": part_num},
                )
            )

        return result

    def _char_split(self, text: str) -> list[str]:
        """滑动窗口字符切，带 overlap。"""
        if not text:
            return []
        step = self.chunk_size - self.chunk_overlap
        chunks: list[str] = []
        start = 0
        length = len(text)
        while start < length:
            end = start + self.chunk_size
            piece = text[start:end].strip()
            if piece:
                chunks.append(piece)
            if end >= length:
                break
            start += step
        return chunks
