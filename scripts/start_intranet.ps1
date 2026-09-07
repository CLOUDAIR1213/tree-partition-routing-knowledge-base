#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8001,

    [ValidatePattern("^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$")]
    [string]$AllowedSubnet = "10.88.20.0/24"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$ruleName = "Partitioned Knowledge Base Intranet ($Port)"
$environmentNames = @(
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "SERVE_FRONTEND",
    "VITE_API_BASE_URL"
)
$originalEnvironment = @{}
foreach ($name in $environmentNames) {
    $originalEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$firewallRuleCreated = $false

Set-Location $repoRoot
$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($listener) {
    throw "Port $Port is already in use. Stop the tree-index service using this port before starting intranet mode. A legacy service on another port can remain running."
}

try {
    # The bundled intranet page must always call the API at its current origin.
    # This overrides an optional local development API URL only for this script run.
    $env:VITE_API_BASE_URL = ""
    npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed; intranet mode was not started."
    }

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
    $firewallRuleCreated = $true

    $env:SERVE_FRONTEND = "true"
    $env:APP_ENV = "trusted_intranet"
    $env:APP_HOST = "0.0.0.0"
    $env:APP_PORT = $Port.ToString()
    uv run uvicorn app.main:app --host 0.0.0.0 --port $Port
}
finally {
    if ($firewallRuleCreated) {
        Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
            Remove-NetFirewallRule
    }
    foreach ($name in $environmentNames) {
        if ($null -eq $originalEnvironment[$name]) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item "Env:$name" -Value $originalEnvironment[$name]
        }
    }
}
