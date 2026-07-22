"""Markdown 结构化切块器测试。"""
import pytest

from app.utils.markdown_splitter import MarkdownStructuredSplitter


def test_h1_h2_split():
    """测试 # 和 ## 标题正确分节，不会在标题行中间截断。"""
    doc = """# 一级标题
一级内容段落。

## 二级标题
二级内容段落。

# 另一个一级
另一个内容。"""

    splitter = MarkdownStructuredSplitter(chunk_size=500, chunk_overlap=50)
    pieces = splitter.split(doc)

    # 应该有3个section（两个H1各自成节，H2也成节）
    assert len(pieces) == 3
    assert all(p.metadata["chunk_type"] == "section" for p in pieces)

    # 检查heading_path
    assert pieces[0].metadata["heading_path"] == "一级标题"
    assert "一级内容段落" in pieces[0].text

    assert pieces[1].metadata["heading_path"] == "一级标题/二级标题"
    assert "二级内容段落" in pieces[1].text

    assert pieces[2].metadata["heading_path"] == "另一个一级"
    assert "另一个内容" in pieces[2].text


def test_h3_merged_into_h2():
    """测试 ### 及更深标题归入所属 ## 节，不单独成块。"""
    doc = """## 二级标题
二级段落。

### 三级标题
三级内容。

#### 四级标题
四级内容。"""

    splitter = MarkdownStructuredSplitter(chunk_size=800, chunk_overlap=50)
    pieces = splitter.split(doc)

    # 只有1个section，包含所有内容
    assert len(pieces) == 1
    assert pieces[0].metadata["heading_path"] == "二级标题"
    assert pieces[0].metadata["chunk_type"] == "section"

    # 正文应包含所有段落（包括 ### 和 #### 标题行）
    text = pieces[0].text
    assert "二级段落" in text
    assert "### 三级标题" in text
    assert "三级内容" in text
    assert "#### 四级标题" in text
    assert "四级内容" in text


def test_standalone_dash_filtered():
    """测试独立 --- 行被过滤，不出现在任何 chunk 正文中。"""
    doc = """# 标题一
段落1。

---

段落2。

---

## 标题二

---

段落3。"""

    splitter = MarkdownStructuredSplitter(chunk_size=500, chunk_overlap=50)
    pieces = splitter.split(doc)

    # 检查所有chunk的正文都不包含独立的 ---
    for piece in pieces:
        lines = piece.text.split("\n")
        for line in lines:
            # 允许表格分隔符（含|），但不允许独立的 ---
            if line.strip() == "---":
                pytest.fail(f"Found standalone --- in chunk: {piece.text}")


def test_long_section_secondary_split():
    """测试长节内二次切，同节各 chunk 的 heading_path 一致。"""
    # 构造一个超长的二级节
    long_para = "这是一个很长的段落。" * 50  # ~500字符
    doc = f"""# 一级
## 二级

{long_para}

另一段。

{long_para}

最后一段。"""

    splitter = MarkdownStructuredSplitter(chunk_size=300, chunk_overlap=50)
    pieces = splitter.split(doc)

    # 一级节为空，只有二级节有内容；二级节会被二次切分
    h2_pieces = [p for p in pieces if "二级" in p.metadata.get("heading_path", "")]
    assert len(h2_pieces) > 1, "长节应该被二次切分"

    # 所有子块的 heading_path 应该一致
    paths = {p.metadata["heading_path"] for p in h2_pieces}
    assert len(paths) == 1
    assert paths.pop() == "一级/二级"


def test_no_heading_doc():
    """测试无标题文档退化为接近旧行为（字符切）。"""
    doc = "这是一段没有任何标题的文档。" * 100  # 超过 chunk_size

    splitter = MarkdownStructuredSplitter(chunk_size=200, chunk_overlap=50)
    pieces = splitter.split(doc)

    # 应该有多个chunk
    assert len(pieces) > 1

    # 所有chunk的 heading_path 应该为空
    assert all(p.metadata.get("heading_path") == "" for p in pieces)
    assert all(p.metadata["chunk_type"] == "section" for p in pieces)


