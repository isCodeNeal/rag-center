# RAG 知识库管理前端

RAG 中台的独立前端项目，用于**创建知识库**和**上传文档**，方便做检索链路的调优测试。
这是最小可用版本：不含鉴权、不含知识库列表管理等，后续按需补充。

## 技术栈

- React 18 + TypeScript
- Vite
- Tailwind CSS + shadcn/ui 风格组件
- React Router v6
- React Query（@tanstack/react-query）
- axios
- React Hook Form + Zod

## 目录结构

```
src/
├── components/
│   ├── provider/     # React Query + Toaster Provider
│   └── ui/           # shadcn/ui 风格基础组件
│   ├── create-knowledge-base.tsx
│   └── upload-documents.tsx
├── pages/            # 页面组件
├── services/         # API 请求封装（解包 {code,msg,data}）
├── hooks/            # 业务 hooks（创建知识库、顺序上传）
├── types/            # TypeScript 类型
├── lib/              # axios 实例、cn 工具
└── utils/            # 文件读取等工具
```

## 前置条件

后端需先启动并监听 `http://localhost:8000`（见 `../rag-center`）。前端通过 Vite dev
server 把 `/api/*` 代理到该地址，因此**无需后端配置 CORS**。

## 本地启动

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 。

如需指向其它后端地址：

```bash
cp .env.example .env    # 修改 VITE_API_TARGET
```

## 功能说明

1. **顶部 tenant_id**：默认 `tenant_demo`，创建知识库和上传都会带上。
2. **创建知识库**：调用 `POST /api/v1/knowledge-bases/create`，成功后自动把 `kb_id`
   填入下方上传区域。
3. **上传文档**：
   - 支持“选择文件”（多选）和“选择文件夹”（`webkitdirectory`）。
   - 文件夹上传即**逐个文件顺序上传**。
   - 结果表格实时反馈每个文件的状态：成功 / 失败 / 跳过，成功的显示 chunk 数，
     失败/跳过的显示原因，并给出总数汇总。

## 重要约束

后端 `POST /api/v1/documents/upload` 接收的是**纯文本 `content` 字符串**（不是文件流）。
因此前端用 `FileReader` 把文件读成文本再提交，**仅支持文本类文件**
（`.txt / .md / .markdown / .csv / .json / .log / .text`）。其余文件（PDF、docx、图片等）
会被标记为“跳过 - 不支持的文件类型”，不会上传。

## 构建

```bash
npm run build     # tsc 类型检查 + vite 打包到 dist/
npm run preview   # 预览打包产物
```

---

## 离线测评

基于 RAGAS 的离线检索质量评测。使用前需安装 eval 依赖：

```bash
pip install -e ".[eval]"
```

### 三步流程

**1. 从 Langfuse 导出低分 case（需 Langfuse 已部署并有反馈数据）**

```bash
python scripts/export_eval_cases_from_langfuse.py \
  --max-score 3 --days 30 \
  --kb-id YOUR_KB_ID \
  --output eval/datasets/imported_from_feedback.json
```

**2. 人工补 `ground_truth`**，然后合并进主集：

```bash
python scripts/export_eval_cases_from_langfuse.py \
  --max-score 3 \
  --merge eval/datasets/ecommerce_retrieval.json \
  --output eval/datasets/ecommerce_retrieval.json
```

**3. 运行评测**

```bash
python scripts/run_retrieval_eval.py \
  --dataset eval/datasets/ecommerce_retrieval.json \
  --api-key rk_live_你的key \
  --profile balanced \
  --output eval/reports/balanced.json
```

改配置（词表/profile）前后各跑一遍对比：

```bash
python scripts/run_retrieval_eval.py --dataset ... --profile balanced \
  --output eval/reports/before_synonyms.json
# （改完配置）
python scripts/run_retrieval_eval.py --dataset ... --profile balanced \
  --output eval/reports/after_synonyms.json
```

评测报告在 `eval/reports/`（已加入 `.gitignore`）。测例种子见 `eval/datasets/_seed_ecommerce.json`。
