"""DocumentParser 抽象接口。

在切分之前，将上传的源内容归一化为纯文本。第一阶段只处理原始文本（.txt / .md
风格）。后续的 parser（PDF、DOCX、HTML）实现同一接口即可接入，无需改动 indexing
流程。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class DocumentParser(ABC):
    @abstractmethod
    def supports(self, source_type: str) -> bool:
        """该 parser 是否支持处理给定的 source_type。"""
        raise NotImplementedError

    @abstractmethod
    def parse(self, content: str, *, source_type: str = "text") -> str:
        """返回归一化后的纯文本，供下游切分使用。"""
        raise NotImplementedError