def test_small_table_single_chunk():
    """测试小表整表一个 chunk，chunk_type=table，无 table_part。"""
    doc = """# 标题

| 列1 | 列2 | 列3 |
|-----|-----|-----|
| A   | B   | C   |
| D   | E   | F   |

段落。"""

    splitter = MarkdownStructuredSplitter(chunk_size=500, chunk_overlap=50)
    pieces = splitter.split(doc)

    # 应该有2个chunk：表格 + 段落
    assert len(pieces) >= 2

    table_pieces = [p for p in pieces if p.metadata["chunk_type"] == "table"]
    assert len(table_pieces) == 1

    table = table_pieces[0]
    assert "列1" in table.text
    assert "| A" in table.text or "|A" in table.text or "A   |" in table.text
    assert table.metadata["heading_path"] == "标题"
    assert "table_part" not in table.metadata  # 小表无 table_part


def test_large_table_split_with_header():
    """测试大表分组，每组含完整表头，table_part 递增。"""
    # 构造一个有很多数据行的表格
    header = "| 姓名 | 年龄 | 城市 |\n|------|------|------|\n"
    data_rows = "\n".join([f"| 用户{i} | {20+i} | 城市{i} |" for i in range(25)])

    doc = f"""# 用户列表

{header}{data_rows}

段落。"""

    splitter = MarkdownStructuredSplitter(
        chunk_size=300,  # 小 chunk_size 确保表格被拆分
        chunk_overlap=50,
        table_max_rows=5,
    )
    pieces = splitter.split(doc)

    table_pieces = [p for p in pieces if p.metadata["chunk_type"] == "table"]

    # 25行数据，每组5行 → 应该有5个表格chunk
    assert len(table_pieces) == 5

    # 每个chunk都应该有 table_part，从1开始递增
    parts = [p.metadata["table_part"] for p in table_pieces]
    assert parts == [1, 2, 3, 4, 5]

    # 每个chunk顶部都应该有【表头】
    for piece in table_pieces:
        assert "【表头】" in piece.text
        assert "姓名 | 年龄 | 城市" in piece.text


def test_mixed_document():
    """测试混合文档：标题 + 段落 + 表格 + 段落，各类型正确分开。"""
    doc = """# 主标题
这是第一段。

## 子标题
这是第二段。

| 产品 | 价格 |
|------|------|
| A    | 100  |
| B    | 200  |

这是表格后的段落。

---

### 三级标题
三级内容。

```python
def hello():
    print("world")
```

代码后的段落。"""

    splitter = MarkdownStructuredSplitter(chunk_size=500, chunk_overlap=50)
    pieces = splitter.split(doc)

    # 检查chunk类型分布
    section_pieces = [p for p in pieces if p.metadata["chunk_type"] == "section"]
    table_pieces = [p for p in pieces if p.metadata["chunk_type"] == "table"]

    assert len(table_pieces) == 1
    assert len(section_pieces) >= 2

    # 检查表格chunk
    table = table_pieces[0]
    assert "产品" in table.text
    assert "价格" in table.text

    # 检查 --- 未出现在任何正文中
    for piece in pieces:
        lines = [line.strip() for line in piece.text.split("\n")]
        assert "---" not in lines, "独立 --- 不应该出现在正文中"

    # 检查代码块被完整保留在某个section中
    code_pieces = [p for p in section_pieces if "```python" in p.text]
    assert len(code_pieces) >= 1
    assert "def hello():" in code_pieces[0].text
    assert 'print("world")' in code_pieces[0].text

    # 检查三级标题归入了二级节
    h3_pieces = [p for p in section_pieces if "### 三级标题" in p.text]
    assert len(h3_pieces) >= 1
    assert "子标题" in h3_pieces[0].metadata["heading_path"]
