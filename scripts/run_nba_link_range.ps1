param(
    [Parameter(Mandatory = $true)]
    [string]$StartDate,

    [Parameter(Mandatory = $true)]
    [string]$EndDate,

    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,

    [string]$DailyVideoOutputPath = "data/nba_okru_daily.json",
    [string]$OutputDir = "data",
    [string]$PythonExe = "python",
    [string]$PythonPath = "src",
    [switch]$DryRun,
    [switch]$StopOnError,
    [switch]$VerboseLogs
)

$ErrorActionPreference = "Stop"

function Parse-IsoDate([string]$value) {
    try {
        return [DateTime]::ParseExact($value, "yyyy-MM-dd", $null)
    }
    catch {
        throw "Invalid date '$value'. Expected format: YYYY-MM-DD."
    }
}

$start = (Parse-IsoDate $StartDate).Date
$end = (Parse-IsoDate $EndDate).Date

if ($end -lt $start) {
    throw "EndDate must be >= StartDate. Got StartDate=$StartDate EndDate=$EndDate."
}

if (-not (Test-Path $ConfigPath)) {
    throw "Config file not found: $ConfigPath"
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$previousPyPath = $env:PYTHONPATH
$env:PYTHONPATH = $PythonPath

$successCount = 0
$failureCount = 0

try {
    for ($day = $start; $day -le $end; $day = $day.AddDays(1)) {
        $dateStr = $day.ToString("yyyy-MM-dd")
        $outputPath = Join-Path $OutputDir ("nba_link_results_{0}.json" -f $dateStr)
        $subCommand = if ($DryRun) { "dry-run" } else { "run" }

        $args = @(
            "-m", "mentions_sports_poller.nba_link_scout",
            $subCommand,
            "--date", $dateStr,
            "--config", $ConfigPath,
            "--output", $outputPath
        )
        if (-not $DryRun) {
            $args += @("--daily-video-output", $DailyVideoOutputPath)
        }
        if ($VerboseLogs) {
            $args += "-v"
        }

        Write-Host ("[{0}] Running: {1} {2}" -f (Get-Date -Format "u"), $PythonExe, ($args -join " "))
        & $PythonExe @args
        $exitCode = $LASTEXITCODE

        if ($exitCode -ne 0) {
            $failureCount++
            Write-Host ("[{0}] FAILED date={1} exit_code={2}" -f (Get-Date -Format "u"), $dateStr, $exitCode) -ForegroundColor Yellow
            if ($StopOnError) {
                throw "Stopping on first error because -StopOnError is set."
            }
            continue
        }

        $successCount++
        Write-Host ("[{0}] OK date={1} output={2}" -f (Get-Date -Format "u"), $dateStr, $outputPath) -ForegroundColor Green
    }
}
finally {
    if ($null -eq $previousPyPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONPATH = $previousPyPath
    }
}

Write-Host ("Completed range {0}..{1} success={2} failed={3}" -f $StartDate, $EndDate, $successCount, $failureCount)
if ($failureCount -gt 0) {
    exit 1
}
