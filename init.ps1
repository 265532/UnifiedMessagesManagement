$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $PythonCommand) {
    $PythonCommand = Get-Command python3 -ErrorAction SilentlyContinue
}
if ($null -eq $PythonCommand) {
    throw "Harness requires Python 3.10+ (python or python3)"
}
$Python = $PythonCommand.Source

& $Python .harness/scripts/harness.py bootstrap
if ($LASTEXITCODE -ne 0) { throw "Harness bootstrap failed" }
& $Python .harness/scripts/harness.py doctor
if ($LASTEXITCODE -ne 0) { throw "Harness doctor failed" }
& $Python .harness/scripts/harness.py status
if ($LASTEXITCODE -ne 0) { throw "Harness status failed" }
