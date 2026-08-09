<##
.SYNOPSIS
    Configure local secrets and the enterprise source directory.
##>
[CmdletBinding()]
param(
    [switch]$UseMockProvider
)

$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$BackendEnv = Join-Path $BackendDir ".env"
$FrontendEnv = Join-Path $FrontendDir ".env.local"

function Ensure-LocalFile([string]$Target, [string]$Example) {
    if (-not (Test-Path -LiteralPath $Target)) {
        Copy-Item -LiteralPath $Example -Destination $Target
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

function Set-DotEnvValue([string]$Path, [string]$Name, [AllowEmptyString()][string]$Value) {
    $escapedName = [regex]::Escape($Name)
    $lines = @()
    if (Test-Path -LiteralPath $Path) {
        $lines = @(Get-Content -LiteralPath $Path -Encoding utf8)
    }
    $found = $false
    $newLines = foreach ($line in $lines) {
        if ($line -match "^\s*#?\s*$escapedName=") {
            $found = $true
            "$Name=$Value"
        } else {
            $line
        }
    }
    if (-not $found) { $newLines += "$Name=$Value" }
    Set-Content -LiteralPath $Path -Value $newLines -Encoding utf8
}

function Read-SecretText([string]$Prompt) {
    $secureValue = Read-Host -Prompt $Prompt -AsSecureString
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
}

Ensure-LocalFile $BackendEnv (Join-Path $BackendDir ".env.example")
Ensure-LocalFile $FrontendEnv (Join-Path $FrontendDir ".env.local.example")

Write-Host "WendaXitog 首次配置" -ForegroundColor Cyan

$currentKey = Get-DotEnvValue $BackendEnv "RAG_DEEPSEEK_API_KEY"
if ($UseMockProvider) {
    Set-DotEnvValue $BackendEnv "RAG_DEFAULT_LLM_PROVIDER" "mock"
    Write-Host "已选择 Mock Provider（仅用于流程验收）。"
} elseif ($currentKey) {
    Set-DotEnvValue $BackendEnv "RAG_DEFAULT_LLM_PROVIDER" "deepseek"
    Set-DotEnvValue $BackendEnv "RAG_DEEPSEEK_MODEL" "deepseek-v4-flash"
    Write-Host "检测到已有 DeepSeek Key，保留现有配置。"
} else {
    $newKey = Read-SecretText "请输入 DeepSeek API Key（直接回车则使用 Mock）"
    if ($newKey) {
        Set-DotEnvValue $BackendEnv "RAG_DEFAULT_LLM_PROVIDER" "deepseek"
        Set-DotEnvValue $BackendEnv "RAG_DEEPSEEK_API_KEY" $newKey
        Set-DotEnvValue $BackendEnv "RAG_DEEPSEEK_MODEL" "deepseek-v4-flash"
        Write-Host "DeepSeek 已配置（Key 不会显示）。"
    } else {
        Set-DotEnvValue $BackendEnv "RAG_DEFAULT_LLM_PROVIDER" "mock"
        Write-Host "未填写 Key，当前使用 Mock Provider。" -ForegroundColor Yellow
    }
}

$defaultSource = Join-Path $BackendDir "app\data\source_library"
$currentSource = Get-DotEnvValue $BackendEnv "RAG_KNOWLEDGE_SOURCE_ROOT"
if (-not $currentSource -or $currentSource -match "path/to/enterprise-library") {
    $sourceInput = Read-Host "企业总资料库目录（直接回车使用 $defaultSource）"
    if (-not $sourceInput) { $sourceInput = $defaultSource }
    $sourcePath = [IO.Path]::GetFullPath($sourceInput)
    New-Item -ItemType Directory -Force -Path $sourcePath | Out-Null
    Set-DotEnvValue $BackendEnv "RAG_KNOWLEDGE_SOURCE_ROOT" ($sourcePath -replace "\\", "/")
    Write-Host "资料目录：$sourcePath"
} else {
    Write-Host "保留已有资料目录：$currentSource"
}

Set-DotEnvValue $FrontendEnv "NEXT_PUBLIC_API_BASE" "http://localhost:8000"
Write-Host "前端 API 地址：http://localhost:8000"
Write-Host "配置完成。运行 .\start.ps1 启动项目。" -ForegroundColor Green
