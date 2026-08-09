<##
.SYNOPSIS
    Start the WendaXitog backend and frontend on the local machine.
##>
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$BackendEnv = Join-Path $BackendDir ".env"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$RuntimeDir = Join-Path $RootDir ".runtime"
$BackendPidFile = Join-Path $RuntimeDir "backend.pid"
$FrontendPidFile = Join-Path $RuntimeDir "frontend.pid"
$BackendLog = Join-Path $RuntimeDir "backend.log"
$BackendErrorLog = Join-Path $RuntimeDir "backend.error.log"
$FrontendLog = Join-Path $RuntimeDir "frontend.log"

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
$env:PYTHONUTF8 = "1"
$env:TORCH_COMPILE_DISABLE = "1"

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 60) {
    for ($i = 0; $i -lt $TimeoutSeconds; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return $true }
        } catch { }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Get-ListeningProcessId([int]$Port) {
    try {
        $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($connection) { return [int]$connection.OwningProcess }
    } catch { }
    return 0
}

if (-not (Test-Path -LiteralPath $BackendEnv)) {
    Write-Host "首次运行，需要先完成配置。"
    & (Join-Path $RootDir "setup.ps1")
}
if (-not (Test-Path -LiteralPath $VenvPython) -or -not (Test-Path -LiteralPath (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "尚未安装依赖，先运行安装器。"
    & (Join-Path $RootDir "install.ps1")
}
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "未找到 $VenvPython，请先运行 .\install.ps1"
}

$backendUrl = "http://127.0.0.1:$BackendPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"

if (-not (Wait-Http "$backendUrl/health" 2)) {
    $backendOwner = Get-ListeningProcessId $BackendPort
    if ($backendOwner -ne 0) {
        throw "端口 $BackendPort 已被进程 $backendOwner 占用，请先处理该服务。"
    }
    Write-Host "启动后端..."
    $backendProcess = Start-Process -FilePath $VenvPython -WorkingDirectory $BackendDir `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort") `
        -WindowStyle Hidden -RedirectStandardOutput $BackendLog -RedirectStandardError $BackendErrorLog -PassThru
    Set-Content -LiteralPath $BackendPidFile -Value $backendProcess.Id -Encoding ascii
    if (-not (Wait-Http "$backendUrl/health" 60)) {
        Write-Host "后端启动失败，日志：$BackendLog" -ForegroundColor Red
        Get-Content -LiteralPath $BackendLog -Tail 30 -ErrorAction SilentlyContinue
        Get-Content -LiteralPath $BackendErrorLog -Tail 30 -ErrorAction SilentlyContinue
        throw "后端未能在规定时间内启动。"
    }
} else {
    Write-Host "后端已运行：$backendUrl"
}

if (-not (Wait-Http $frontendUrl 2)) {
    $frontendOwner = Get-ListeningProcessId $FrontendPort
    if ($frontendOwner -ne 0) {
        throw "端口 $FrontendPort 已被进程 $frontendOwner 占用，请先处理该服务。"
    }
    Write-Host "启动前端..."
    $frontendCommand = "/c npm run dev -- --hostname 127.0.0.1 --port $FrontendPort > `"$FrontendLog`" 2>&1"
    $frontendProcess = Start-Process -FilePath "cmd.exe" -WorkingDirectory $FrontendDir `
        -ArgumentList $frontendCommand -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $FrontendPidFile -Value $frontendProcess.Id -Encoding ascii
    if (-not (Wait-Http $frontendUrl 60)) {
        Write-Host "前端启动失败，日志：$FrontendLog" -ForegroundColor Red
        Get-Content -LiteralPath $FrontendLog -Tail 30 -ErrorAction SilentlyContinue
        throw "前端未能在规定时间内启动。"
    }
} else {
    Write-Host "前端已运行：$frontendUrl"
}

Write-Host ""
Write-Host "WendaXitog 已启动：$frontendUrl" -ForegroundColor Green
Write-Host "停止服务：.\stop.ps1"
if (-not $NoBrowser) {
    Start-Process $frontendUrl
}
