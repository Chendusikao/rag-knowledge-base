# 企业知识库问答与治理系统（V1）

面向企业内部知识管理、部门知识库、权限控制、审计追踪与资料问答的本地优先系统。
当前版本使用 DeepSeek API 完成自然语言对话生成；企业文件解析、权限判断、检索、引用绑定和审计在本地完成。

> **模型边界**：要获得真实的自然语言答案，后端必须配置 DeepSeek API Key。没有 Key 时，系统仍可以导入资料、检索片段、展示引用并验证权限审计链路，但问答会使用 Mock 生成器，仅用于开发和验收。仓库不包含 API Key、企业资料或模型权重。

> 本仓库当前为 **V1 可运行版本**：核心数据模型、持久任务系统、Provider 抽象、文档导入、检索、引用、权限和审计链路已成形；本地 LLM 权重与推理运行时没有随仓库内置，需要根据部署设备另行安装。

## 目标范围（摘自 PLAN.md）

- 多个相互隔离的知识库。
- 支持 PDF、Markdown、Markdown 素材目录、PNG/JPG。
- 扫描件 OCR、表格/图片语义理解、结构化切分。
- BM25 + 稠密向量 + RRF 融合 + Rerank + 查询改写 + 低置信度二次检索。
- 回答提供可点击引用，定位页码/章节/表格/图片。
- 增量索引、分层缓存、链路追踪、RAG 评测面板。
- 默认本地 RAG，兼容 OpenAI-compatible 与 Dify Agent API。
- 部门归属与部门知识库，支持“本部门可读”和“仅授权用户”两种范围。
- 系统管理员、部门负责人、成员、审计员四类角色，以及知识库查看/编辑/管理三级授权。
- HttpOnly 登录会话、首次强制改密、登录限流、来源校验和安全响应头。
- 只追加审计日志，记录登录、部门、用户、授权、文档、问答和配置变更，不记录密码与问答正文。
- 管理员可从配置的企业总资料库扫描一级资料分支，先配置部门与访问范围，再以受管副本方式增量导入。

**V1 明确排除**：SaaS 公开注册、多租户、外部 SSO/LDAP、云部署、网页爬取。

## 技术栈

- **前端**：Next.js 14、React 18、TypeScript 5、Tailwind CSS 3；提供登录、企业初始化、部门知识库、文件导入、知识问答、权限和审计页面。
- **后端**：Python、FastAPI 0.115、Uvicorn 0.30、Pydantic 2；以 REST API 和 SSE 流式接口连接前端。
- **数据与任务**：SQLite WAL、SQLAlchemy 2（异步）、aiosqlite、Alembic；内置可恢复的任务队列和 Worker，不依赖 Redis 或外部数据库。
- **RAG 检索**：中文 BM25、稠密向量检索、Chroma 持久化 ANN（未安装时回退文件索引）、RRF 融合、可选重排、引用绑定和检索追踪。
- **文档处理**：Docling 解析 PDF、Office、图片等文件；支持 Markdown/纯文本结构化切分，并预留 OCR/VLM 能力。
- **模型接入**：DeepSeek OpenAI-compatible API；可插拔 Mock、DeepSeek、OpenAI-compatible、Dify 和本地 Embedding Provider。
- **企业安全**：PBKDF2-SHA256 密码哈希、HttpOnly 会话 Cookie、角色与知识库 ACL、只追加审计日志、CORS 和安全响应头。
- **工程工具**：npm、Python venv、pytest、TypeScript 类型检查和 Next.js production build。

## 对话模型与本地替代

### 当前使用：DeepSeek API

当前正式对话使用 DeepSeek API，默认模型为 `deepseek-v4-flash`。在 `backend/.env` 中配置：

```env
RAG_DEFAULT_LLM_PROVIDER=deepseek
RAG_DEEPSEEK_API_KEY=你的 DeepSeek API Key
RAG_DEEPSEEK_BASE_URL=https://api.deepseek.com
RAG_DEEPSEEK_MODEL=deepseek-v4-flash
```

DeepSeek 只负责根据本地检索出的上下文生成答案；API Key 只放在后端环境变量中，不进入前端、数据库或 GitHub。由于当前对话使用云端 API，提交前应评估企业资料出网、合规和费用策略。DeepSeek 官方文档已将 `deepseek-chat` 标记为旧模型别名并进入弃用周期，因此项目说明使用当前模型名 `deepseek-v4-flash`。

### 可实现本项目功能的本地模型（当前未随项目内置）

由于当前设备的显存、内存和本地推理环境限制，仓库没有捆绑本地 LLM 权重或运行时；具备合适设备后，可以通过本项目的 OpenAI-compatible Provider 接入以下模型：

- **Qwen3 8B / 14B（Instruct 或混合思考版本）**：优先推荐中文企业资料问答；支持多语言、指令跟随和思考/非思考模式。
- **DeepSeek-R1-Distill-Qwen 7B / 14B / 32B**：偏复杂推理和多步分析；模型规模越大，部署资源和响应时间要求越高。
- **Qwen2.5-Instruct 7B / 14B**：成熟的中文指令模型，可作为轻量本地问答备选。
- **DeepSeek-R1-Distill-Llama 8B** 或 **Llama 3.1/3.2 Instruct 8B**：通用英文/多语言备选，接入企业中文资料前应单独评估中文回答和引用准确率。

