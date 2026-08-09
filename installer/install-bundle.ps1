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
    [string]$InstallPath = "",
    [string]$ApiKey = "",
    [string]$SourcePath = "",
    [switch]$NoGui
)

$ErrorActionPreference = "Stop"
$AppName = "WendaXitog"
$TempPayload = $null
$script:FormsAvailable = $false
$script:ProgressForm = $null
$script:ProgressLabel = $null

try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $script:FormsAvailable = $true
} catch {
    $script:FormsAvailable = $false
}

function Write-Stage([string]$Message) {
    Write-Host ""
    Write-Host ("==> " + $Message) -ForegroundColor Cyan
    if ($script:ProgressLabel) {
        $script:ProgressLabel.Text = $Message
        [System.Windows.Forms.Application]::DoEvents()
    }
}

function Show-InstallerMessage([string]$Message, [string]$Title = $AppName) {
    if ($script:FormsAvailable) {
        [void][System.Windows.Forms.MessageBox]::Show(
            $Message,
            $Title,
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        )
    } else {
        Write-Host $Message
    }
}

function Show-InstallerError([string]$Message) {
    if ($script:FormsAvailable) {
        [void][System.Windows.Forms.MessageBox]::Show(
            $Message,
            "$AppName Installer",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        )
    } else {
        Write-Error $Message
    }
}

function Get-Confirmation([string]$Message) {
    if ($script:FormsAvailable) {
        $answer = [System.Windows.Forms.MessageBox]::Show(
            $Message,
            "$AppName Installer",
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Question
        )
        return $answer -eq [System.Windows.Forms.DialogResult]::Yes
    }

    $answer = Read-Host "$Message [y/N]"
    return $answer -match "^(?i:y|yes)$"
}

function New-ProgressForm {
    if (-not $script:FormsAvailable) { return $null }

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "$AppName Installer"
    $form.ClientSize = New-Object System.Drawing.Size(520, 130)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.ControlBox = $false
    $form.TopMost = $true

    $label = New-Object System.Windows.Forms.Label
    $label.AutoSize = $false
    $label.TextAlign = "MiddleCenter"
    $label.Dock = "Fill"
    $label.Text = "Preparing..."
    $label.Font = New-Object System.Drawing.Font("Segoe UI", 11)
    $form.Controls.Add($label)

    $script:ProgressForm = $form
    $script:ProgressLabel = $label
    $form.Show()
    [System.Windows.Forms.Application]::DoEvents()
    return $form
}

function Close-ProgressForm {
    if ($script:ProgressForm) {
        $script:ProgressForm.Close()
        $script:ProgressForm.Dispose()
        $script:ProgressForm = $null
        $script:ProgressLabel = $null
    }
}

