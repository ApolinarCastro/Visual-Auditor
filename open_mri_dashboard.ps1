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
            Start-Process $url
            exit 0
        }
    } catch {
        Start-Sleep -Milliseconds 750
    }
}

# Final attempt: let the default browser show the actual connection error.
Start-Process $url
exit 1
