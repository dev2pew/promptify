$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$mailmapPath = Join-Path $root ".mailmap-rewrite"
$createdMailmap = $false

$confirm = {
    param($prompt)
    Write-Host "$prompt [y/N]: " -NoNewline
    $key = [Console]::ReadKey($true).KeyChar
    Write-Host $key
    return ($key -match '^[yY]$')
}

function Read-RequiredValue {
    param(
        [string]$Prompt,
        [string]$Default = ""
    )

    while ($true) {
        if ($Default) {
            $value = Read-Host "$Prompt [$Default]"
            if ([string]::IsNullOrWhiteSpace($value)) {
                return $Default
            }
        }
        else {
            $value = Read-Host $Prompt
        }

        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value.Trim()
        }

        Write-Host "Value cannot be empty." -ForegroundColor Yellow
    }
}

Push-Location $root
try {
    $originUrl = git remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0) {
        $originUrl = $null
    }
    $sourceNameDefault = (git config user.name 2>$null).Trim()
    $sourceEmailDefault = (git config user.email 2>$null).Trim()
    if ($LASTEXITCODE -ne 0) {
        $sourceNameDefault = ""
        $sourceEmailDefault = ""
    }

    Write-Host "Repository: $root" -ForegroundColor Cyan
    if ($originUrl) {
        Write-Host "Origin: $originUrl" -ForegroundColor Cyan
    }
    else {
        Write-Host "Origin: <missing>" -ForegroundColor Yellow
    }

    $sourceName = Read-RequiredValue "Source git name to replace" $sourceNameDefault
    $sourceEmail = Read-RequiredValue "Source git email to replace" $sourceEmailDefault
    $targetName = Read-RequiredValue "New git name" "lucky"
    $targetEmail = Read-RequiredValue "New git email" "lucky@localhost"

    if (($sourceName.Trim().ToLowerInvariant() -eq $targetName.Trim().ToLowerInvariant()) -and ($sourceEmail.Trim().ToLowerInvariant() -eq $targetEmail.Trim().ToLowerInvariant())) {
        throw "Source and target identity are identical. Refusing to run a no-op history rewrite."
    }

    Write-Host ""
    Write-Host "This rewrites all local branches, tags, reachable commits, and the current HEAD." -ForegroundColor Yellow
    Write-Host "Source: $sourceName <$sourceEmail>" -ForegroundColor Yellow
    Write-Host "Target: $targetName <$targetEmail>" -ForegroundColor Yellow

    if (-not (& $confirm "Rewrite the full git history, restore origin, and force-push all branches and tags?")) {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 1
    }

    $mailmapLine = "$targetName <$targetEmail> $sourceName <$sourceEmail>"
    Set-Content -Path $mailmapPath -Value $mailmapLine -Encoding ascii
    $createdMailmap = $true
    Write-Host "Wrote $mailmapPath" -ForegroundColor Green

    uv run git-filter-repo --mailmap $mailmapPath --force
    if ($LASTEXITCODE -ne 0) {
        throw "git-filter-repo failed."
    }

    if ($originUrl) {
        $hasOrigin = git remote | Select-String '^origin$'
        if ($hasOrigin) {
            git remote set-url origin $originUrl
        }
        else {
            git remote add origin $originUrl
        }

        if ($LASTEXITCODE -ne 0) {
            throw "Failed to restore origin remote."
        }
    }
    else {
        Write-Host "Skipping origin restore because no origin remote was configured." -ForegroundColor Yellow
    }

    git config user.name $targetName
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to set git user.name."
    }

    git config user.email $targetEmail
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to set git user.email."
    }

    if ($originUrl) {
        git push --force --all origin
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to force-push branches."
        }

        git push --force --tags origin
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to force-push tags."
        }
    }

    Write-Host "History rewrite completed." -ForegroundColor Green
}
catch {
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}
finally {
    if ($createdMailmap -and (Test-Path $mailmapPath)) {
        Remove-Item -LiteralPath $mailmapPath -Force
        Write-Host "Removed generated $mailmapPath" -ForegroundColor DarkGray
    }
    Pop-Location
}
