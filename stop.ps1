<##
.SYNOPSIS
    Stop only the processes recorded by start.ps1.
##>
[CmdletBinding()]
param()

$ErrorActionPreference = "SilentlyContinue"
$RootDir = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$RuntimeDir = Join-Path $RootDir ".runtime"

function Stop-RecordedProcess([string]$Name) {
    $pidFile = Join-Path $RuntimeDir "$Name.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) {
        Write-Host "$Name 没有可记录的进程。"
        return
    }
    $processId = [int](Get-Content -LiteralPath $pidFile | Select-Object -First 1)
    if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
        & taskkill.exe /PID $processId /T /F | Out-Null
        Write-Host "已停止 $Name（PID $processId）。"
    } else {
        Write-Host "$Name 进程已结束。"
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

Stop-RecordedProcess "frontend"
Stop-RecordedProcess "backend"
Write-Host "WendaXitog 已停止。"
