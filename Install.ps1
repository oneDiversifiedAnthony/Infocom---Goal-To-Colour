# ============================================================================
# Install.ps1 -- oneDiversified World Cup Colour sACN
#
# Dependency installer:
#   1. Installs Python 3.14 (if not already present) via winget
#   2. Installs all pip dependencies (sacn, pygame-ce, Pillow, numpy, sounddevice)
#   3. Updates config.ini [dependencies] section when complete
#
# Run via Launch.bat or: powershell -ExecutionPolicy Bypass -File Install.ps1
# ============================================================================

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $AppDir

$ConfigPath   = Join-Path $AppDir "config.ini"
$PythonTarget = "3.14"

# ── pip packages: import_name = pip_name ────────────────────────────────────
$PipPackages = @(
    @{ Import = "sacn";        Pip = "sacn"        },
    @{ Import = "pygame";      Pip = "pygame-ce"   },
    @{ Import = "PIL";         Pip = "Pillow"      },
    @{ Import = "numpy";       Pip = "numpy"       },
    @{ Import = "sounddevice"; Pip = "sounddevice" }
)

# ── Helpers ─────────────────────────────────────────────────────────────────

function Write-Section($title) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Get-PythonExe {
    <#
    .SYNOPSIS
        Finds a working Python 3.14+ executable. Returns $null if none found.
    #>
    foreach ($candidate in @("python", "python3", "py")) {
        try {
            $ver = & $candidate --version 2>&1
            if ($ver -match "Python (\d+\.\d+)") {
                $found = $Matches[1]
                if ([version]$found -ge [version]$PythonTarget) {
                    return $candidate
                }
            }
        } catch { }
    }
    # Check common install locations
    $paths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
        "C:\Python314\python.exe",
        "$env:ProgramFiles\Python314\python.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) {
            try {
                $ver = & $p --version 2>&1
                if ($ver -match "Python (\d+\.\d+)" -and [version]$Matches[1] -ge [version]$PythonTarget) {
                    return $p
                }
            } catch { }
        }
    }
    return $null
}

