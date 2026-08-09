# 企业多模态 RAG 知识库问答系统（V1 地基脚手架）

面向企业内部知识管理与业务问答的本地部署、单组织、全栈多模态 RAG 系统。
当前 V1 聚焦受控环境内的知识入库、检索、问答与企业治理。

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
- 部门归属与部门知识库，支持“本部门可读”和“仅授权用户”两种范围。
- 系统管理员、部门负责人、成员、审计员四类角色，以及知识库查看/编辑/管理三级授权。
- HttpOnly 登录会话、首次强制改密、登录限流、来源校验和安全响应头。
- 只追加审计日志，记录登录、部门、用户、授权、文档、问答和配置变更，不记录密码与问答正文。
- 管理员可从配置的企业总资料库扫描一级资料分支，先配置部门与访问范围，再以受管副本方式增量导入。

**V1 明确排除**：SaaS 公开注册、多租户、外部 SSO/LDAP、云部署、网页爬取。

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
  默认 `MockProvider` 让系统在没有任何模型或云端 Key 时也能跑通流程；后续接 Qwen3 / OpenAI-compatible / Dify 即可切换。
- **持久化任务系统**：`services/task_system.py` 以 `JobRun` 持久表 + 租约(lease) + 检查点(checkpoint) + 重试实现，
  API 进程与独立 Worker 共用同一 SQLite，支持失败恢复与重启续跑，不依赖 Redis/Docker。
- **检索编排**：`services/retrieval/manager.py` 实现 `fast / balanced / deep` 三档参数化流程；BM25 真实可用，
  Dense 向量与 Rerank 为可插拔留桩，RRF 融合已实装。
- **密钥管理**：云端 Provider 的 API Key 计划存入 Windows 凭据管理器，SQLite 仅存凭据引用与能力信息（见 `ProviderProfile`）。

详见 `docs/architecture.md`。
