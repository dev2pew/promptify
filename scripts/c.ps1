Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$ProjectRoot = Resolve-Path -LiteralPath (Join-Path $ScriptDir "..")

Set-Location -LiteralPath $ProjectRoot

function Remove-PathIfExists {
    param (
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
        Write-Host "Deleted: $Path"
    }
}

Write-Host "Project root: $ProjectRoot"

# 1. Recursively delete all __pycache__ directories.
Get-ChildItem `
    -LiteralPath $ProjectRoot `
    -Directory `
    -Recurse `
    -Force `
    -Filter "__pycache__" |
    ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force
        Write-Host "Deleted: $($_.FullName)"
    }

# 2. Delete selected folders in the project root.
$RootDirs = @(
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    "__pycache__",
    "pytest-cache-files-*"
)

foreach ($Dir in $RootDirs) {
    if ($Dir.Contains("*")) {
        Get-ChildItem -LiteralPath $ProjectRoot -Directory -Force -Filter $Dir -ErrorAction SilentlyContinue |
            ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force
                Write-Host "Deleted: $($_.FullName)"
            }
        continue
    }
    Remove-PathIfExists -Path (Join-Path $ProjectRoot $Dir)
}

# 3. Delete selected files in the project root.
$RootFiles = @(
    "bp-detail.json",
    "data/problems.json",
    "data/problems.md"
)

foreach ($File in $RootFiles) {
    Remove-PathIfExists -Path (Join-Path $ProjectRoot $File)
}