function Update-ConfigDependencies {
    param(
        [string]$Status,           # "installed" or "failed"
        [string]$PythonVersion,
        [string]$PythonPath
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    # Read existing config.ini (or start empty)
    $lines = @()
    if (Test-Path $ConfigPath) {
        $lines = Get-Content $ConfigPath
    }

    # Remove any existing [dependencies] section
    $newLines = @()
    $inDeps = $false
    foreach ($line in $lines) {
        if ($line -match '^\[dependencies\]') {
            $inDeps = $true
            continue
        }
        if ($inDeps -and $line -match '^\[') {
            $inDeps = $false
        }
        if (-not $inDeps) {
            $newLines += $line
        }
    }

    # Strip trailing blank lines
    while ($newLines.Count -gt 0 -and $newLines[-1].Trim() -eq "") {
        $newLines = $newLines[0..($newLines.Count - 2)]
    }

    # Append [dependencies] section
    $newLines += ""
    $newLines += "[dependencies]"
    $newLines += "status = $Status"
    $newLines += "python_version = $PythonVersion"
    $newLines += "python_path = $PythonPath"
    $newLines += "installed_on = $timestamp"

    $pipList = ($PipPackages | ForEach-Object { $_.Pip }) -join ", "
    $newLines += "packages = $pipList"
    $newLines += ""

    $newLines | Set-Content $ConfigPath -Encoding UTF8
}

# ── 1. Install Python ──────────────────────────────────────────────────────

Write-Section "Python $PythonTarget"

$pythonExe = Get-PythonExe

if ($pythonExe) {
    $verOut = & $pythonExe --version 2>&1
    Write-Host "  Already installed: $verOut" -ForegroundColor Green
    Write-Host "  Path: $pythonExe" -ForegroundColor DarkGray
} else {
    Write-Host "  Python $PythonTarget not found. Installing via winget..." -ForegroundColor Yellow

    try {
        # Try winget first (preferred on Windows 11)
        $wingetAvailable = Get-Command winget -ErrorAction SilentlyContinue
        if ($wingetAvailable) {
            Write-Host "  Running: winget install Python.Python.3.14" -ForegroundColor DarkGray
            winget install --id Python.Python.3.14 --accept-source-agreements --accept-package-agreements --silent
        } else {
            # Fallback: download installer from python.org
            Write-Host "  winget not available. Downloading from python.org..." -ForegroundColor Yellow
            $installerUrl = "https://www.python.org/ftp/python/3.14.0/python-3.14.0-amd64.exe"
            $installerPath = Join-Path $env:TEMP "python-3.14-installer.exe"

            Write-Host "  Downloading installer..." -ForegroundColor DarkGray
            Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing

            Write-Host "  Running installer (silent, includes pip, adds to PATH)..." -ForegroundColor DarkGray
            Start-Process -FilePath $installerPath -ArgumentList `
                "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1", "Include_tcltk=1" `
                -Wait -NoNewWindow

            Remove-Item $installerPath -ErrorAction SilentlyContinue
        }

        # Refresh PATH so we can find the new python
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                     [System.Environment]::GetEnvironmentVariable("Path", "User")

        $pythonExe = Get-PythonExe
        if (-not $pythonExe) {
            Write-Host ""
            Write-Host "  FAILED: Python $PythonTarget could not be found after install." -ForegroundColor Red
            Write-Host "  Please install Python $PythonTarget manually from https://www.python.org" -ForegroundColor Red
            Update-ConfigDependencies -Status "failed" -PythonVersion "not found" -PythonPath ""
            Read-Host "  Press Enter to close"
            exit 1
        }

        $verOut = & $pythonExe --version 2>&1
        Write-Host "  Installed: $verOut" -ForegroundColor Green
    } catch {
        Write-Host "  FAILED: $_" -ForegroundColor Red
        Update-ConfigDependencies -Status "failed" -PythonVersion "error" -PythonPath ""
        Read-Host "  Press Enter to close"
        exit 1
    }
}

# ── 2. Upgrade pip ──────────────────────────────────────────────────────────

Write-Section "pip (upgrade)"

Write-Host "  Ensuring pip is up to date..." -ForegroundColor DarkGray
& $pythonExe -m pip install --upgrade pip 2>&1 | ForEach-Object {
    Write-Host "    $_" -ForegroundColor DarkGray
}

# ── 3. Install pip packages ────────────────────────────────────────────────

Write-Section "Python Packages"

$allOk = $true

foreach ($pkg in $PipPackages) {
    $importName = $pkg.Import
    $pipName    = $pkg.Pip

    # Check if already importable
    $check = & $pythonExe -c "import $importName" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK (installed): $pipName" -ForegroundColor DarkGray
        continue
    }

    Write-Host "  Installing $pipName ..." -ForegroundColor Yellow -NoNewline
    & $pythonExe -m pip install $pipName 2>&1 | Out-Null

    # Verify
    $check = & $pythonExe -c "import $importName" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "    Try manually: $pythonExe -m pip install $pipName" -ForegroundColor Red
        $allOk = $false
    }
}

# ── 4. Update config.ini ───────────────────────────────────────────────────

Write-Section "Configuration"

$pyVer = (& $pythonExe --version 2>&1) -replace "Python ", ""
$pyPath = (Get-Command $pythonExe -ErrorAction SilentlyContinue).Source
if (-not $pyPath) { $pyPath = $pythonExe }

if ($allOk) {
    Update-ConfigDependencies -Status "installed" -PythonVersion $pyVer -PythonPath $pyPath
    Write-Host "  config.ini updated: [dependencies] status = installed" -ForegroundColor Green
} else {
    Update-ConfigDependencies -Status "failed" -PythonVersion $pyVer -PythonPath $pyPath
    Write-Host "  config.ini updated: [dependencies] status = failed" -ForegroundColor Red
}

# ── Done ────────────────────────────────────────────────────────────────────

Write-Host ""
if ($allOk) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  All dependencies installed OK" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  Some dependencies failed to install" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Read-Host "  Press Enter to close"
    exit 1
}

Write-Host ""
