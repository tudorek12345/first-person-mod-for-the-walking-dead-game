# Windows PowerShell 5.1. No Python or compiler is needed by players.
Set-StrictMode -Version 2.0
$script:PatchName = '0_00_firstperson.ttarch'
$script:Episodes = @('default','WalkingDead102','WalkingDead103','WalkingDead104','WalkingDead105')
$script:ToolUrl = 'https://aluigi.altervista.org/papers/ttarchext.zip'
$script:ToolZipHash = 'F348FEF4E90348733994DF18ACA10F92E7DA87F43D4637359007CBC5B948827D'
$script:ToolExeHash = '8B8576610A9CD6E8598793879740DAD000E60856D35A9E465E382031532FA61A'

function Get-ModDataRoot {
    if (-not $env:LOCALAPPDATA) { throw 'Windows LOCALAPPDATA is unavailable.' }
    return [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'First-person-mode'))
}
function New-Directory([string]$Path) { [void][IO.Directory]::CreateDirectory($Path) }
function Get-Sha256([string]$Path) {
    $stream=[IO.File]::OpenRead($Path)
    $algorithm=[Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','') }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
function Assert-Within([string]$Path,[string]$Root) {
    $full=[IO.Path]::GetFullPath($Path)
    $boundary=[IO.Path]::GetFullPath($Root).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($boundary,[StringComparison]::OrdinalIgnoreCase)) { throw "Path outside expected directory: $full" }
    return $full
}
function Assert-OutputOutsideGame([string]$OutputRoot,[string]$Game) {
    $output=[IO.Path]::GetFullPath($OutputRoot).TrimEnd('\','/')
    $gameRoot=[IO.Path]::GetFullPath($Game).TrimEnd('\','/')
    if ($output.Equals($gameRoot,[StringComparison]::OrdinalIgnoreCase) -or
        $output.StartsWith($gameRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'OutputRoot must be outside the game folder. PrepareOnly never writes prepared archives into the game installation.'
    }
    return $output
}
function Assert-GameClosed {
    if (Get-Process -Name WalkingDead101 -ErrorAction SilentlyContinue) {
        throw 'Close The Walking Dead before installing or uninstalling. Your game was not stopped.'
    }
}
function Resolve-GamePath([string]$GamePath,[switch]$NoPrompt) {
    $candidates=New-Object 'System.Collections.Generic.List[string]'
    if ($GamePath) { $candidates.Add($GamePath.Trim('"')) }
    else {
        $steamRoots=New-Object 'System.Collections.Generic.List[string]'
        foreach ($key in @('HKCU:\Software\Valve\Steam','HKLM:\SOFTWARE\WOW6432Node\Valve\Steam')) {
            $item=Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
            if ($item) {
                foreach ($name in @('SteamPath','InstallPath')) {
                    $property=$item.PSObject.Properties[$name]
                    if ($property -and $property.Value) { $steamRoots.Add([string]$property.Value) }
                }
            }
        }
        if (${env:ProgramFiles(x86)}) { $steamRoots.Add((Join-Path ${env:ProgramFiles(x86)} 'Steam')) }
        foreach ($steam in $steamRoots.ToArray()) {
            $candidates.Add((Join-Path $steam 'steamapps\common\The Walking Dead'))
            $vdf=Join-Path $steam 'steamapps\libraryfolders.vdf'
            if (Test-Path -LiteralPath $vdf -PathType Leaf) {
                foreach ($match in [regex]::Matches([IO.File]::ReadAllText($vdf),'"path"\s+"([^"]+)"')) {
                    $library=$match.Groups[1].Value.Replace('\\','\')
                    $candidates.Add((Join-Path $library 'steamapps\common\The Walking Dead'))
                }
            }
        }
    }
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath (Join-Path $candidate 'WalkingDead101.exe') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $candidate 'Pack') -PathType Container)) {
            return [IO.Path]::GetFullPath($candidate).TrimEnd('\','/')
        }
    }
    if (-not $GamePath -and -not $NoPrompt) {
        Write-Host 'Steam could not be located automatically.'
        $chosen=Read-Host 'Paste the game folder containing WalkingDead101.exe'
        return Resolve-GamePath -GamePath $chosen -NoPrompt
    }
    throw 'Game folder not found. Use -GamePath with the folder containing WalkingDead101.exe and Pack (original Season One).'
}
function Get-InstallerPayloadRoot([string]$ScriptRoot,[string]$Requested) {
    if ($Requested) { return [IO.Path]::GetFullPath($Requested) }
    $local=Join-Path $ScriptRoot 'payload'
    if (Test-Path -LiteralPath $local -PathType Container) { return $local }
    return Join-Path (Split-Path -Parent $ScriptRoot) 'payload'
}
function Read-PayloadManifest([string]$PayloadRoot) {
    $manifestPath=Join-Path $PayloadRoot 'manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'Compiled release payload is missing. Download and extract the release ZIP, not the GitHub source-code ZIP.'
    }
    $manifest=[IO.File]::ReadAllText($manifestPath) | ConvertFrom-Json
    if ($manifest.format -ne 1 -or -not $manifest.build) { throw 'Unsupported payload manifest.' }
    $seen=@{}
    foreach ($episode in $manifest.episodes) {
        if ($script:Episodes -cnotcontains $episode.episode -or $seen.ContainsKey($episode.episode)) { throw 'Invalid or duplicate episode in payload.' }
        $seen[$episode.episode]=$true
        $files=@{}
        foreach ($entry in $episode.scripts) {
            $name=[string]$entry.name
            if ($name -cnotmatch '^(_system|module_visibility|fp_[a-z0-9_]+)\.lua$' -or $name -like 'fp_original_*' -or $files.ContainsKey($name)) {
                throw "Invalid payload script: $name"
            }
            if ([string]$entry.sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw "Missing SHA256: $name" }
            $file=Assert-Within (Join-Path (Join-Path $PayloadRoot $episode.episode) $name) $PayloadRoot
            if ((Get-Sha256 $file) -ne $entry.sha256) { throw "Release payload is damaged: $($episode.episode)/$name" }
            $bytes=[IO.File]::ReadAllBytes($file)
            if ($bytes.Length -lt 12 -or ([BitConverter]::ToString($bytes,0,12)) -ne '1B-4C-75-61-51-00-01-04-04-04-04-00') {
                throw "Payload is not original-game Lua bytecode: $name"
            }
            $files[$name]=$true
        }
        foreach ($required in @('_system.lua','module_visibility.lua','fp_main.lua','fp_generated.lua')) {
            if (-not $files.ContainsKey($required)) { throw "Payload is missing $required" }
        }
    }
    foreach ($name in $script:Episodes) { if (-not $seen.ContainsKey($name)) { throw "Payload is missing $name" } }
    return $manifest
}
function ConvertTo-NativeArgument([string]$Value) {
    $escaped=[regex]::Replace($Value,'(\\*)"','$1$1\"')
    $escaped=[regex]::Replace($escaped,'(\\+)$','$1$1')
    return '"'+$escaped+'"'
}
function Invoke-Archiver([string]$Tool,[string[]]$Arguments,[string]$WorkingDirectory) {
    $info=New-Object Diagnostics.ProcessStartInfo
    $info.FileName=$Tool
    $info.Arguments=($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $info.WorkingDirectory=$WorkingDirectory
    $info.UseShellExecute=$false; $info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true
    $process=New-Object Diagnostics.Process
    $process.StartInfo=$info
    [void]$process.Start()
    $outTask=$process.StandardOutput.ReadToEndAsync()
    $errTask=$process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $output=$outTask.Result+$errTask.Result
    $exitCode=$process.ExitCode
    $process.Dispose()
    if ($exitCode -ne 0) { throw "Archive tool failed ($exitCode): $output" }
    return $output
}
function Get-Archiver([string]$DataRoot,[string]$ExistingTool) {
    if ($ExistingTool) {
        if ((Get-Sha256 $ExistingTool) -ne $script:ToolExeHash) { throw 'Provided ttarchext.exe does not match the supported SHA256.' }
        return [IO.Path]::GetFullPath($ExistingTool)
    }
    $cache=Join-Path $DataRoot 'tools\ttarchext-0.3.2'
    $tool=Join-Path $cache 'ttarchext.exe'
    if (Test-Path -LiteralPath $tool -PathType Leaf) {
        if ((Get-Sha256 $tool) -eq $script:ToolExeHash) { return $tool }
        throw 'Cached archive tool has changed. Remove the First-person-mode tools cache and retry.'
    }
    New-Directory $cache
    $zip=Join-Path $cache 'download.zip'
    Write-Host 'Downloading the archive tool from its original author...'
    [Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $client=New-Object Net.WebClient
    # The author's host can return its homepage to requests without a user agent.
    $client.Headers['User-Agent']='Mozilla/5.0 FirstPersonModInstaller/1.0'
    $client.Headers['Referer']='https://aluigi.altervista.org/papers.htm'
    try { $client.DownloadFile($script:ToolUrl,$zip) } finally { $client.Dispose() }
    if ((Get-Sha256 $zip) -ne $script:ToolZipHash) {
        throw 'The official archive-tool download changed. SHA256 verification failed; nothing was executed. Download a newer mod release.'
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive=[IO.Compression.ZipFile]::OpenRead($zip)
    try {
        $entry=$archive.GetEntry('ttarchext.exe')
        if (-not $entry) { throw 'Official ZIP does not contain ttarchext.exe.' }
        $inputStream=$entry.Open(); $outputStream=[IO.File]::Create($tool)
        try { $inputStream.CopyTo($outputStream) } finally { $inputStream.Dispose(); $outputStream.Dispose() }
    } finally { $archive.Dispose() }
    if ((Get-Sha256 $tool) -ne $script:ToolExeHash) { throw 'Extracted archive tool failed SHA256 verification.' }
    return $tool
}
function Get-ArchiveEntries([string]$Listing) {
    $result=New-Object 'System.Collections.Generic.List[object]'
    foreach ($match in [regex]::Matches($Listing,'(?m)^\s+([0-9a-fA-F]{8})\s+(\d+)\s+([^\r\n]+)\r?$')) {
        $result.Add([pscustomobject]@{offset=[Convert]::ToInt64($match.Groups[1].Value,16);size=[int64]$match.Groups[2].Value;name=$match.Groups[3].Value.Trim()})
    }
    return $result.ToArray()
}
function Write-TtarchV3([hashtable]$Entries,[string]$Path) {
    if ($Entries.Count -eq 0) { throw 'Cannot package an empty archive.' }
    [string[]]$names=@($Entries.Keys)
    [Array]::Sort($names,[StringComparer]::OrdinalIgnoreCase)
    $tableStream=New-Object IO.MemoryStream
    $table=New-Object IO.BinaryWriter($tableStream)
    $payloadStream=New-Object IO.MemoryStream
    $table.Write([uint32]1); $table.Write([uint32]1); $table.Write([byte]46); $table.Write([uint32]$names.Length)
    foreach ($name in $names) {
        if ($name -cnotmatch '^[a-zA-Z0-9_]+\.lenc$') { throw "Invalid archive name: $name" }
        [byte[]]$bytes=$Entries[$name]
        $encoded=[Text.Encoding]::ASCII.GetBytes($name)
        $table.Write([uint32]$encoded.Length); $table.Write($encoded)
        $table.Write([uint32]0); $table.Write([uint32]$payloadStream.Length); $table.Write([uint32]$bytes.Length)
        $payloadStream.Write($bytes,0,$bytes.Length)
    }
    $output=[IO.File]::Create($Path)
    try {
        $writer=New-Object IO.BinaryWriter($output)
        foreach ($number in @(3,0,2,1,0,$payloadStream.Length,$tableStream.Length)) { $writer.Write([uint32]$number) }
        $writer.Write($tableStream.ToArray()); $writer.Write($payloadStream.ToArray()); $writer.Flush()
    } finally { $output.Dispose(); $table.Dispose(); $payloadStream.Dispose() }
}
function Get-OriginalScripts([string]$Game,[string]$Episode,[string]$Tool,[string]$Stage,[string]$Work) {
    $folder=Join-Path (Join-Path $Game 'Pack') $Episode
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) { throw "Episode data missing: $Episode" }
    [string[]]$archives=@(Get-ChildItem -LiteralPath $folder -Filter '*.ttarch' -File | Where-Object { $_.Name -notlike '*firstperson*' } | ForEach-Object { $_.FullName })
    [Array]::Sort($archives,[StringComparer]::OrdinalIgnoreCase)
    $wanted=@{'_system'='fp_original_system.lua';'module_visibility'='fp_original_visibility.lua'}
    $origins=@{}
    foreach ($archive in $archives) {
        if ($origins.Count -eq 2) { break }
        $listing=Invoke-Archiver $Tool @('-l','52',$archive,$Work) $Work
        $entries=@(Get-ArchiveEntries $listing)
        foreach ($base in @('_system','module_visibility')) {
            if ($origins.ContainsKey($base)) { continue }
            $found=@($entries | Where-Object { $_.name -ieq ($base+'.lenc') -or $_.name -ieq ($base+'.lua') })
            if ($found.Count -eq 0) { continue }
            $extract=Join-Path $Work ('extract-'+$Episode+'-'+$base)
            New-Directory $extract
            [void](Invoke-Archiver $Tool @('-o','-f',$found[0].name,'52',$archive,$extract) $Work)
            $source=Join-Path $extract ($base+'.lua')
            if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Original script extraction failed: $base in $archive" }
            Copy-Item -LiteralPath $source -Destination (Join-Path $Stage $wanted[$base])
            $origins[$base]=[pscustomobject]@{archive=$archive;sha256=Get-Sha256 $source}
        }
    }
    if ($origins.Count -ne 2) { throw "Original bootstrap/visibility scripts not found for $Episode. Verify the original game's Steam files." }
    return $origins
}
function New-EpisodePatch([string]$Game,$Episode,[string]$PayloadRoot,[string]$Tool,[string]$Work,[string]$OutputRoot) {
    $name=[string]$Episode.episode
    Write-Host "Preparing and verifying $name..."
    $stage=Join-Path $Work ('stage-'+$name)
    New-Directory $stage
    foreach ($entry in $Episode.scripts) {
        Copy-Item -LiteralPath (Join-Path (Join-Path $PayloadRoot $name) $entry.name) -Destination (Join-Path $stage $entry.name)
    }
    $origins=Get-OriginalScripts $Game $name $Tool $stage $Work
    $intermediate=Join-Path $Work ($name+'-v8.ttarch')
    [void](Invoke-Archiver $Tool @('-o','-b','-x','-V','8','52',$intermediate,$stage) $Work)
    $bytes=[IO.File]::ReadAllBytes($intermediate)
    $expected=@(8,1,2,1,0)
    for ($i=0;$i -lt 5;$i++) { if ([BitConverter]::ToUInt32($bytes,$i*4) -ne $expected[$i]) { throw 'Unexpected intermediate archive format.' } }
    $listing=Invoke-Archiver $Tool @('-l','52',$intermediate,$Work) $Work
    $entries=@(Get-ArchiveEntries $listing)
    $sources=@(Get-ChildItem -LiteralPath $stage -Filter '*.lua' -File)
    if ($entries.Count -ne $sources.Count) { throw 'Archive entry count mismatch.' }
    $encrypted=@{}
    foreach ($entry in $entries) {
        if ($entry.offset -lt 20 -or $entry.size -lt 1 -or $entry.offset+$entry.size -gt $bytes.Length) { throw 'Invalid intermediate archive bounds.' }
        $slice=New-Object byte[] $entry.size
        [Buffer]::BlockCopy($bytes,[int]$entry.offset,$slice,0,[int]$entry.size)
        $encrypted[$entry.name]=$slice
    }
    $destination=Join-Path (Join-Path (Join-Path $OutputRoot 'Pack') $name) $script:PatchName
    New-Directory (Split-Path -Parent $destination)
    Write-TtarchV3 $encrypted $destination
    $verify=Join-Path $Work ('verify-'+$name)
    New-Directory $verify
    [void](Invoke-Archiver $Tool @('-o','52',$destination,$verify) $Work)
    foreach ($source in $sources) {
        if ((Get-Sha256 $source.FullName) -ne (Get-Sha256 (Join-Path $verify $source.Name))) { throw "Archive round-trip verification failed: $name/$($source.Name)" }
    }
    return [pscustomobject]@{episode=$name;archive=$destination;sha256=Get-Sha256 $destination;originals=$origins}
}
function Install-PreparedPatches([string]$Game,[object[]]$Records,[string]$DataRoot) {
    Assert-GameClosed
    $stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')+'-'+[guid]::NewGuid().ToString('N')
    $backupRoot=Join-Path (Join-Path $DataRoot 'backups') $stamp
    New-Directory $backupRoot
    $changed=New-Object 'System.Collections.Generic.List[object]'
    try {
        foreach ($record in $Records) {
            Assert-GameClosed
            $target=Assert-Within (Join-Path (Join-Path (Join-Path $Game 'Pack') $record.episode) $script:PatchName) $Game
            $backup=Join-Path (Join-Path $backupRoot $record.episode) $script:PatchName
            $hadPrevious=Test-Path -LiteralPath $target -PathType Leaf
            if ($hadPrevious) {
                New-Directory (Split-Path -Parent $backup)
                $previousHash=Get-Sha256 $target
                Copy-Item -LiteralPath $target -Destination $backup
                if ((Get-Sha256 $backup) -ne $previousHash) { throw "Existing patch backup verification failed: $target" }
            }
            $temporary=$target+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
            Copy-Item -LiteralPath $record.archive -Destination $temporary
            try {
                if ((Get-Sha256 $temporary) -ne $record.sha256) { throw 'Installation copy verification failed.' }
                if ($hadPrevious) { [IO.File]::Replace($temporary,$target,[NullString]::Value) }
                else { [IO.File]::Move($temporary,$target) }
            } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
            $changed.Add([pscustomobject]@{target=$target;backup=$backup;previous=$hadPrevious;sha256=$record.sha256})
            if ((Get-Sha256 $target) -ne $record.sha256) { throw "Installed archive verification failed: $target" }
        }
    } catch {
        $installationError=$_.Exception.Message
        $rollbackErrors=New-Object 'System.Collections.Generic.List[string]'
        foreach ($item in $changed) {
            try {
                if ($item.previous) { Copy-Item -LiteralPath $item.backup -Destination $item.target -Force }
                elseif (Test-Path -LiteralPath $item.target) { Remove-Item -LiteralPath $item.target -Force }
            } catch { $rollbackErrors.Add($item.target+': '+$_.Exception.Message) }
        }
        if ($rollbackErrors.Count -gt 0) {
            throw "Installation failed: $installationError. Rollback also failed for: $($rollbackErrors -join '; '). Backups: $backupRoot"
        }
        throw "Installation failed; earlier changes were rolled back: $installationError"
    }
    [pscustomobject]@{game=$Game;installed_utc=(Get-Date).ToUniversalTime().ToString('o');patches=$changed.ToArray()} |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $backupRoot 'installation.json') -Encoding UTF8
    return $backupRoot
}
function Uninstall-Mod([string]$Game,[string]$DataRoot) {
    Assert-GameClosed
    $stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')+'-'+[guid]::NewGuid().ToString('N')
    $backupRoot=Join-Path (Join-Path $DataRoot 'uninstalled') $stamp
    $removed=New-Object 'System.Collections.Generic.List[object]'
    try {
        foreach ($episode in $script:Episodes) {
            $target=Assert-Within (Join-Path (Join-Path (Join-Path $Game 'Pack') $episode) $script:PatchName) $Game
            if (Test-Path -LiteralPath $target -PathType Leaf) {
                Assert-GameClosed
                $backup=Join-Path (Join-Path $backupRoot $episode) $script:PatchName
                New-Directory (Split-Path -Parent $backup)
                $hash=Get-Sha256 $target
                Move-Item -LiteralPath $target -Destination $backup
                $removed.Add([pscustomobject]@{target=$target;backup=$backup;sha256=$hash})
                if ((Get-Sha256 $backup) -ne $hash) { throw "Uninstall backup verification failed: $backup" }
            }
        }
    } catch {
        $uninstallError=$_.Exception.Message
        $rollbackErrors=New-Object 'System.Collections.Generic.List[string]'
        foreach ($item in $removed) {
            try { Move-Item -LiteralPath $item.backup -Destination $item.target }
            catch { $rollbackErrors.Add($item.target+': '+$_.Exception.Message) }
        }
        if ($rollbackErrors.Count -gt 0) { throw "Uninstall failed: $uninstallError. Rollback also failed for: $($rollbackErrors -join '; '). Backups: $backupRoot" }
        throw "Uninstall failed; removed patches were restored: $uninstallError"
    }
    if ($removed.Count -gt 0) {
        [pscustomobject]@{game=$Game;uninstalled_utc=(Get-Date).ToUniversalTime().ToString('o');patches=$removed.ToArray()} |
            ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $backupRoot 'uninstallation.json') -Encoding UTF8
    }
    Write-Host "Removed $($removed.Count) first-person patch archives. Backups: $backupRoot"
}
