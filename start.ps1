<##
.SYNOPSIS
    Start the WendaXitog backend and frontend on the local machine.
##>
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000,
    [bool]$ReplaceStaleBackend = $true
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
$ExpectedBackendVersion = "0.2.0"
$MainPy = Join-Path $BackendDir "app\main.py"
if (Test-Path -LiteralPath $MainPy) {
    $versionMatch = [regex]::Match((Get-Content -LiteralPath $MainPy -Raw -Encoding utf8), 'version="([^"]+)"')
    if ($versionMatch.Success) {
        $ExpectedBackendVersion = $versionMatch.Groups[1].Value
    }
}

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

function Get-BackendHealth([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($response.StatusCode -ne 200) { return $null }
        return ($response.Content | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Get-ListeningProcessId([int]$Port) {
    try {
        $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($connection) { return [int]$connection.OwningProcess }
    } catch { }
    return 0
}

function Stop-ProcessTree([int]$ProcessId) {
    if ($ProcessId -eq 0) { return $false }
    $result = Start-Process -FilePath "taskkill.exe" `
        -ArgumentList @("/PID", "$ProcessId", "/T", "/F") `
        -WindowStyle Hidden -Wait -PassThru
    return $result.ExitCode -eq 0
}

function Find-FreePort([int]$StartingPort) {
    for ($port = $StartingPort; $port -lt ($StartingPort + 20); $port++) {
        if (Get-ListeningProcessId $port -eq 0) { return $port }
    }
    throw "没有找到可用的后端端口（起始端口 $StartingPort）。"
}

function Find-HealthyBackend([int]$StartingPort, [int]$EndPort) {
    for ($port = $StartingPort; $port -le $EndPort; $port++) {
        $health = Get-BackendHealth ("http://127.0.0.1:{0}/health" -f $port)
        if ($health -and [string]$health.version -eq $ExpectedBackendVersion) {
            return [pscustomobject]@{ Port = $port; Health = $health }
        }
    }
    return $null
}

function Set-FrontendApiBase([int]$Port) {
    $envFile = Join-Path $FrontendDir ".env.local"
    if (-not (Test-Path -LiteralPath $envFile)) {
        Copy-Item -LiteralPath (Join-Path $FrontendDir ".env.local.example") -Destination $envFile
    }
    $newValue = "NEXT_PUBLIC_API_BASE=http://localhost:$Port"
    $lines = @(Get-Content -LiteralPath $envFile -Encoding utf8)
    $found = $false
    $changed = $false
    $newLines = foreach ($line in $lines) {
        if ($line -match "^\s*#?\s*NEXT_PUBLIC_API_BASE=") {
            $found = $true
            if ($line -ne $newValue) { $changed = $true }
            $newValue
        } else {
            $line
        }
    }
    if (-not $found) {
        $newLines += $newValue
        $changed = $true
    }
    if ($changed) {
        Set-Content -LiteralPath $envFile -Value $newLines -Encoding utf8
    }
    return $changed
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

$activeBackendPort = $BackendPort
$backendUrl = "http://127.0.0.1:$activeBackendPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"

$backendHealth = Get-BackendHealth "$backendUrl/health"
if ($backendHealth -and [string]$backendHealth.version -ne $ExpectedBackendVersion) {
    $backendOwner = Get-ListeningProcessId $BackendPort
    if ($ReplaceStaleBackend -and $backendOwner -ne 0) {
        Write-Host "检测到旧版后端（$($backendHealth.version)），正在替换为 $ExpectedBackendVersion..."
        $killSucceeded = Stop-ProcessTree $backendOwner
        Start-Sleep -Seconds 1
        if ($killSucceeded -and (Get-ListeningProcessId $BackendPort -eq 0)) {
            $backendHealth = $null
        } else {
            Write-Host "无法替换旧版后端，正在寻找可用端口..." -ForegroundColor Yellow
            $healthyFallback = Find-HealthyBackend ($BackendPort + 1) ($BackendPort + 19)
            if ($healthyFallback) {
                $activeBackendPort = $healthyFallback.Port
                $backendUrl = "http://127.0.0.1:$activeBackendPort"
                $backendHealth = $healthyFallback.Health
            } else {
                $activeBackendPort = Find-FreePort ($BackendPort + 1)
                $backendUrl = "http://127.0.0.1:$activeBackendPort"
                $backendHealth = $null
            }
        }
    } else {
        $healthyFallback = Find-HealthyBackend ($BackendPort + 1) ($BackendPort + 19)
        if ($healthyFallback) {
            $activeBackendPort = $healthyFallback.Port
            $backendUrl = "http://127.0.0.1:$activeBackendPort"
            $backendHealth = $healthyFallback.Health
        } else {
            $activeBackendPort = Find-FreePort ($BackendPort + 1)
            $backendUrl = "http://127.0.0.1:$activeBackendPort"
            $backendHealth = $null
        }
    }
}

if (-not $backendHealth) {
    $backendOwner = Get-ListeningProcessId $activeBackendPort
    if ($backendOwner -ne 0) {
        throw "端口 $activeBackendPort 已被进程 $backendOwner 占用，请先处理该服务。"
    }
    Write-Host "启动后端（端口 $activeBackendPort）..."
    $backendProcess = Start-Process -FilePath $VenvPython -WorkingDirectory $BackendDir `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$activeBackendPort") `
        -WindowStyle Hidden -RedirectStandardOutput $BackendLog -RedirectStandardError $BackendErrorLog -PassThru
    Set-Content -LiteralPath $BackendPidFile -Value $backendProcess.Id -Encoding ascii
    if (-not (Wait-Http "$backendUrl/health" 60)) {
        Write-Host "后端启动失败，日志：$BackendLog" -ForegroundColor Red
        Get-Content -LiteralPath $BackendLog -Tail 30 -ErrorAction SilentlyContinue
        Get-Content -LiteralPath $BackendErrorLog -Tail 30 -ErrorAction SilentlyContinue
        throw "后端未能在规定时间内启动。"
    }
    $backendHealth = Get-BackendHealth "$backendUrl/health"
    if (-not $backendHealth -or [string]$backendHealth.version -ne $ExpectedBackendVersion) {
        throw "后端已启动，但版本不匹配（期望 $ExpectedBackendVersion）。"
    }
} else {
    Write-Host "后端已运行：$backendUrl（版本 $($backendHealth.version)）"
}

$frontendConfigChanged = Set-FrontendApiBase $activeBackendPort
if ($frontendConfigChanged -and (Get-ListeningProcessId $FrontendPort) -ne 0) {
    $staleFrontendOwner = Get-ListeningProcessId $FrontendPort
    Write-Host "后端端口已变更，正在重启前端以加载 API 地址..."
    Stop-ProcessTree $staleFrontendOwner | Out-Null
    Start-Sleep -Seconds 1
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
