# Saarthi installer for Windows 10/11.
#
#   Double-click install.bat, or in PowerShell:
#   .\install.ps1               install (or update) and start Saarthi
#   .\install.ps1 -Autostart    ...and start it with Windows
#   .\install.ps1 -Uninstall    remove the app (your notes/reminders are kept)
#
# Nothing needs admin rights: everything goes in your user profile.
param([switch]$Autostart, [switch]$Uninstall)
$ErrorActionPreference = "Stop"

$Repo    = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppHome = Join-Path $env:LOCALAPPDATA "Saarthi"
$Venv    = Join-Path $AppHome "venv"
$StartMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Saarthi.lnk"
$Desktop   = Join-Path ([Environment]::GetFolderPath("Desktop")) "Saarthi.lnk"

function Say($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "!!  $m" -ForegroundColor Yellow }

if ($Uninstall) {
    Say "Removing Saarthi (your data in %APPDATA%\Saarthi is kept)"
    Get-Process pythonw, python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "$Venv*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $AppHome, $StartMenu, $Desktop -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Saarthi" -ErrorAction SilentlyContinue
    Say "Done."
    exit 0
}

# ---------- Python ----------
$Py = $null
foreach ($cand in @(@("py", "-3"), @("python"), @("python3"))) {
    try {
        $ok = & $cand[0] $cand[1..9] -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
        if ($ok -eq "True") { $Py = $cand; break }
    } catch { }
}
if (-not $Py) {
    Warn "Python 3.10+ is needed."
    Warn "Install it from https://www.python.org/downloads/windows/ and tick 'Add python.exe to PATH',"
    Warn "or run:  winget install Python.Python.3.12"
    Read-Host "Press Enter to close"
    exit 1
}
Say ("Using " + (& $Py[0] $Py[1..9] --version))

# ---------- remove the old "DeskBuddy" install (the app was renamed to Saarthi) ----------
$OldHome = Join-Path $env:LOCALAPPDATA "DeskBuddy"
if (Test-Path $OldHome) {
    Say "Removing the old DeskBuddy install (your notes and settings move over to Saarthi)"
    Get-Process pythonw, python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "$OldHome*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $OldHome -ErrorAction SilentlyContinue
    foreach ($old in @((Join-Path ([Environment]::GetFolderPath("Programs")) "DeskBuddy.lnk"),
                       (Join-Path ([Environment]::GetFolderPath("Desktop")) "DeskBuddy.lnk"))) {
        Remove-Item -Force $old -ErrorAction SilentlyContinue
    }
}

# ---------- install into a private virtualenv ----------
Say "Installing into $AppHome"
New-Item -ItemType Directory -Force -Path $AppHome | Out-Null
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    & $Py[0] $Py[1..9] -m venv $Venv
}
$VPy  = Join-Path $Venv "Scripts\python.exe"
$VPyw = Join-Path $Venv "Scripts\pythonw.exe"
& $VPy -m pip install --quiet --upgrade pip
& $VPy -m pip install --quiet --upgrade $Repo
if ($LASTEXITCODE -ne 0) { Warn "Install failed."; Read-Host "Press Enter to close"; exit 1 }

# ---------- shortcuts ----------
$Icon = Join-Path $AppHome "saarthi.ico"
Copy-Item (Join-Path $Repo "src\saarthi\assets\icon.ico") $Icon -Force
$shell = New-Object -ComObject WScript.Shell
foreach ($path in @($StartMenu, $Desktop)) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $VPyw
    $lnk.Arguments = "-m saarthi"
    $lnk.IconLocation = $Icon
    $lnk.Description = "Your animated desktop companion"
    $lnk.Save()
}
Say "Added Saarthi to the Start menu and Desktop"

if ($Autostart) {
    & $VPy -c "from saarthi.system import set_autostart; set_autostart(True)"
    Say "Saarthi will start with Windows"
}

Say "Starting Saarthi (double-click it for reminders & notes, right-click for the menu)"
Start-Process $VPyw -ArgumentList "-m", "saarthi"