function Get-InstallerInputs([string]$DefaultInstallPath) {
    if (-not $script:FormsAvailable -or $NoGui) { return $null }

    $state = @{
        Cancelled = $true
        InstallPath = $DefaultInstallPath
        ApiKey = ""
        SourcePath = ""
    }

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "$AppName Installer"
    $form.ClientSize = New-Object System.Drawing.Size(700, 300)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $installLabel = New-Object System.Windows.Forms.Label
    $installLabel.Text = "Install folder"
    $installLabel.Location = New-Object System.Drawing.Point(20, 22)
    $installLabel.Size = New-Object System.Drawing.Size(135, 24)
    $form.Controls.Add($installLabel)

    $installBox = New-Object System.Windows.Forms.TextBox
    $installBox.Text = $DefaultInstallPath
    $installBox.Location = New-Object System.Drawing.Point(160, 18)
    $installBox.Size = New-Object System.Drawing.Size(430, 24)
    $form.Controls.Add($installBox)

    $installBrowse = New-Object System.Windows.Forms.Button
    $installBrowse.Text = "Browse..."
    $installBrowse.Location = New-Object System.Drawing.Point(600, 17)
    $installBrowse.Size = New-Object System.Drawing.Size(80, 26)
    $installBrowse.Add_Click({
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.SelectedPath = $installBox.Text
        if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
            $installBox.Text = $dialog.SelectedPath
        }
        $dialog.Dispose()
    })
    $form.Controls.Add($installBrowse)

    $keyLabel = New-Object System.Windows.Forms.Label
    $keyLabel.Text = "DeepSeek API key"
    $keyLabel.Location = New-Object System.Drawing.Point(20, 72)
    $keyLabel.Size = New-Object System.Drawing.Size(135, 24)
    $form.Controls.Add($keyLabel)

    $keyBox = New-Object System.Windows.Forms.TextBox
    $keyBox.UseSystemPasswordChar = $true
    $keyBox.Location = New-Object System.Drawing.Point(160, 68)
    $keyBox.Size = New-Object System.Drawing.Size(520, 24)
    $form.Controls.Add($keyBox)

    $keyHint = New-Object System.Windows.Forms.Label
    $keyHint.Text = "Leave blank for Mock mode; real answers require a DeepSeek key."
    $keyHint.ForeColor = [System.Drawing.Color]::DimGray
    $keyHint.Location = New-Object System.Drawing.Point(160, 94)
    $keyHint.Size = New-Object System.Drawing.Size(520, 24)
    $form.Controls.Add($keyHint)

    $sourceLabel = New-Object System.Windows.Forms.Label
    $sourceLabel.Text = "Enterprise source folder"
    $sourceLabel.Location = New-Object System.Drawing.Point(20, 137)
    $sourceLabel.Size = New-Object System.Drawing.Size(135, 38)
    $form.Controls.Add($sourceLabel)

    $sourceBox = New-Object System.Windows.Forms.TextBox
    $sourceBox.Location = New-Object System.Drawing.Point(160, 134)
    $sourceBox.Size = New-Object System.Drawing.Size(430, 24)
    $form.Controls.Add($sourceBox)

    $sourceBrowse = New-Object System.Windows.Forms.Button
    $sourceBrowse.Text = "Browse..."
    $sourceBrowse.Location = New-Object System.Drawing.Point(600, 133)
    $sourceBrowse.Size = New-Object System.Drawing.Size(80, 26)
    $sourceBrowse.Add_Click({
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
            $sourceBox.Text = $dialog.SelectedPath
        }
        $dialog.Dispose()
    })
    $form.Controls.Add($sourceBrowse)

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = "Cancel"
    $cancel.Location = New-Object System.Drawing.Point(500, 235)
    $cancel.Size = New-Object System.Drawing.Size(85, 32)
    $cancel.Add_Click({
        $state.Cancelled = $true
        $form.Close()
    })
    $form.Controls.Add($cancel)

    $install = New-Object System.Windows.Forms.Button
    $install.Text = "Install"
    $install.Location = New-Object System.Drawing.Point(595, 235)
    $install.Size = New-Object System.Drawing.Size(85, 32)
    $install.Add_Click({
        if (-not $installBox.Text.Trim()) {
            [void][System.Windows.Forms.MessageBox]::Show("Choose an install folder first.", "$AppName Installer")
            return
        }
        try {
            $state.InstallPath = [IO.Path]::GetFullPath($installBox.Text.Trim())
        } catch {
            [void][System.Windows.Forms.MessageBox]::Show("The install folder is not valid.", "$AppName Installer")
            return
        }
        $state.ApiKey = $keyBox.Text.Trim()
        $state.SourcePath = $sourceBox.Text.Trim()
        $state.Cancelled = $false
        $form.Close()
    })
    $form.Controls.Add($install)
    $form.AcceptButton = $install
    $form.CancelButton = $cancel

    [void]$form.ShowDialog()
    $form.Dispose()
    if ($state.Cancelled) { return $null }
    return [pscustomobject]@{
        InstallPath = $state.InstallPath
        ApiKey = $state.ApiKey
        SourcePath = $state.SourcePath
    }
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

    if (-not (Get-Confirmation "$DisplayName was not found. Install it automatically with winget?")) {
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

function Write-LocalConfiguration([string]$ProjectRoot, [string]$ConfiguredApiKey, [string]$ConfiguredSourcePath) {
    Write-Stage "Writing local configuration"
    $backendDir = Join-Path $ProjectRoot "backend"
    $frontendDir = Join-Path $ProjectRoot "frontend"
    $backendEnv = Join-Path $backendDir ".env"
    $frontendEnv = Join-Path $frontendDir ".env.local"

    if (-not (Test-Path -LiteralPath $backendEnv)) {
        Copy-Item -LiteralPath (Join-Path $backendDir ".env.example") -Destination $backendEnv
    }
    if (-not (Test-Path -LiteralPath $frontendEnv)) {
        Copy-Item -LiteralPath (Join-Path $frontendDir ".env.local.example") -Destination $frontendEnv
    }

    $currentKey = Get-DotEnvValue $backendEnv "RAG_DEEPSEEK_API_KEY"
    $currentSource = Get-DotEnvValue $backendEnv "RAG_KNOWLEDGE_SOURCE_ROOT"
    $effectiveSource = $ConfiguredSourcePath
    if (-not $effectiveSource) { $effectiveSource = $currentSource }
    if (-not $effectiveSource -or $effectiveSource -match "path/to/enterprise-library") {
        $effectiveSource = Join-Path $backendDir "app\data\source_library"
    }
    $effectiveSource = [IO.Path]::GetFullPath($effectiveSource)
    New-Item -ItemType Directory -Force -Path $effectiveSource | Out-Null
    Set-DotEnvValue $backendEnv "RAG_KNOWLEDGE_SOURCE_ROOT" ($effectiveSource -replace "\\", "/")

    if ($ConfiguredApiKey) {
        Set-DotEnvValue $backendEnv "RAG_DEFAULT_LLM_PROVIDER" "deepseek"
        Set-DotEnvValue $backendEnv "RAG_DEEPSEEK_API_KEY" $ConfiguredApiKey
        Set-DotEnvValue $backendEnv "RAG_DEEPSEEK_BASE_URL" "https://api.deepseek.com"
        Set-DotEnvValue $backendEnv "RAG_DEEPSEEK_MODEL" "deepseek-v4-flash"
    } elseif ($currentKey) {
        Set-DotEnvValue $backendEnv "RAG_DEFAULT_LLM_PROVIDER" "deepseek"
        Set-DotEnvValue $backendEnv "RAG_DEEPSEEK_MODEL" "deepseek-v4-flash"
    } else {
        Set-DotEnvValue $backendEnv "RAG_DEFAULT_LLM_PROVIDER" "mock"
    }
    Set-DotEnvValue $frontendEnv "NEXT_PUBLIC_API_BASE" "http://localhost:8000"
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
    $arguments = @("-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $scriptPath)
    $process = Start-Process -FilePath powershell.exe -ArgumentList $arguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    while (-not $process.HasExited) {
        if ($script:ProgressForm) {
            [System.Windows.Forms.Application]::DoEvents()
        }
        Start-Sleep -Milliseconds 250
    }
    if ($process.ExitCode -ne 0) {
        throw "$ScriptName failed (exit code $($process.ExitCode))."
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

    $defaultInstallPath = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) $AppName
    if ($NoGui) {
        $inputs = [pscustomobject]@{
            InstallPath = if ($InstallPath) { $InstallPath } else { $defaultInstallPath }
            ApiKey = $ApiKey
            SourcePath = $SourcePath
        }
    } elseif ($script:FormsAvailable) {
        $inputs = Get-InstallerInputs $defaultInstallPath
        if (-not $inputs) { throw "Installation cancelled." }
    } else {
        $requestedPath = if ($InstallPath) { $InstallPath } else { Read-Host "Installation folder [$defaultInstallPath]" }
        if (-not $requestedPath) { $requestedPath = $defaultInstallPath }
        $inputs = [pscustomobject]@{
            InstallPath = $requestedPath
            ApiKey = if ($ApiKey) { $ApiKey } else { Read-Host "DeepSeek API key (blank uses Mock)" }
            SourcePath = if ($SourcePath) { $SourcePath } else { Read-Host "Enterprise source folder (blank uses the local default)" }
        }
    }

    $progress = New-ProgressForm
    if (-not $SkipRuntimeInstall) {
        Write-Stage "Checking prerequisites"
        Ensure-Prerequisites
    }

    $installPath = [IO.Path]::GetFullPath($inputs.InstallPath)
    if (Test-Path -LiteralPath $installPath) {
        if (-not (Get-Confirmation "The folder already exists. Update it and preserve existing configuration?")) {
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
        Write-LocalConfiguration $installPath $inputs.ApiKey $inputs.SourcePath
    }

    if (-not $SkipShortcuts) {
        Create-Shortcuts $installPath
    }

    if (-not $SkipStart) {
        Invoke-ProjectScript $installPath "start.ps1"
    }

    Close-ProgressForm
    Write-Host ""
    Write-Host "$AppName is installed at: $installPath" -ForegroundColor Green
    $successMessage = $AppName + " is installed at:" + [Environment]::NewLine + $installPath + [Environment]::NewLine + [Environment]::NewLine + "A desktop shortcut was created. Start the app from the shortcut."
    Show-InstallerMessage $successMessage
    exit 0
} catch {
    Close-ProgressForm
    $message = $_.Exception.Message
    Write-Error $_
    Show-InstallerError $message
    exit 1
} finally {
    if ($TempPayload -and (Test-Path -LiteralPath $TempPayload)) {
        Remove-Item -LiteralPath $TempPayload -Recurse -Force -ErrorAction SilentlyContinue
    }
}
