# 架构与数据契约（V1 地基脚手架）

> 配套 PLAN.md。本文件描述脚手架已实现与留桩的部分，便于后续按 8–10 周计划推进。

## 1. 技术栈

| 层 | 选型 | 状态 |
|---|---|---|
| 前端 | Next.js 14 (App Router) + TS + Tailwind | 已实现页面骨架 |
| 后端 | FastAPI + Pydantic v2 + SQLAlchemy 2.0 (async) | 已实现 |
| 业务/任务/聊天/缓存/评测存储 | SQLite（WAL 单文件） | 已实现 |
| 稠密向量 | Chroma（持久化 ANN，按 KB 代次分集合，PLAN 目标） | 已实现：接口与 File 回退双后端；装了 `chromadb` 自动启用，否则用零依赖文件索引 |
| 稀疏索引 | BM25（rank_bm25，基于 SQLite Chunk 文本；**中文按字符 n-gram 切分**，否则中文整句被当单个 token 而失效） | 已实现（中文分词已修复） |
| 解析 | **Docling 真实解析已接入**：PDF/Word/PPT/Excel/图片/HTML 的版面+表格抽取，带真实页码/章节路径/模态；图片 OCR 可选（easyocr） | Markdown/纯文本仍走标题感知切分；PDF 解析失败优雅降级为占位 |
| 本地嵌入 | **BGE-M3**（真·语义，1024 维，sentence-transformers）**或** `local-lexical`（零下载、纯本地、内容派生词法向量，1024 维） | `LocalEmbedding` + `LocalLexicalEmbedding` 均已实装；默认 `local-lexical`（当前网络封锁模型权重 CDN）；可切 `local` 用 BGE-M3 |
| 密钥 | Windows 凭据管理器（计划） | secret_store 占位（支持 env 注入） |

## 2. 目录

```
backend/
  app/
    core/config.py            # 所有运行时配置（路径/限额/默认 provider）
    db/                       # Base, 异步 Session(WAL), init_db
    models/                   # 全部核心对象（见 PLAN §3）
    schemas/                  # 请求/响应契约
    api/routers/              # knowledge-bases, documents, jobs, chat, retrieval, evaluation, providers
    services/
      task_system.py          # 持久化任务：租约/心跳/检查点/重试/恢复
      providers/              # base + mock + openai_compatible + dify + factory + secret_store + local_embedding + lexical_embedding
      retrieval/              # bm25, dense_store(Chroma+File 双后端,自动切换), rrf, manager（三档模式）
      parsing.py              # Markdown 结构化切分（占位解析）
      indexing.py             # 索引 Job：写 Chunk + 原子代次切换
      chat_service.py         # 流式问答：检索→生成→引用绑定→持久化
      evaluation.py           # 评测 Job：MRR/Hit/Recall/nDCG + Faithfulness 占位
frontend/
  src/app/                    # 六个页面 + 布局
  src/lib/api.ts              # 类型化客户端 + SSE 读取
  scripts/generate-client.ts  # 从 /openapi.json 生成 TS 类型
```

## 3. 核心对象（PLAN §3）

`KnowledgeBase · Document · DocumentVersion · Chunk · IndexGeneration ·
ChatSession · Message · Citation · RetrievalTrace · EvaluationCase ·
EvaluationRun · MetricResult · JobRun · ProviderProfile · CacheEntry`

全部落在单一 SQLite（WAL）文件，便于持久任务系统在 API 与独立 Worker 间共享。

## 4. 检索三档（PLAN §3.Online）

| 模式 | 召回 Top | RRF 保留 | 重排保留 | 改写 | 二次检索 |
|---|---|---|---|---|---|
| fast | 20/20 | 8 | 8 | 否 | 否 |
| balanced | 40/40 | 30 | 8 | 是 | 否（默认） |
| deep | 40/40 | 60 | 12 | 是(子问题) | 是（最多一次） |

