# 切换解析器后的「重启后端 + 全库重索引」指南

> 适用场景：本次把 RAG 的文档解析从占位升级为 **Docling 真实解析**（PDF / Word / PPT / Excel / 图片 / HTML 的版面 + 表格抽取）。
> 切换解析器后，**已索引的旧向量不会自动更新**，必须重索引，否则线上检索仍用的是旧的占位块。

---

## 为什么要做这两步

| 步骤 | 作用 | 不做会怎样 |
|------|------|-----------|
| 重启后端 | 让在线 API 进程加载新的 `parsing.py` / `parsing_docling.py` 代码 | 之后上传的文档仍走旧解析路径 |
| 全库重索引 | 用当前解析器（Docling）重新解析磁盘上已存的文档并重新向量化 | 已存文档的 Chunk 仍是旧的占位内容，检索质量不提升 |

重索引脚本 `scripts/reindex_all_kbs.py` **自带 worker**，直接读 SQLite + 调解析/嵌入管线，
**不需要后端在线**也能跑。脚本里「重启后端」主要是为了让你之后通过 API 上传也能用上新解析器。

---

## 前置条件

1. **依赖已装好**：`backend/.venv` 内已 `pip install -r requirements.txt`（含 `docling 2.118.1`）。
2. **首次解析 PDF 需联网**：Docling 会自动从 HuggingFace 下载布局/表格模型（模型较小，
   缓存到 `~/.cache/huggingface`，和之前 BGE-M3 下载方式一致）。下载一次后离线可用。
3. **可选 OCR（扫描件/图片文字）**：`pip install easyocr` + 在 `backend/.env` 设 `RAG_DOCLING_OCR=true`。
   不装则图片无 OCR 文字时产出占位说明块。

---

## ⚠️ 中文 Windows 必读：Docling 需要的环境变量

在中文 Windows 上，torch 的 `torch.compile` 会触发 **torch inductor** 去读取 CUDA kernel 模板文件，而 torch 读取该文件时没指定编码、默认用系统 **GBK** 去解码一个 **UTF-8** 文件，会抛：

```
UnicodeDecodeError: 'gbk' codec can't decode byte 0x94 in position 618: illegal multibyte sequence
```

这会导致 Docling 的**版面模型加载失败**，进而文档被**静默降级成占位块**——你只会看到
`parser_version=docling-1.0` 标签，但 Chunk 内容是占位的「解析待接入 Docling…」。

**修复：启动 Python 前设置以下两个环境变量**（一键脚本 `reindex_restart.ps1/.sh` 已内置）：
- `TORCH_COMPILE_DISABLE=1`：让 `torch.compile` 变 no-op，彻底绕开 inductor 路径（CPU 上本就没多少加速收益）。
- `PYTHONUTF8=1`：让 Python 默认用 UTF-8，避免任何地方再冒 GBK 错误。

> 注：`app/services/parsing_docling.py` 顶部已 `os.environ.setdefault("TORCH_COMPILE_DISABLE","1")`
> 作为纵深防御——即使进程启动时没设这俩变量，通过 API 上传 PDF 也不会因 inductor 崩溃。
> 但手动 `python -m uvicorn` 启动时仍建议显式设置，以防万一。

---

## 方式一：一键脚本（推荐）

### Windows（PowerShell）
**必须先切换到项目根目录 `E:\xaizai\wendaxitog`，或用绝对路径。**

在项目根目录执行：
```powershell
cd E:\xaizai\wendaxitog
powershell -ExecutionPolicy Bypass -File backend\scripts\reindex_restart.ps1
```

或者从任意目录用绝对路径：
```powershell
powershell -ExecutionPolicy Bypass -File E:\xaizai\wendaxitog\backend\scripts\reindex_restart.ps1
```

> 报错 `backend/scripts/reindex_restart.ps1 不存在` 就是因为你当前目录不对（比如在 `C:\Users\liang`），找不到这个相对路径。

### Git Bash / WSL / Linux
```bash
bash backend/scripts/reindex_restart.sh
```
> Linux 下若 `.venv/Scripts/python.exe` 不存在，脚本会自动回退到 `.venv/bin/python`。

---

## 方式二：手动分步

```bash
cd backend

# 1) 停掉旧后端（如有），例如结束占用 8000 端口的进程
#    Windows: 任务管理器结束 uvicorn，或 fuser -k 8000/tcp
# 2) 启动后端（后台）—— 中文 Windows 必须先设这两个环境变量，否则 Docling 版面模型加载会因 GBK 崩溃
export PYTHONUTF8=1
export TORCH_COMPILE_DISABLE=1
nohup .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &

# 3) 跑全库重索引（ standalone，不依赖后端在线）
.venv/Scripts/python.exe scripts/reindex_all_kbs.py
```

脚本输出示例：
```
Found 3 knowledge base(s) to reindex.
  enqueued reindex for KB <id> (job <id>)
Draining job queue...
  worker cycle #1 finished
  ...
Reindexed 3 KB(s). Job queue state: queued=0 running=0 succeeded=3 failed=0
```

---

## 预期与排错

- **首次跑会慢**：每个 PDF 首次解析要下载 Docling 模型（仅一次）。之后命中缓存会快很多。
- **`failed` 数不为 0**：脚本会打印每个失败 job 的 `error`。常见原因：
  - 网络不通导致模型下载失败 → 检查网络，或手动预下载；
  - 个别文件损坏 → 单独删除/重新上传该文档。
- **后端 60s 内没起来**：重索引仍会继续（自带 worker）。启动问题看 `backend/backend.log`。
- **怎么确认真的用了 Docling**：重索引后，每条 Chunk / DocumentVersion 的 `parser_version` 字段应为
  `docling-1.0`（旧占位块为 `md-0.1` / `legacy-0.1`）。可用 SQLite 工具查：
  ```sql
  SELECT parser_version, COUNT(*) FROM chunks GROUP BY parser_version;
  SELECT parser_version, COUNT(*) FROM document_versions GROUP BY parser_version;
  ```

---

## 相关代码位置

- 解析分发：`backend/app/services/parsing.py`（`RAG_DOC_PARSER` 控制 auto/docling/legacy）
- Docling 实现：`backend/app/services/parsing_docling.py`
- 版本溯源：`parser_version_for(ext)` → 写入 `DocumentVersion` 与 `Chunk`
- 重索引：`backend/scripts/reindex_all_kbs.py`
- 配置项：`backend/app/core/config.py` → `doc_parser`、`docling_ocr`
