# 知识库问答网页版（Web Chat）

把命令行工具 `chat_kb.py` 升级成的网页问答界面：选知识库 → 中文提问 → 答案由
DeepSeek 基于知识库内容**逐字流式**生成，末尾展示「参考来源」（文档/页码/章节）。

## 入口

后端启动后，浏览器打开：

```
http://127.0.0.1:8000/
```

（根路径即是聊天页，Swagger 仍在 `/docs`。）

## 功能

- 左侧知识库列表（移动端自动变为顶部下拉），点选即切换
- 流式中文问答，多轮会话自动带上下文（同一知识库连续追问）
- 回答末尾渲染「参考来源」卡片：文档名、页码、章节路径、原文片段
- 顶部徽章显示当前模型状态：`DeepSeek 已启用` / `示例回答（未配置模型）`
- 资料不足时，回答末尾追加提示
- 「新建会话」按钮：清空多轮上下文，重新问

## 技术说明

- 前端：单文件原生 HTML/CSS/JS（`backend/app/static/index.html`），无框架、无构建
- 托管：`backend/app/main.py` 末尾 `app.mount("/", StaticFiles(...))`，`/api/*` 路由优先级更高，现有接口不受影响
- 新增 `GET /api/v1/meta`：返回 `llm_provider` / `deepseek_configured` / `doc_parser`，供前端顶部状态徽章使用
- 聊天走 `POST /api/v1/chat/stream`（SSE），解析 `phase == "generate"` 的 `token` 增量渲染

## 改动代码后如何生效

改完 `index.html` 或 `main.py` 后，重跑：

```
cd E:\xaizai\wendaxitog\backend
.\scripts\start_backend.ps1
```

## 排错

| 现象 | 处理 |
| --- | --- |
| 页面提示「连不上后端」 | 后端没启动或 8000 被占。重跑 `start_backend.ps1` |
| 徽章显示「示例回答」 | `backend/.env` 里 `RAG_DEEPSEEK_API_KEY` 未填，或 provider 未设为 deepseek |
| 提问后没有任何回答 | 看 `backend.log` 末尾，多为检索或模型调用报错；重跑启动脚本 |
| 回答提示「资料不足」 | 该问题在所选知识库里没检索到相关内容，换个问法或换知识库 |
