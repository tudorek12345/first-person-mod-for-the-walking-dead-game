[CmdletBinding()]
param([string]$GamePath,[string]$PayloadRoot,[switch]$PrepareOnly,[string]$OutputRoot,[string]$ArchiverPath,[switch]$NoPrompt)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Installer.Core.ps1')
$transcript=$false
try {
    $dataRoot=Get-ModDataRoot
    New-Directory (Join-Path $dataRoot 'logs')
    $log=Join-Path (Join-Path $dataRoot 'logs') ('installer-'+(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')+'.log')
    Start-Transcript -Path $log -Append | Out-Null; $transcript=$true
    $game=Resolve-GamePath $GamePath -NoPrompt:$NoPrompt
    if ($OutputRoot) { $OutputRoot=Assert-OutputOutsideGame $OutputRoot $game }
    if (-not $PrepareOnly) { Assert-GameClosed }
    $payload=Get-InstallerPayloadRoot $PSScriptRoot $PayloadRoot
    $manifest=Read-PayloadManifest $payload
    $tool=Get-Archiver $dataRoot $ArchiverPath
    $work=Join-Path (Join-Path $dataRoot 'work') ([guid]::NewGuid().ToString('N'))
    New-Directory $work
    if (-not $OutputRoot) { $OutputRoot=Join-Path $work 'prepared' }
    $OutputRoot=Assert-OutputOutsideGame $OutputRoot $game
    New-Directory $OutputRoot
    $records=@()
    foreach ($episode in $manifest.episodes) { $records+=New-EpisodePatch $game $episode $payload $tool $work $OutputRoot }
    [pscustomobject]@{format=1;build=$manifest.build;game=$game;episodes=$records} |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputRoot 'prepared-manifest.json') -Encoding UTF8
    if ($PrepareOnly) {
        Write-Host "Prepared and round-trip verified all five episodes. Game files were not changed. Output: $OutputRoot"
    } else {
        $backups=Install-PreparedPatches $game $records $dataRoot
        Write-Host "Installed first-person mode for all five episodes in: $game"
        Write-Host "Existing patches backed up to: $backups"
        Write-Host 'Start the game through Steam. F6: camera toggle. F8: recovery. Alt: original interaction view.'
    }
    Write-Host "Logs: $(Join-Path $dataRoot 'logs')"
    if ($transcript) { Stop-Transcript | Out-Null; $transcript=$false }
    exit 0
} catch {
    Write-Host "Installation stopped: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception -is [UnauthorizedAccessException]) { Write-Host 'Windows denied write access. Right-click Install.cmd and choose Run as administrator.' }
    if ($transcript) { Stop-Transcript | Out-Null }
    exit 1
}
