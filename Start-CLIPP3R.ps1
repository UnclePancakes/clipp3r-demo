$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "CLIPP3R is not set up yet. Run Setup-CLIPP3R.bat first."
}
if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue)) {
    throw "FFmpeg is missing from PATH. Install FFmpeg, then run Setup-CLIPP3R.bat again."
}

$port = $null
foreach ($candidate in 8787..8800) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $candidate)
    try {
        $listener.Start()
        $port = $candidate
        break
    }
    catch {
        continue
    }
    finally {
        $listener.Stop()
    }
}
if ($null -eq $port) {
    throw "No free CLIPP3R port was found between 8787 and 8800."
}

$env:CLIPP3R_HOST = "127.0.0.1"
$env:CLIPP3R_PORT = "$port"
$url = "http://127.0.0.1:$port/"
$browserJob = Start-Job -ArgumentList $url -ScriptBlock {
    param($targetUrl)
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $targetUrl -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Start-Process $targetUrl
                return
            }
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    throw "CLIPP3R did not respond at $targetUrl within 60 seconds."
}

Write-Host "Starting CLIPP3R at $url"
Write-Host "Your clips and source files stay on this computer."
Write-Host "Keep this window open while CLIPP3R is running. Press Ctrl+C here to stop it."
Push-Location $root
try {
    & $python -u -m ai_clips_maker.webapp
    if ($LASTEXITCODE -ne 0) {
        throw "The CLIPP3R server exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
    if ($browserJob.State -eq "Running") {
        Stop-Job -Job $browserJob
    }
    Remove-Job -Job $browserJob -Force
}
