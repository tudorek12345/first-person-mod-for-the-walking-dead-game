[CmdletBinding()]
param([string]$GamePath,[switch]$NoPrompt)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Installer.Core.ps1')
$transcript=$false
try {
    $dataRoot=Get-ModDataRoot
    New-Directory (Join-Path $dataRoot 'logs')
    $log=Join-Path (Join-Path $dataRoot 'logs') ('uninstaller-'+(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')+'.log')
    Start-Transcript -Path $log -Append | Out-Null; $transcript=$true
    $game=Resolve-GamePath $GamePath -NoPrompt:$NoPrompt
    Uninstall-Mod $game $dataRoot
    Write-Host 'Other game files, saves, mods, and diagnostic logs were kept.'
    Stop-Transcript | Out-Null; $transcript=$false
    exit 0
} catch {
    Write-Host "Uninstall stopped: $($_.Exception.Message)" -ForegroundColor Red
    if ($transcript) { Stop-Transcript | Out-Null }
    exit 1
}
