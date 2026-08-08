<#
.SYNOPSIS
    一键重启后端 + 全库重索引（Windows / PowerShell）
.DESCRIPTION
    1. 停掉占用 8000 端口的旧 uvicorn 进程（让新解析代码生效）
    2. 用项目 .venv 后台启动后端，并把日志写到 backend/backend.log
    3. 轮询 /docs 做健康检查，最多等 ~60s
    4. 运行 scripts/reindex_all_kbs.py，用当前解析器（Docling）重新解析+向量化所有知识库
.NOTES
    - 仅在本机执行；需要 .venv 已装好依赖（含 docling）。
    - 首次解析 PDF 时 Docling 会自动从 HuggingFace 下载布局/表格模型，需联网。
    - 重索引脚本自带 worker，不依赖后端是否在线；此处重启后端是为了让在线 API 也加载新解析代码。
#>

$ErrorActionPreference = "Stop"

# 中文 Windows 上 torch inductor 读取 kernel 模板会用 GBK 解码 UTF-8 文件，导致
# Docling 版面模型加载失败（'gbk' codec can't decode byte）。设置这两个环境变量
# 修复：启用 Python UTF-8 模式 + 禁用 torch.compile（变 no-op，绕开 inductor）。
$env:PYTHONUTF8 = "1"
$env:TORCH_COMPILE_DISABLE = "1"

# ---- 路径（全部用 ASCII，避免编码问题）----
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir  = Resolve-Path (Join-Path $ScriptDir "..")
$VenvPython  = Join-Path $BackendDir ".venv\Scripts\python.exe"
$ReindexPy   = Join-Path $BackendDir "scripts\reindex_all_kbs.py"
$BackendLog  = Join-Path $BackendDir "backend.log"
$Port        = 8000

if (-not (Test-Path $VenvPython)) {
    Write-Error "Venv not found: $VenvPython`nRun in backend/: python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt"
    exit 1
}

# ---- 1. 停掉占用端口的旧后端 ----
Write-Host "[1/4] Stopping old uvicorn on port $Port ..." -ForegroundColor Cyan
$conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($conns) {
    $pids = $conns.OwningProcess | Where-Object { $_ -and $_ -gt 4 } | Sort-Object -Unique
    if (-not $pids) {
        Write-Host "    no user process on port $Port, skipped."
    } else {
        foreach ($procId in $pids) {
            try {
                Stop-Process -Id $procId -Force -ErrorAction Stop
                Write-Host "    killed PID $procId"
            } catch {
                Write-Warning "    failed to kill PID $procId (may need admin)"
            }
        }
        Start-Sleep -Seconds 2
    }
} else {
    Write-Host "    no process on port $Port, skipped."
}

# ---- 2. 后台启动后端 ----
Write-Host "[2/4] Starting backend in background (log -> $BackendLog) ..." -ForegroundColor Cyan
# Start-Process 不允许 stdout/stderr 指向同一个文件；用 cmd /c 合并两路到单一日志。
$quotedPy  = "`"$VenvPython`""
$quotedLog = "`"$BackendLog`""
$cmdLine   = "$quotedPy -m uvicorn app.main:app --host 127.0.0.1 --port $Port > $quotedLog 2>&1"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $cmdLine -WorkingDirectory $BackendDir -WindowStyle Hidden

# ---- 3. 健康检查 ----
Write-Host "[3/4] Waiting for backend (max 60s) ..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest "http://127.0.0.1:$Port/docs" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    Write-Warning "Backend not ready within 60s; see $BackendLog"
    Write-Warning "Reindex will still run because the script has its own worker."
} else {
    Write-Host "    backend ready at http://127.0.0.1:$Port/docs" -ForegroundColor Green
}

# ---- 4. 全库重索引 ----
Write-Host "[4/4] Running full reindex ..." -ForegroundColor Cyan
& $VenvPython $ReindexPy
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "Done. Backend is running in background; reindex finished." -ForegroundColor Green
    Write-Host "Backend log: $BackendLog"
} else {
    Write-Error "Reindex script exited with code $exitCode."
}
exit $exitCode
