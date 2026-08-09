[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$PackageZip,

    # These switches are used by the local package smoke test. The public
    # installer entry point does not pass them.
    [switch]$SkipRuntimeInstall,
    [switch]$SkipSetup,
    [switch]$SkipStart,
    [switch]$SkipShortcuts,
    [string]$InstallPath = ""
)

$ErrorActionPreference = "Stop"
$AppName = "WendaXitog"
$TempPayload = $null

function Write-Stage([string]$Message) {
    Write-Host ""
    Write-Host ("==> " + $Message) -ForegroundColor Cyan
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($machinePath -or $userPath) {
        $env:Path = (($machinePath, $userPath | Where-Object { $_ }) -join ";")
    }
}

function Test-PythonAvailable {
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $version = (& $py.Source -3 -c "import sys; print(sys.version_info.major * 100 + sys.version_info.minor)").Trim()
            if ([int]$version -ge 311) { return $true }
        } catch { }
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) {
        try {
            $version = (& $python.Source -c "import sys; print(sys.version_info.major * 100 + sys.version_info.minor)").Trim()
            if ([int]$version -ge 311) { return $true }
        } catch { }
    }
    return $false
}

function Test-NodeAvailable {
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    return [bool]($node -and $npm)
}

function Install-WithWinget([string]$DisplayName, [string]$PackageId) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "$DisplayName is required, but winget is not available. Install it manually and run the installer again."
    }

    $answer = Read-Host "$DisplayName was not found. Install it automatically with winget? [Y/n]"
    if ($answer -and $answer -notmatch "^(?i:y|yes)$") {
        throw "Installation cancelled. Install $DisplayName and run the installer again."
    }

    & $winget.Source install --id $PackageId --exact --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install $DisplayName (exit code $LASTEXITCODE)."
    }
    Refresh-ProcessPath
}

function Ensure-Prerequisites {
    if (-not (Test-PythonAvailable)) {
        Install-WithWinget "Python 3.11 or newer" "Python.Python.3.11"
        if (-not (Test-PythonAvailable)) {
            throw "Python 3.11 or newer is still not available after installation."
        }
    }
    Write-Host "[OK] Python 3.11+"

    if (-not (Test-NodeAvailable)) {
        Install-WithWinget "Node.js LTS" "OpenJS.NodeJS.LTS"
        if (-not (Test-NodeAvailable)) {
            throw "Node.js and npm are still not available after installation."
        }
    }
    Write-Host "[OK] Node.js and npm"
}

function Should-SkipRelativePath([string]$RelativePath) {
    $path = $RelativePath.Replace("\", "/")
    return (
        $path -eq "backend/.env" -or
        $path -eq "frontend/.env.local" -or
        $path -eq "installer-entry.cmd" -or
        $path.StartsWith("backend/.venv/", [StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("backend/app/data/", [StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("backend/models/", [StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("frontend/node_modules/", [StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("frontend/.next/", [StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith(".runtime/", [StringComparison]::OrdinalIgnoreCase)
    )
}

function Copy-Payload([string]$SourceRoot, [string]$TargetRoot) {
    Write-Stage "Copying application files"
    $sourceRootFull = (Resolve-Path -LiteralPath $SourceRoot).Path.TrimEnd("\")
    foreach ($file in (Get-ChildItem -LiteralPath $sourceRootFull -Recurse -Force -File)) {
        $relative = $file.FullName.Substring($sourceRootFull.Length).TrimStart("\", "/")
        if (Should-SkipRelativePath $relative) { continue }

        $destination = Join-Path $TargetRoot ($relative.Replace("/", "\"))
        $parent = Split-Path -Parent $destination
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    }
}

function Invoke-ProjectScript([string]$ProjectRoot, [string]$ScriptName) {
    $scriptPath = Join-Path $ProjectRoot $ScriptName
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "Missing project script: $scriptPath"
    }

    Write-Stage "Running $ScriptName"
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $scriptPath
    if ($LASTEXITCODE -ne 0) {
        throw "$ScriptName failed (exit code $LASTEXITCODE)."
    }
}

function New-Shortcut(
    [string]$ShortcutPath,
    [string]$TargetPath,
    [string]$Arguments,
    [string]$WorkingDirectory
) {
    $parent = Split-Path -Parent $ShortcutPath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.WindowStyle = 7
    $shortcut.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,270"
    $shortcut.Save()
}

function Create-Shortcuts([string]$ProjectRoot) {
    Write-Stage "Creating desktop and Start Menu shortcuts"
    $powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $startScript = Join-Path $ProjectRoot "start.ps1"
    $stopScript = Join-Path $ProjectRoot "stop.ps1"
    $startArgs = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $startScript + '"'
    $stopArgs = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $stopScript + '"'

    $desktop = [Environment]::GetFolderPath("Desktop")
    if ($desktop) {
        New-Shortcut (Join-Path $desktop "$AppName.lnk") $powershell $startArgs $ProjectRoot
    }

    $programs = [Environment]::GetFolderPath("Programs")
    if ($programs) {
        $menu = Join-Path $programs $AppName
        New-Shortcut (Join-Path $menu "$AppName.lnk") $powershell $startArgs $ProjectRoot
        New-Shortcut (Join-Path $menu "Stop $AppName.lnk") $powershell $stopArgs $ProjectRoot
    }
}

try {
    $packagePath = (Resolve-Path -LiteralPath $PackageZip).Path
    Write-Host "$AppName Windows Installer" -ForegroundColor Green
    Write-Host "The installer keeps application data and secrets in the selected local folder."

    if (-not $SkipRuntimeInstall) {
        Write-Stage "Checking prerequisites"
        Ensure-Prerequisites
    }

    $defaultInstallPath = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) $AppName
    $requestedPath = if ($InstallPath) {
        $InstallPath
    } else {
        Read-Host "Installation folder [$defaultInstallPath]"
    }
    if (-not $requestedPath) { $requestedPath = $defaultInstallPath }
    $installPath = [IO.Path]::GetFullPath($requestedPath)

    if (Test-Path -LiteralPath $installPath) {
        $reuse = Read-Host "The folder already exists. Update it and preserve existing configuration? [y/N]"
        if ($reuse -notmatch "^(?i:y|yes)$") {
            throw "Installation cancelled."
        }
    } else {
        New-Item -ItemType Directory -Force -Path $installPath | Out-Null
    }

    $TempPayload = Join-Path ([IO.Path]::GetTempPath()) ("WendaXitog-payload-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $TempPayload | Out-Null
    Write-Stage "Preparing application payload"
    Expand-Archive -LiteralPath $packagePath -DestinationPath $TempPayload -Force
    Copy-Payload $TempPayload $installPath

    if (-not $SkipRuntimeInstall) {
        Invoke-ProjectScript $installPath "install.ps1"
    }
    if (-not $SkipSetup) {
        Invoke-ProjectScript $installPath "setup.ps1"
    }

    if (-not $SkipShortcuts) {
        Create-Shortcuts $installPath
    }

    if (-not $SkipStart) {
        Invoke-ProjectScript $installPath "start.ps1"
    }

    Write-Host ""
    Write-Host "$AppName is installed at: $installPath" -ForegroundColor Green
    Write-Host "Use the desktop shortcut to start it next time."
    exit 0
} catch {
    Write-Host ""
    Write-Error $_
    exit 1
} finally {
    if ($TempPayload -and (Test-Path -LiteralPath $TempPayload)) {
        Remove-Item -LiteralPath $TempPayload -Recurse -Force -ErrorAction SilentlyContinue
    }
}
