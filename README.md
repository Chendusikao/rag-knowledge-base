# 个人多模态 RAG 知识库问答系统（V1 地基脚手架）

面向求职作品集的本地单用户、全栈、多模态 RAG 知识库问答系统。

> 本仓库当前为 **V1 地基脚手架**：核心数据模型、持久任务系统、Provider 抽象与检索编排已成形，
> 但解析（Docling/OCR/VLM）、本地模型推理、完整评测面板等为**留桩（stub）**，需后续按 8–10 周计划逐步填充。

## 目标范围（摘自 PLAN.md）

- 多个相互隔离的知识库。
- 支持 PDF、Markdown、Markdown 素材目录、PNG/JPG。
- 扫描件 OCR、表格/图片语义理解、结构化切分。
- BM25 + 稠密向量 + RRF 融合 + Rerank + 查询改写 + 低置信度二次检索。
- 回答提供可点击引用，定位页码/章节/表格/图片。
- 增量索引、分层缓存、链路追踪、RAG 评测面板。
- 默认本地 RAG，兼容 OpenAI-compatible 与 Dify Agent API。

**V1 明确排除**：公开注册、团队权限、云部署、网页爬取、DOCX。

## 目录结构

```
wendaxitog/
├── backend/      # FastAPI + SQLAlchemy + Alembic（业务/任务/聊天/缓存/评测共用 SQLite WAL）
├── frontend/     # Next.js + TS + Tailwind（知识库/文档/聊天/检索实验室/评测/设置）
└── docs/         # 架构与数据契约说明
```

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 默认使用 Mock Provider，无需 GPU / 大模型即可启动
uvicorn app.main:app --reload --port 8000
# 打开 http://localhost:8000/docs 查看 OpenAPI
```

### 前端

```bash
cd frontend
npm install
cp .env.local.example .env.local   # 设置 NEXT_PUBLIC_API_BASE=http://localhost:8000
npm run dev
# 打开 http://localhost:3000
```

## 关键设计要点

- **可插拔 Provider**：`services/providers/base.py` 定义 `LLMProvider / EmbeddingProvider / VisionProvider / AgentProvider`。
  默认 `MockProvider` 让系统在没有任何模型或云端 Key 时也能跑通流程；后续接 Qwen3 / OpenAI-compatible / Dify 即可切换。
- **持久化任务系统**：`services/task_system.py` 以 `JobRun` 持久表 + 租约(lease) + 检查点(checkpoint) + 重试实现，
  API 进程与独立 Worker 共用同一 SQLite，支持失败恢复与重启续跑，不依赖 Redis/Docker。
- **检索编排**：`services/retrieval/manager.py` 实现 `fast / balanced / deep` 三档参数化流程；BM25 真实可用，
  Dense 向量与 Rerank 为可插拔留桩，RRF 融合已实装。
- **密钥管理**：云端 Provider 的 API Key 计划存入 Windows 凭据管理器，SQLite 仅存凭据引用与能力信息（见 `ProviderProfile`）。

详见 `docs/architecture.md`。
