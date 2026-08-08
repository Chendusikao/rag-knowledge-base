#!/usr/bin/env bash
# 一键重启后端 + 全库重索引（Git Bash / WSL / Linux）
#
# 步骤：
#   1. 停掉占用 8000 端口的旧 uvicorn（让新解析代码生效）
#   2. 用项目 .venv 后台启动后端，日志写到 backend/backend.log
#   3. 轮询 /docs 做健康检查，最多等 ~60s
#   4. 运行 scripts/reindex_all_kbs.py 用当前解析器（Docling）重新解析+向量化所有知识库
#
# 注意：
#   - 仅在本机执行；需要 .venv 已装好依赖（含 docling）。
#   - 首次解析 PDF 时 Docling 会自动从 HuggingFace 下载布局/表格模型，需联网。
#   - 重索引脚本自带 worker，不依赖后端是否在线；重启后端是为了让在线 API 也加载新解析代码。

set -euo pipefail

# 中文 Windows 上 torch inductor 读取 kernel 模板会用 GBK 解码 UTF-8 文件，导致
# Docling 版面模型加载失败。设置这两个环境变量修复（UTF-8 模式 + 禁用 torch.compile）。
export PYTHONUTF8=1
export TORCH_COMPILE_DISABLE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$BACKEND_DIR/.venv/Scripts/python.exe"   # Windows venv（Git Bash 下可用）
# 若在纯 Linux/WSL 用系统 venv，则改为: VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
fi
REINDEX_PY="$BACKEND_DIR/scripts/reindex_all_kbs.py"
BACKEND_LOG="$BACKEND_DIR/backend.log"
PORT=8000

if [ ! -f "$VENV_PYTHON" ]; then
  echo "ERROR: 找不到虚拟环境解释器: $VENV_PYTHON" >&2
  echo "请先在 backend 目录执行: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

# 1. 停掉占用端口的旧后端
echo "[1/4] 停止占用端口 $PORT 的旧 uvicorn 进程..."
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" || true
elif command -v lsof >/dev/null 2>&1; then
  pids="$(lsof -ti tcp:"$PORT" || true)"
  [ -n "$pids" ] && kill -9 $pids || true
else
  # Windows / Git Bash 回退：用 taskkill
  taskkill //F //IM uvicorn.exe >/dev/null 2>&1 || true
fi
sleep 2

# 2. 后台启动后端
echo "[2/4] 后台启动后端 (日志 -> $BACKEND_LOG)..."
nohup "$VENV_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
  > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

# 3. 健康检查
echo "[3/4] 等待后端就绪 (最多 60s)..."
ready=0
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$PORT/docs" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [ "$ready" -eq 1 ]; then
  echo "    后端已就绪 (http://127.0.0.1:$PORT/docs)。"
else
  echo "WARNING: 后端在 60s 内未就绪，请查看 $BACKEND_LOG"
  echo "WARNING: 仍会继续尝试重索引（脚本自带 worker，不依赖后端在线）。"
fi

# 4. 全库重索引
echo "[4/4] 运行全库重索引..."
"$VENV_PYTHON" "$REINDEX_PY"
exit_code=$?

echo ""
if [ "$exit_code" -eq 0 ]; then
  echo "完成。后端已在后台运行（PID $BACKEND_PID），重索引已执行。"
  echo "查看后端日志: $BACKEND_LOG"
else
  echo "ERROR: 重索引脚本返回非零退出码 ($exit_code)，请检查上方输出。" >&2
fi
exit "$exit_code"
