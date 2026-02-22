# upstream-sync.ps1 — Sync fork with upstream (mcp-servers-for-revit)
# Our custom code lives in custom_tools/ and custom_routes/ — no conflicts expected
# Only main.py has our 3 added lines (easy manual merge if needed)

param(
    [switch]$DryRun,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "[SYNC] Fetching upstream..." -ForegroundColor Cyan
git fetch upstream

$behind = git rev-list --count "HEAD..upstream/master"
$ahead = git rev-list --count "upstream/master..HEAD"

Write-Host "[SYNC] Status: $behind commits behind, $ahead commits ahead of upstream" -ForegroundColor Yellow

if ($behind -eq 0) {
    Write-Host "[SYNC] Already up to date!" -ForegroundColor Green
    exit 0
}

if ($DryRun) {
    Write-Host "[SYNC] Dry run — would merge $behind commits from upstream/master" -ForegroundColor Yellow
    git log --oneline "HEAD..upstream/master"
    exit 0
}

Write-Host "[SYNC] Merging upstream/master..." -ForegroundColor Cyan
$mergeResult = git merge upstream/master --no-edit 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "[SYNC] MERGE CONFLICT detected!" -ForegroundColor Red
    Write-Host "[SYNC] Resolving: keeping our custom_tools/ and custom_routes/" -ForegroundColor Yellow
    
    # Our folders — always keep ours
    if (Test-Path "custom_tools") { git checkout --ours custom_tools/ 2>$null }
    if (Test-Path "custom_routes") { git checkout --ours custom_routes/ 2>$null }
    
    # Check if main.py has conflict (our 3 lines)
    $conflicts = git diff --name-only --diff-filter=U
    Write-Host "[SYNC] Remaining conflicts: $conflicts" -ForegroundColor Red
    Write-Host "[SYNC] Please resolve manually, then: git add . && git commit" -ForegroundColor Yellow
    exit 1
}

Write-Host "[SYNC] Merge successful! Pushing to origin..." -ForegroundColor Green
git push origin master

Write-Host "[SYNC] Done! $behind commits merged from upstream." -ForegroundColor Green
