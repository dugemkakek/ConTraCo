# create_desktop_shortcut.ps1 - drop a one-click launcher on the user's Desktop.
# Usage (PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\create_desktop_shortcut.ps1

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$root      = Resolve-Path (Join-Path $scriptDir "..")
$target    = Join-Path $root "scripts\start.cmd"
$iconFile  = Join-Path $root "apps\web\public\favicon.ico"

if (-not (Test-Path $target)) {
    Write-Error "start.cmd not found at $target"
    exit 1
}

$desktop = [Environment]::GetFolderPath("DesktopDirectory")
$shell   = New-Object -ComObject WScript.Shell
$shortcut = Join-Path $desktop "Confluence Terminal.lnk"

$shell.CreateShortcut($shortcut) | Out-Null
$shortObj = (Get-Content $shortcut -Raw) # not used; below is the real API

$s = $shell.CreateShortcut($shortcut)
$s.TargetPath       = $target
$s.WorkingDirectory = $root.Path
$s.IconLocation     = if (Test-Path $iconFile) { $iconFile } else { "$env:SystemRoot\system32\shell32.dll,12" }
$s.Description      = "Confluence Trading Consultant - one-click launcher"
$s.WindowStyle      = 1
$s.Save()

Write-Host "Shortcut created: $shortcut"
Write-Host "Double-click to start the app."
exit 0
