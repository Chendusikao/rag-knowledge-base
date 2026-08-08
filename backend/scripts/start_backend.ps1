# start_backend.ps1
# One-click: free port 8000, then start the RAG backend with the correct
# environment variables for Chinese Windows (torch inductor GBK crash).
# Run from the backend folder in PowerShell:
#   cd E:\xaizai\wendaxitog\backend
#   .\scripts\start_backend.ps1

$ErrorActionPreference = "Stop"

# Critical env vars for Chinese Windows.
# Without these, torch.compile triggers an inductor that reads UTF-8 CUDA
# kernel templates as GBK -> UnicodeDecodeError, and the backend crashes
# on the first embedding (retrieval / chat).
$env:PYTHONUTF8 = "1"
$env:TORCH_COMPILE_DISABLE = "1"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Resolve-Path (Join-Path $ScriptDir "..")
$Port       = 8000
Set-Location $BackendDir

# --- Free port 8000 if something is still listening ---
$lines = netstat -ano | Select-String ":$Port\s"
foreach ($l in $lines) {
    if ($l -match '(\d+)\s+LISTENING\s+(\d+)') {
        $procId = $matches[2]
        if ($procId -ne '0' -and $procId -ne '4') {
            Write-Host "Killing stale process $procId on port $Port"
            taskkill /F /PID $procId 2>$null
        }
    }
}
Start-Sleep -Seconds 1

$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$Log        = Join-Path $BackendDir "backend.log"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Venv not found: $VenvPython"
    exit 1
}

# --- Start backend detached; cmd /c handles stdout+stderr redirection ---
Write-Host "Starting backend on http://127.0.0.1:$Port  (log: $Log)"
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c","$VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port > `"$Log`" 2>&1" `
    -WindowStyle Hidden

# --- Wait for health check ---
$ok = $false
for ($i = 1; $i -le 40; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/docs" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}

if ($ok) {
    Write-Host ""
    Write-Host "Backend is UP at http://127.0.0.1:$Port"
    Write-Host "  Swagger UI : http://127.0.0.1:$Port/docs"
    Write-Host "  Chat tool  : .\.venv\Scripts\python.exe .\scripts\chat_kb.py"
} else {
    Write-Host ""
    Write-Host "Backend did not come up in time. Check $Log for errors:"
    Get-Content $Log -Tail 30 -ErrorAction SilentlyContinue
}