RRF 已实装（`k=60`）；**BM25 已支持中文**（按字符 n-gram 切分）；**Dense 已接真实 Chroma 持久化 ANN 索引**（向量由可插拔 EmbeddingProvider 产出）。默认 `local-lexical`：零下载、纯本地的**内容派生词法向量**（中文 2~3-gram + 英文词，TF 加权 + 符号哈希 + L2 归一化，1024 维）——让稠密检索/RRF/重排跑在真实内容上，但属「词法级」（不识别同义词）。**真·语义向量（BGE-M3）**待权重可下载时启用：设 `RAG_DEFAULT_EMBEDDING_PROVIDER=local`（模型 `BAAI/bge-m3`，首次加载下载 ~2.3GB 权重）。**Rerank 已支持 DeepSeek LLM-as-reranker**：`rerank_provider=deepseek` 且填了 `RAG_DEEPSEEK_API_KEY` 时，对 RRF 融合后的候选用 DeepSeek 打分重排序；否则回退 RRF 顺序（永不因重排失败而阻断检索）。

索引采用**整库原子再生**：每次（重）索引把该 KB 全部文档重写为一个新代次，写入 Chroma 后再原子翻转 `current_generation` 并回收旧代次集合，避免"只刷新单文档却全局 +1 代次导致其他文档被检索过滤"的隐患。

## 5. 持久任务系统（PLAN §2）

`JobRun` 一行即任务。Worker 通过**租约(lease)**认领，定时**心跳**续期；
崩溃的作业由 `recover_stale_jobs` 在超时后重新入队，状态/检查点全在 SQLite，
**不依赖 Redis/Docker**。后端 `lifespan` 内置一个 in-process Worker，便于单命令启动。

## 6. Provider 抽象（PLAN §3）

`LLMProvider / EmbeddingProvider / VisionProvider / AgentProvider / RerankProvider`。
默认 `mock` 使系统在**无 GPU、无云端 Key** 下也能跑通；接本地 BGE-M3 / OpenAI-compatible /
Dify / DeepSeek 时只改配置/ProviderProfile，不改动检索与引用逻辑。`LocalEmbedding`
（懒加载 sentence-transformers，指向 **BGE-M3**，1024 维，100+ 语言，本地 CPU 推理）与
`LocalLexicalEmbedding`（零依赖、离线、内容派生词法向量）均已实装。`local` Provider 支持
**离线本地路径**模式：把 BGE-M3 权重下到本地目录后，于 `.env` 设
`RAG_DEFAULT_EMBEDDING_PROVIDER=local` + `RAG_LOCAL_EMBEDDING_MODEL_PATH=<绝对路径>` 即从本地
文件夹直接加载（`config.local_embedding_model_path`），**完全不经过网络**；若未设 PATH 则该
Provider 按 `local_embedding_model`（默认 `BAAI/bge-m3`）尝试从 HF 下载。当前环境已启用本地
BGE-M3（权重位于 `E:/xaizai/wendaxitog/backend/models/bge-m3`），验证语义相似度（中文猫/小猫
余弦 0.795 ≫ 股票 0.324）与端到端检索均正常。切换 embedding provider 后使用
`scripts/reindex_all_kbs.py` 一键重索引所有知识库。新增 **DeepSeek 接入**：
`factory` 增加 `kind=deepseek`（复用 OpenAI-compatible 指向 `https://api.deepseek.com`），
`default_llm_provider=deepseek` 即让问答用 DeepSeek 真实生成（前端 `backend="local"` 走
`get_llm()`）；`deepseek.py` 提供 `DeepSeekReranker` 作 LLM-as-reranker。密钥仅走
`RAG_DEEPSEEK_API_KEY` 环境变量（`.env`，git 忽略），不进源码。Dify 必须接收本地
`context_bundle`，不得绕过本地引用核验。

## 7. 已知留桩（后续阶段填充）

- Docling / OCR / VLM 解析（当前仅 Markdown 真实切分）
- Qwen3-Reranker 本地重排推理（当前使用 DeepSeek 云端重排，可优雅回退）；查询改写与子问题拆解的真实 LLM 调用（DeepSeek 云端重排/生成已可启用）
- RAGAS 指标、引用准确率、分层缓存命中统计
- 密钥的 Windows 凭据管理器集成（secret_store 占位）
- 独立 Worker 进程启动脚本、E2E/压测、评测面板 UI
