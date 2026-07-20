from app.utils.text_splitter import CharacterTextSplitter


def test_split_empty_returns_no_chunks():
    splitter = CharacterTextSplitter(chunk_size=100, chunk_overlap=10)
    assert splitter.split("") == []
    assert splitter.split("   \n  ") == []


def test_split_short_text_single_chunk():
    splitter = CharacterTextSplitter(chunk_size=100, chunk_overlap=10)
    chunks = splitter.split("hello world")
    assert chunks == ["hello world"]


def test_split_respects_size_and_overlap():
    splitter = CharacterTextSplitter(chunk_size=10, chunk_overlap=2)
    text = "abcdefghij" * 3  # 共 30 个字符
    chunks = splitter.split(text)
    # 步长为 8；窗口起始位置分别为 0、8、16、24
    assert len(chunks) == 4
    assert all(len(c) <= 10 for c in chunks)


def test_invalid_overlap_raises():
    import pytest

    with pytest.raises(ValueError):
        CharacterTextSplitter(chunk_size=10, chunk_overlap=10)
