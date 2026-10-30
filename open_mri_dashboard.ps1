param(
    [int]$Port = 8055,
    [int]$TimeoutSeconds = 90
)

$url = "http://127.0.0.1:$Port/"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
            break
        }
    } catch {
        Start-Sleep -Milliseconds 750
    }
}

$chromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromeCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

$marker = Join-Path $PSScriptRoot 'data\runtime_tmp\mri_browser_launch.json'
New-Item -ItemType Directory -Force -Path (Split-Path $marker) | Out-Null

if ($chrome) {
    # Explicitly open a real Chrome window; this also triggers the Basic-auth prompt.
    $proc = Start-Process -FilePath $chrome -ArgumentList "--new-window", $url -PassThru
    @{ opened_at = (Get-Date).ToString('o'); browser = $chrome; url = $url; pid = $proc.Id } |
        ConvertTo-Json | Set-Content -Encoding UTF8 $marker
    exit 0
}

# Fallback: system default browser.
$proc = Start-Process $url -PassThru
@{ opened_at = (Get-Date).ToString('o'); browser = 'DEFAULT'; url = $url; pid = $proc.Id } |
    ConvertTo-Json | Set-Content -Encoding UTF8 $marker
exit 0
