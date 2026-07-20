"""LLMProvider 抽象接口。

统一的大模型调用入口。任何需要调用大模型的能力（rerank、query rewrite、意图识别、
评测辅助生成等）都必须通过这个接口访问模型，不允许在业务 service 或具体能力
provider 里直接发 HTTP 请求。切换模型厂商（DeepSeek、百炼、OpenAI 等）只需要
新增/替换 LLMProvider 实现，不需要改动上层调用方。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def chat_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict,
        temperature: float = 0.0,
        timeout_seconds: int | None = None,
    ) -> dict:
        """调用大模型，返回解析后的 JSON 对象。

        - system_prompt：系统提示词，定义任务、约束和输出格式。
        - user_payload：结构化 JSON 输入，会被序列化后作为用户消息发送给模型。
        - temperature：采样温度；重排、意图识别这类任务建议使用 0.0。
        - timeout_seconds：单次调用超时时间；为 None 时使用 provider 的默认值。

        如果模型没有返回合法 JSON，必须抛出 `LLMProviderError`。本方法只负责
        模型调用和 JSON 解析，不负责具体业务逻辑（业务逻辑归上层 provider，
        比如 RerankProvider）。
        """
        raise NotImplementedError
