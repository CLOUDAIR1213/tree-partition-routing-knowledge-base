#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,

    [ValidatePattern("^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$")]
    [string]$AllowedSubnet = "10.88.20.0/24"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$ruleName = "Partitioned Knowledge Base Intranet ($Port)"

Set-Location $repoRoot
$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($listener) {
    throw "Port $Port is already in use. Stop the existing local server before starting intranet mode."
}

npm --prefix frontend run build

# Replace only this application's previous rule so the allowed subnet stays current.
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule
New-NetFirewallRule `
    -DisplayName $ruleName `
    -Group "Partitioned Knowledge Base" `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $Port `
    -RemoteAddress $AllowedSubnet `
    -Profile Any | Out-Null

try {
    $env:SERVE_FRONTEND = "true"
    $env:APP_ENV = "trusted_intranet"
    uv run uvicorn app.main:app --host 0.0.0.0 --port $Port
}
finally {
    Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule
}
