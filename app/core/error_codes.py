"""统一错误码规范。

分区规则（便于一眼定位问题归属）：
    0                : 成功
    10000 ~ 19999    : 通用 / 请求 / 权限 / 资源
    20000 ~ 29999    : 接口 / HTTP / 外部请求
    30000 ~ 39999    : 数据库 / 存储（含向量库）
    40000 ~ 49999    : 大模型 LLM 专属（含 embedding）
    50000 ~ 59999    : 系统 / 服务异常

每个错误码同时携带「对外提示」（msg，简洁、安全、不泄露技术细节）。
「对内细节」（堆栈、上下文）由异常的 detail 字段和日志承载，不返回给调用方。
"""
from __future__ import annotations

from enum import Enum


class ErrorCode(Enum):
    # ---- 成功 ----
    SUCCESS = (0, "成功")

    # ---- 通用 / 请求 / 权限 / 资源 10000~19999 ----
    PARAM_ERROR = (10001, "参数错误")
    UNAUTHORIZED = (10002, "未授权，请登录")
    FORBIDDEN = (10003, "权限不足")
    NOT_FOUND = (10004, "资源不存在")
    METHOD_ERROR = (10005, "请求方法错误")
    # 业务资源细化
    KB_NOT_FOUND = (10010, "知识库不存在")
    DOCUMENT_NOT_FOUND = (10011, "文档不存在")
    UNSUPPORTED_SOURCE_TYPE = (10012, "不支持的文档格式")

    # ---- 接口 / HTTP 20000~29999 ----
    API_REQUEST_ERROR = (20001, "接口请求失败")
    API_TIMEOUT = (20002, "接口请求超时")
    API_RATE_LIMIT = (20003, "接口调用超限")

    # ---- 数据库 / 存储 30000~39999 ----
    DB_ERROR = (30001, "数据库操作失败")
    DATA_DUPLICATE = (30002, "数据已存在")
    VECTOR_STORE_ERROR = (30010, "向量库操作失败")

    # ---- 大模型 LLM 40000~49999 ----
    LLM_ERROR = (40000, "大模型调用失败")
    LLM_TIMEOUT = (40001, "大模型响应超时")
    LLM_NO_RESPONSE = (40002, "大模型未返回有效内容")
    LLM_CONTENT_VIOLATION = (40003, "内容违规，大模型拒绝生成")
    LLM_TOKEN_LIMIT = (40004, "上下文长度超限")
    LLM_RATE_LIMIT = (40005, "大模型调用频率超限")
    LLM_MODEL_ERROR = (40006, "模型不存在或未部署")
    LLM_INVALID_JSON = (40007, "大模型返回内容不是合法 JSON")
    EMBEDDING_ERROR = (40010, "向量化（embedding）调用失败")
    RERANK_ERROR = (40020, "重排调用失败")

    # ---- 系统 / 服务 50000~59999 ----
    SERVER_ERROR = (50000, "服务器异常")
    SYSTEM_BUSY = (50001, "系统繁忙，请稍后再试")
    INDEXING_ERROR = (50010, "文档索引失败")

    @property
    def code(self) -> int:
        return self.value[0]

    @property
    def msg(self) -> str:
        return self.value[1]
