# upstream-sync.ps1
# Sync our fork with upstream without overwriting custom_tools/ and bim-semantic-layer/

$ErrorActionPreference = "Stop"

$UPSTREAM = "https://github.com/mcp-servers-for-revit/mcp-server-for-revit-python.git"

Write-Host "[1] Fetch upstream..."
git remote add upstream $UPSTREAM 2>$null
git fetch upstream

Write-Host "`n[2] Upstream commits not in our master:"
git log HEAD..upstream/master --oneline | Select-Object -First 20

$delta = (git log HEAD..upstream/master --oneline 2>$null).Count
if ($delta -eq 0) {
    Write-Host "`n[OK] We are up to date with upstream."
    exit 0
}

Write-Host "`n[3] Merging upstream/master with our changes..."
Write-Host "    (custom_tools/ and bim-semantic-layer/ will NOT be overwritten)"

# Strategy: merge with ours for our protected directories
git merge upstream/master --no-edit -X ours --no-ff 2>&1

Write-Host "`n[4] Checking protected files survived..."
$protected = @(
    "custom_tools/__init__.py",
    "custom_tools/bim_catalog.py",
    "custom_tools/bim_summary.py",
    "custom_tools/vor_vs_bim.py",
    "custom_tools/bim_vor_to_sheets.py",
    "bim-semantic-layer/global_patterns.json"
)
foreach ($f in $protected) {
    if (Test-Path $f) {
        Write-Host "  [OK] $f exists"
    } else {
        Write-Host "  [WARN] $f MISSING after merge!"
    }
}

Write-Host "`n[5] Push to our fork..."
git push

Write-Host "`n[DONE] Sync complete. Our custom tools preserved."
