# RAG 中台租户接入指南

面向新接入的业务方（租户）。按本文操作即可完成从开通到检索的完整流程，无需阅读源码。

## 1. 定位

RAG 中台是一个**检索能力中台**：你把文档灌进知识库，中台负责切片、向量化、混合检索，
`retrieve` 接口返回结构化的 chunk 列表（`retrieved_chunks`）。

**中台不生成答案**——把召回的 chunk 作为上下文，交给你自己的大模型/业务逻辑去生成最终回复。

## 2. 开通步骤

由平台运维执行（脚本在项目根目录 `scripts/`）：

```bash
# 1) 注册租户（默认 free 套餐）
python scripts/create_tenant.py --id tenant_a --name "租户 A"

# 2) 给租户发一把 API Key（明文只打印一次，请立即保存）
python scripts/create_api_key.py --tenant-id tenant_a --name "客服系统对接"

# 3)（可选）调整套餐档位
python scripts/update_tenant_plan.py --tenant-id tenant_a --plan standard
```

此后所有请求在请求头带上 Key：

```
Authorization: Bearer $API_KEY
```

（`$API_KEY` 为 `create_api_key.py` 签发后保存的明文；格式为 `rk_live_` + 32 位 hex，此处用变量占位避免误触密钥扫描。）

未授权或 Key 错误时，响应 `code=20010`（HTTP 状态码仍为 200）。

## 3. 套餐（plan）三档

套餐挂在租户上，决定**能做什么**（功能开关）和**能用多少**（配额）。三档写死在代码里
（`app/tenant/plan_presets.py`），改配额需改代码发版。

| 功能 | free | standard | pro |
|---|---|---|---|
| 允许的 profile | 仅 speed | speed / balanced / custom | 全部（含 quality） |
| hybrid 检索 | ❌ | ✅ | ✅ |
| rerank | ❌ | ❌ | ✅ |
| query 改写 | ❌ | ❌ | ✅ |

| 配额项 | free | standard | pro |
|---|---|---|---|
| 检索 QPS | 3 | 10 | 50 |
| 日检索量 | 500 | 5,000 | 100,000 |
| 最大知识库数 | 1 | 5 | 50 |
| 单库最大文档数 | 30 | 200 | 5,000 |
| 最大并发索引（PROCESSING） | 1 | 2 | 10 |

## 4. 检索预设（retrieve profile）四档

profile 是**每次 retrieve 请求**传的字段，决定这次检索要快还是要准。不传时默认 `balanced`。

| profile | 说明 | 展开概要 |
|---|---|---|
| `speed` | 追求速度 | mode=vector，top_k=3，关 rerank / rewrite |
| `balanced` | 均衡（默认） | mode=hybrid，top_k=5，关 rerank / rewrite |
| `quality` | 追求质量（仅 pro） | mode=hybrid，top_k=8，开 rerank + rewrite |
| `custom` | 自定义 | 用请求里的 retrieval_options / rerank_options / query_options，仍受 plan 约束 |

curl 示例（每条都带 `profile`）：

```bash
# speed
curl -X POST http://localhost:8000/api/v1/rag/retrieve \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"kb_id":"KB_ID","user_id":"u1","query":"退款要几天","profile":"speed"}'

# balanced（等价于不传 profile）
curl -X POST http://localhost:8000/api/v1/rag/retrieve \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"kb_id":"KB_ID","user_id":"u1","query":"退款要几天","profile":"balanced"}'

# quality（需 pro）
curl -X POST http://localhost:8000/api/v1/rag/retrieve \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"kb_id":"KB_ID","user_id":"u1","query":"退款要几天","profile":"quality"}'

# custom（自定义 options）
curl -X POST http://localhost:8000/api/v1/rag/retrieve \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"kb_id":"KB_ID","user_id":"u1","query":"退款要几天","profile":"custom",
       "retrieval_options":{"mode":"vector"},"top_k":5}'
```

响应 `metadata.tenant_policy` 会带回本次生效的 plan、profile 与实际参数，便于对照。

## 5. plan 与 profile 的关系

- **plan 管「能用什么」**：租户档案，决定功能与配额上限，脚本维护。
- **profile 管「这次怎么跑」**：每次请求的策略，不属于租户档案。
- 不传 profile 默认 `balanced`；传了 plan 不允许的 profile（如 free 传 balanced）→ `code=20013`。
- custom 下主动打开 plan 不允许的能力（如 standard 传 rerank）→ 同样 `code=20013`。

## 6. 词表配置（各 plan 都可用）

知识库可配同义词扩展（`synonyms`）与改写提示（`rewrite_hint`），检索时自动生效。用脚本维护：

```bash
python scripts/update_kb_settings.py --kb-id KB_ID --settings-file kb_settings.json
```

示例文件见 `examples/kb_settings.example.json`（整文件覆盖，非增量合并）。

## 7. 常见错误码

响应 HTTP 状态码恒为 200，业务结果看 body 里的 `code`：

| code | 含义 | 处理 |
|---|---|---|
| 20010 | 未授权 / Key 无效 | 检查 Authorization 头与 Key |
| 20013 | 功能超出 plan（profile 或 options） | 换更低档 profile，或升级套餐 |
| 20014 | 配额超限（库数 / 文档数 / 并发 / 日检索量） | 清理或升级套餐 |
| 20005 | 检索 QPS 超限 | 降低并发，稍后重试 |
| 20020 | 反馈写入失败（Langfuse 不可用） | 确认 Langfuse 已启动，或 LANGFUSE_ENABLED=false 下跳过 |
| 20021 | log_id 与 trace_id 不匹配 / 无权操作 | 使用本次 retrieve 返回的 log_id 和 trace_id |

## 8. 检索反馈

每次 `retrieve` 成功后，响应 `metadata` 中带有：
- `log_id`：本次检索的本地记录 ID，与 `retrieval_logs` 表主键一致
- `trace_id`：Langfuse trace 标识（`LANGFUSE_ENABLED=false` 时为 null）

业务方保存 `trace_id`，对召回质量打分：

```bash
curl -X POST http://localhost:8000/api/v1/rag/feedback \\
  -H "Authorization: Bearer $API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "trace_id": "响应里的 trace_id",
    "log_id": "响应里的 log_id",
    "score": 4,
    "comment": "排第三的 chunk 才是对的，但召回了"
  }'
```

`score` 为 1～5 分。运营可在 Langfuse 按 `user_feedback` 筛选低分 trace 做复盘，
也可用 `scripts/export_eval_cases_from_langfuse.py` 导出后跑 RAGAS 离线评测，
详见 [eval/ 目录说明](../eval/)。

## 9. 旧租户说明

本次套餐能力上线时，迁移脚本把升级前已存在的租户默认设为 `standard`
（`tenant_demo` 设为 `pro`），避免老用户突然降档。升档用：

```bash
python scripts/update_tenant_plan.py --tenant-id tenant_a --plan pro
```
