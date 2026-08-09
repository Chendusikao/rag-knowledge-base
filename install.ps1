<##
.SYNOPSIS
    Install the local Windows runtime for WendaXitog.

.DESCRIPTION
    Creates the backend virtual environment, installs Python dependencies,
    installs frontend dependencies, and creates local environment files from
    the checked-in examples. Secrets and runtime data stay outside Git.
##>
[CmdletBinding()]
param(
    [switch]$SkipPythonDependencies,
    [switch]$SkipFrontendDependencies
)

$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$VenvDir = Join-Path $BackendDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

function Invoke-Native([string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory) {
    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "命令失败（退出码 $LASTEXITCODE）：$FilePath $($Arguments -join ' ')"
        }
    } finally {
        Pop-Location
    }
}

Write-Host "WendaXitog Windows 安装器" -ForegroundColor Cyan
Write-Host "项目目录：$RootDir"

$pythonCommand = Get-Command py -ErrorAction SilentlyContinue
if ($pythonCommand) {
    $systemPython = (& $pythonCommand.Source -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $systemPython = $pythonCommand.Source
    }
}
if (-not $systemPython -or -not (Test-Path -LiteralPath $systemPython)) {
    Fail "未找到 Python 3。请安装 Python 3.11 或更高版本后重新运行。"
}

$pythonVersion = (& $systemPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
$versionParts = $pythonVersion.Split('.')
if ([int]$versionParts[0] -lt 3 -or ([int]$versionParts[0] -eq 3 -and [int]$versionParts[1] -lt 11)) {
    Fail "检测到 Python $pythonVersion，需要 Python 3.11 或更高版本。"
}
Write-Host "[OK] Python $pythonVersion"

$npmCommand = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    Fail "未找到 npm。请安装 Node.js 18 或更高版本后重新运行。"
}
$nodeVersion = (& node --version).Trim()
Write-Host "[OK] Node.js $nodeVersion"

if (-not (Test-Path -LiteralPath (Join-Path $BackendDir ".env"))) {
    Copy-Item -LiteralPath (Join-Path $BackendDir ".env.example") -Destination (Join-Path $BackendDir ".env")
    Write-Host "已创建 backend/.env（尚未填写 DeepSeek Key）" -ForegroundColor Yellow
}
if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir ".env.local"))) {
    Copy-Item -LiteralPath (Join-Path $FrontendDir ".env.local.example") -Destination (Join-Path $FrontendDir ".env.local")
    Write-Host "已创建 frontend/.env.local"
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "正在创建 Python 虚拟环境..."
    Invoke-Native $systemPython @("-m", "venv", $VenvDir) $BackendDir
}
Write-Host "[OK] backend/.venv"

if (-not $SkipPythonDependencies) {
    Write-Host "正在安装后端依赖（首次可能需要几分钟）..."
    Invoke-Native $VenvPython @("-m", "pip", "install", "--upgrade", "pip") $BackendDir
    Invoke-Native $VenvPython @("-m", "pip", "install", "-r", "requirements.txt") $BackendDir
}

if (-not $SkipFrontendDependencies) {
    Write-Host "正在安装前端依赖（首次可能需要几分钟）..."
    Invoke-Native $npmCommand.Source @("install") $FrontendDir
}

Write-Host ""
Write-Host "安装完成。下一步运行：" -ForegroundColor Green
Write-Host "  .\setup.ps1   # 配置 DeepSeek Key 和资料目录"
Write-Host "  .\start.ps1   # 启动前后端并打开浏览器"