本地运行可以选择 **Ollama、LM Studio 或 vLLM**，只要提供 `/v1/chat/completions` 形式的 OpenAI-compatible 接口即可复用当前问答链路；不需要改动前端页面、权限过滤或引用机制。模型权重、量化版本、显存/内存要求和许可证需由部署方单独确认。

官方资料：

- [Qwen3 官方说明](https://github.com/QwenLM/Qwen3)
- [DeepSeek-R1 官方仓库与蒸馏模型](https://github.com/deepseek-ai/DeepSeek-R1)
- [Ollama OpenAI 兼容接口](https://docs.ollama.com/api/openai-compatibility)
- [LM Studio 本地 API](https://lmstudio.ai/docs/developer/rest)

## 目录结构

```
wendaxitog/
├── backend/      # FastAPI + SQLAlchemy + Alembic（API、任务、评测与开发调试，共用 SQLite WAL）
├── frontend/     # Next.js + TS + Tailwind（面向用户的知识库、多文件导入与问答界面）
└── docs/         # 架构与数据契约说明
```

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 默认 Mock Provider 只用于启动和链路验收；正式问答请在 backend/.env 中切换到 DeepSeek
uvicorn app.main:app --reload --port 8000
# 打开 http://localhost:8000/docs 查看 OpenAPI
```

正式使用时，在 `backend/.env` 中配置：

```env
RAG_DEFAULT_LLM_PROVIDER=deepseek
RAG_DEEPSEEK_API_KEY=你的 DeepSeek API Key
RAG_DEEPSEEK_BASE_URL=https://api.deepseek.com
RAG_DEEPSEEK_MODEL=deepseek-v4-flash
```

API Key 只保存在本机 `.env`，不要提交到 GitHub、写入 SQLite 或放进前端代码。
DeepSeek 负责自然语言答案生成；向量检索可继续使用 `local-lexical` 或本地 BGE-M3，
不需要把企业资料发送给向量云服务。没有配置 Key 时，系统仍能运行检索和引用链路，
但问答会使用 Mock 占位生成，不代表正式模型效果。

### 前端

```bash
cd frontend
npm install
cp .env.local.example .env.local   # 设置 NEXT_PUBLIC_API_BASE=http://localhost:8000
npm run dev
# 首次打开 http://localhost:3000，创建企业和首位系统管理员
```

管理员登录后可打开 `/source-library` 查看总资料库分支，并通过
`RAG_KNOWLEDGE_SOURCE_ROOT` 配置本机源目录。系统不会直接索引或删除
源文件，而是将受支持文件复制进受管知识库目录后再建立索引；重复同步按内容哈希跳过。

开发调试统一放在后端：打开 `http://127.0.0.1:8000/docs` 查看并调用 API；
检索参数、评测、Provider 与任务状态不作为普通用户前端导航的一部分。

## 企业治理与安全边界

- 首次初始化入口仅在数据库中没有任何用户时开放；完成后不可再次调用。
- 密码使用 PBKDF2-SHA256 加盐哈希；浏览器只保存 HttpOnly 会话 Cookie，不把令牌写入 localStorage。
- 部门成员仅自动获得“部门可读”知识库的查看权限；跨部门访问和受限知识库必须单独授权。
- 原文件只能从受控知识库目录读取；删除文档或知识库时同步清理对应文件。
- 总资料库作为只读数据源使用；“简历、合同、人事、薪酬、法务、财务、客户”等敏感分支默认采用受限访问，改为部门共享时必须再次确认。
- 审计表由 SQLite 触发器禁止更新和删除，但数据库文件和原始资料的静态加密仍依赖部署机器的 BitLocker 或等效磁盘加密。
- 本地 HTTP 默认不启用 Cookie `Secure` 标志。正式部署到 HTTPS 后设置 `RAG_AUTH_COOKIE_SECURE=true`。

部署参数示例位于 `backend/.env.example`，复制为 `backend/.env` 后由后端自动读取。

完整权限矩阵和部署检查见 `docs/enterprise-governance.md`。

## 关键设计要点

- **可插拔 Provider**：`services/providers/base.py` 定义 `LLMProvider / EmbeddingProvider / VisionProvider / AgentProvider`。
  默认 `MockProvider` 让系统在没有任何模型或云端 Key 时也能跑通流程；正式对话通过 DeepSeek，或切换到本地 OpenAI-compatible 模型服务。
- **持久化任务系统**：`services/task_system.py` 以 `JobRun` 持久表 + 租约(lease) + 检查点(checkpoint) + 重试实现，
  API 进程与独立 Worker 共用同一 SQLite，支持失败恢复与重启续跑，不依赖 Redis/Docker。
- **检索编排**：`services/retrieval/manager.py` 实现 `fast / balanced / deep` 三档参数化流程；BM25 真实可用，
  Dense 向量与 Rerank 为可插拔留桩，RRF 融合已实装。
- **密钥管理**：云端 Provider 的 API Key 计划存入 Windows 凭据管理器，SQLite 仅存凭据引用与能力信息（见 `ProviderProfile`）。

详见 `docs/architecture.md`。
