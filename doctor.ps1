<##
.SYNOPSIS
    Check dependencies, configuration, ports and running services.
##>
[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "SilentlyContinue"
$RootDir = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$BackendEnv = Join-Path $BackendDir ".env"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$issues = 0

function Check-Item([string]$Label, [bool]$Ok, [string]$Detail, [switch]$Warning) {
    if ($Ok) {
        Write-Host "[OK] $Label - $Detail" -ForegroundColor Green
    } elseif ($Warning) {
        Write-Host "[WARN] $Label - $Detail" -ForegroundColor Yellow
    } else {
        Write-Host "[FAIL] $Label - $Detail" -ForegroundColor Red
        $script:issues++
    }
}

function Get-DotEnvValue([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path)) { return "" }
    $escapedName = [regex]::Escape($Name)
    $line = Get-Content -LiteralPath $Path -Encoding utf8 |
        Where-Object { $_ -match "^\s*$escapedName=(.*)$" } |
        Select-Object -First 1
    if ($line) { return $line.Substring($Name.Length + 1) }
    return ""
}

Write-Host "WendaXitog 环境诊断" -ForegroundColor Cyan
$python = Get-Command py -ErrorAction SilentlyContinue
$node = Get-Command node -ErrorAction SilentlyContinue
Check-Item "Python Launcher" ([bool]$python) "需要 Python 3.11+"
Check-Item "Node.js" ([bool]$node) "需要 Node.js 18+"
Check-Item "Python venv" (Test-Path -LiteralPath $VenvPython) $VenvPython
Check-Item "Frontend dependencies" (Test-Path -LiteralPath (Join-Path $FrontendDir "node_modules")) "frontend/node_modules"
Check-Item "Backend env" (Test-Path -LiteralPath $BackendEnv) "backend/.env"

$provider = Get-DotEnvValue $BackendEnv "RAG_DEFAULT_LLM_PROVIDER"
$apiKey = Get-DotEnvValue $BackendEnv "RAG_DEEPSEEK_API_KEY"
if ($provider -eq "deepseek") {
    Check-Item "DeepSeek API Key" ([bool]$apiKey) "已配置（不会显示 Key）"
} else {
    Check-Item "LLM Provider" $false "当前为 $provider（Mock 适合链路验收）" -Warning
}

$sourceRoot = Get-DotEnvValue $BackendEnv "RAG_KNOWLEDGE_SOURCE_ROOT"
Check-Item "Source library" ([bool]$sourceRoot -and (Test-Path -LiteralPath $sourceRoot)) $sourceRoot -Warning

foreach ($port in @($BackendPort, $FrontendPort)) {
    try {
        $connection = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($connection) {
            Check-Item "Port $port" $true "PID $($connection.OwningProcess) 正在监听"
        } else {
            Check-Item "Port $port" $true "当前空闲"
        }
    } catch {
        Check-Item "Port $port" $true "无法读取监听状态" -Warning
    }
}

try {
    $backendStatus = (Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/health" -UseBasicParsing -TimeoutSec 3).StatusCode
    Check-Item "Backend health" ($backendStatus -eq 200) "HTTP $backendStatus"
} catch {
    Check-Item "Backend health" $false "http://127.0.0.1:$BackendPort/health 尚未响应" -Warning
}

try {
    $frontendStatus = (Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort" -UseBasicParsing -TimeoutSec 3).StatusCode
    Check-Item "Frontend health" ($frontendStatus -eq 200) "HTTP $frontendStatus"
} catch {
    Check-Item "Frontend health" $false "http://127.0.0.1:$FrontendPort 尚未响应" -Warning
}

if ($issues -gt 0) {
    Write-Host ""
    Write-Host "诊断发现 $issues 个必须处理的问题。" -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "诊断完成。" -ForegroundColor Green
