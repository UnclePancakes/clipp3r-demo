$ErrorActionPreference = "Stop"
$shortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "CLIPP3R - Local.lnk"
if (Test-Path -LiteralPath $shortcutPath) {
    $existingShortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
    $expectedTarget = Join-Path $PSScriptRoot "Run-CLIPP3R.bat"
    if ($existingShortcut.TargetPath -eq $expectedTarget) {
        Write-Host "Desktop shortcut already exists: $shortcutPath"
        exit 0
    }
    throw "A different shortcut already uses this name: $shortcutPath. Rename it before running setup."
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $PSScriptRoot "Run-CLIPP3R.bat"
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = "Start the private, local CLIPP3R video studio"
$shortcut.Save()

Write-Host "Created desktop shortcut: $shortcutPath"
