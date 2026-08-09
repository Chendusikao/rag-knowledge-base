[CmdletBinding()]
param(
    [string]$Version = "v0.1.0",
    [string]$OutputDirectory = "",
    [switch]$KeepWork
)

$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Version = $Version.Trim()
if ($Version -notmatch "^v?\d+\.\d+\.\d+$") {
    throw "Version must look like v0.1.0."
}
if (-not $Version.StartsWith("v")) { $Version = "v$Version" }

$outputRoot = if ($OutputDirectory) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    Join-Path $RootDir "dist"
}
$outputRoot = (New-Item -ItemType Directory -Force -Path $outputRoot).FullName

$git = Get-Command git.exe -ErrorAction SilentlyContinue
$tar = Get-Command tar.exe -ErrorAction SilentlyContinue
$iexpress = Join-Path $env:SystemRoot "System32\iexpress.exe"
if (-not $git) { throw "Git is required to build the installer." }
if (-not $tar) { throw "Windows tar.exe is required to build the installer." }
if (-not (Test-Path -LiteralPath $iexpress)) { throw "IExpress is not available at $iexpress." }

$workRoot = Join-Path ([IO.Path]::GetTempPath()) ("WendaXitog-installer-" + [Guid]::NewGuid().ToString("N"))
$projectStage = Join-Path $workRoot "project"
$iexpressStage = Join-Path $workRoot "iexpress"
$payloadZip = Join-Path $iexpressStage "payload.zip"
$sedPath = Join-Path $workRoot "package.sed"
$outputExe = Join-Path $outputRoot ("WendaXitog-Setup-{0}.exe" -f $Version)

function Is-Excluded([string]$RelativePath) {
    $path = $RelativePath.Replace("\", "/")
    return (
        $path -eq "backend/.env" -or
        $path -eq "frontend/.env.local" -or
        $path.StartsWith("backend/.venv/", [StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("backend/app/data/", [StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("backend/models/", [StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("backend/.pytest_cache/", [StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("frontend/node_modules/", [StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith("frontend/.next/", [StringComparison]::OrdinalIgnoreCase) -or
        $path.StartsWith(".runtime/", [StringComparison]::OrdinalIgnoreCase) -or
        $path -match "(^|/)([^/]+)\.log$"
    )
}

try {
    New-Item -ItemType Directory -Force -Path $projectStage, $iexpressStage | Out-Null
    Write-Host "Collecting source files from the working tree..." -ForegroundColor Cyan

    $files = @(& $git.Source -C $RootDir ls-files -co --exclude-standard)
    if ($LASTEXITCODE -ne 0 -or $files.Count -eq 0) {
        throw "Could not enumerate project files."
    }
    foreach ($relative in $files) {
        if (-not $relative -or (Is-Excluded $relative)) { continue }
        $source = Join-Path $RootDir $relative
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { continue }
        $destination = Join-Path $projectStage $relative
        $parent = Split-Path -Parent $destination
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }

    $archiveEntries = @(Get-ChildItem -LiteralPath $projectStage -Force)
    if ($archiveEntries.Count -eq 0) { throw "The installer payload is empty." }
    Compress-Archive -Path $archiveEntries.FullName -DestinationPath $payloadZip -CompressionLevel Optimal -Force

    Copy-Item -LiteralPath (Join-Path $RootDir "installer\iexpress-entry.cmd") -Destination (Join-Path $iexpressStage "iexpress-entry.cmd") -Force
    Copy-Item -LiteralPath (Join-Path $RootDir "installer\install-bundle.ps1") -Destination (Join-Path $iexpressStage "install-bundle.ps1") -Force

    $sourceFiles = @(Get-ChildItem -LiteralPath $iexpressStage -File | Sort-Object Name)
    $sedLines = @(
        "[Version]",
        "Class=IEXPRESS",
        "SEDVersion=3",
        "[Options]",
        "PackagePurpose=InstallApp",
        "ShowInstallProgramWindow=1",
        "HideExtractAnimation=1",
        "UseLongFileName=1",
        "InsideCompressed=1",
        "CAB_FixedSize=0",
        "CAB_ResvCodeSigning=0",
        "RebootMode=N",
        "InstallPrompt=",
        "DisplayLicense=",
        "FinishMessage=%FinishMessage%",
        "TargetName=%TargetName%",
        "FriendlyName=%FriendlyName%",
        "AppLaunched=%AppLaunched%",
        "PostInstallCmd=<None>",
        "AdminQuietInstCmd=",
        "UserQuietInstCmd=",
        "SourceFiles=SourceFiles",
        "[SourceFiles]",
        "SourceFiles0=$iexpressStage",
        "[SourceFiles0]"
    )
    for ($index = 0; $index -lt $sourceFiles.Count; $index++) {
        $sedLines += "%FILE$index%="
    }
    $sedLines += @(
        "[Strings]",
        "FinishMessage=Setup finished. Use the WendaXitog desktop shortcut to start the application.",
        "TargetName=$outputExe",
        "FriendlyName=WendaXitog $Version Windows Installer",
        "AppLaunched=iexpress-entry.cmd"
    )
    for ($index = 0; $index -lt $sourceFiles.Count; $index++) {
        $sedLines += "FILE$index=$($sourceFiles[$index].Name)"
    }
    [IO.File]::WriteAllLines($sedPath, [string[]]$sedLines, [Text.Encoding]::ASCII)

    if (Test-Path -LiteralPath $outputExe) {
        Remove-Item -LiteralPath $outputExe -Force
    }
    Write-Host "Building $outputExe ..." -ForegroundColor Cyan
    # IExpress is a GUI subsystem executable. Invoke it directly so PowerShell
    # passes the SED path as its third argument; Start-Process can drop that
    # argument on some Windows builds and open the wizard instead.
    & $iexpress /N /Q $sedPath
    $deadline = (Get-Date).AddSeconds(45)
    while (-not (Test-Path -LiteralPath $outputExe) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-Path -LiteralPath $outputExe)) {
        throw "IExpress completed without creating $outputExe."
    }

    $sizeMb = [math]::Round(((Get-Item -LiteralPath $outputExe).Length / 1MB), 2)
    Write-Host "Installer created: $outputExe ($sizeMb MB)" -ForegroundColor Green
} finally {
    if (-not $KeepWork -and $workRoot -and (Test-Path -LiteralPath $workRoot)) {
        Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
    } elseif ($KeepWork -and $workRoot) {
        Write-Host "Kept build diagnostics at: $workRoot" -ForegroundColor Yellow
    }
}
