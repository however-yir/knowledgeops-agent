Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

function Write-Step {
    param([string]$Message)
    Write-Host "[knowledgeops-agent][install][win] $Message" -ForegroundColor Cyan
}

function Fail {
    param([string]$Message)
    Write-Host "[knowledgeops-agent][install][win][error] $Message" -ForegroundColor Red
    exit 1
}

function Get-EnvValue {
    param([string]$Path, [string]$Key)
    if (-not (Test-Path $Path)) { return $null }
    $escaped = [Regex]::Escape($Key)
    $line = Get-Content $Path | Where-Object { $_ -match "^$escaped=" } | Select-Object -First 1
    if ($null -eq $line) { return $null }
    return $line.Substring($Key.Length + 1)
}

function Set-EnvValue {
    param([string]$Path, [string]$Key, [string]$Value)
    $lines = @()
    if (Test-Path $Path) {
        $lines = Get-Content $Path
    }
    $escaped = [Regex]::Escape($Key)
    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^$escaped=") {
            $lines[$i] = "$Key=$Value"
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $lines += "$Key=$Value"
    }
    Set-Content -Path $Path -Value $lines
}

Write-Step "Checking prerequisites..."

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker is not installed. Install Docker Desktop first."
}

try {
    docker info | Out-Null
} catch {
    Fail "Docker is not running. Start Docker Desktop first."
}

$composeMode = ""
try {
    docker compose version | Out-Null
    $composeMode = "docker-compose-plugin"
} catch {
    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        $composeMode = "docker-compose-v1"
    } else {
        Fail "Docker Compose is not available. Install Docker Compose plugin first."
    }
}

$envFile = Join-Path $RepoRoot ".env"
$envExample = Join-Path $RepoRoot ".env.example"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Step "Created .env from .env.example"
    } else {
        New-Item -Path $envFile -ItemType File | Out-Null
        Write-Step "Created empty .env"
    }
}

$apiKey = $env:OPENAI_API_KEY
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    $apiKey = Get-EnvValue -Path $envFile -Key "OPENAI_API_KEY"
}

if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey -eq "replace_me" -or $apiKey -eq "sk-local-dev-placeholder") {
    $inputKey = Read-Host "Please enter OPENAI_API_KEY"
    if ([string]::IsNullOrWhiteSpace($inputKey)) {
        Fail "OPENAI_API_KEY cannot be empty."
    }
    Set-EnvValue -Path $envFile -Key "OPENAI_API_KEY" -Value $inputKey
    Write-Step "Saved OPENAI_API_KEY to .env"
}

Write-Step "Starting containers..."
if ($composeMode -eq "docker-compose-plugin") {
    docker compose up --build -d
} else {
    docker-compose up --build -d
}

Write-Host "[knowledgeops-agent][install][win] Done." -ForegroundColor Green
Write-Host "- Frontend Console: http://localhost:8088"
Write-Host "- Backend API:      http://localhost:8080"
Write-Host "- RabbitMQ Console: http://localhost:15672"
Write-Host ""
Write-Host "Demo API Key (local only): dev-admin-key-2026"
