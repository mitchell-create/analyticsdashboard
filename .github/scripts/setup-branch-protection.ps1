# Setup branch protection on main
# Run: gh auth login   (first time only)
# Then: .github/scripts/setup-branch-protection.ps1

$repo = gh repo view --json nameWithOwner -q .nameWithOwner
if (-not $repo) {
    Write-Error "Not in a git repo or gh not authenticated. Run: gh auth login"
    exit 1
}

Write-Host "Configuring branch protection for $repo (main)..."

$body = @{
    required_status_checks = $null
    enforce_admins = $false
    required_pull_request_reviews = @{
        dismiss_stale_reviews = $true
        require_code_owner_reviews = $false
        required_approving_review_count = 0
    }
    restrictions = $null
    allow_force_pushes = $false
    allow_deletions = $false
    required_linear_history = $false
} | ConvertTo-Json -Depth 5 -Compress

$body | gh api repos/$repo/branches/main/protection -X PUT --input -

if ($LASTEXITCODE -eq 0) {
    Write-Host "Branch protection enabled: PRs required to merge into main."
} else {
    Write-Host "If you lack permissions, set it manually: Settings > Branches > Add rule (main)"
}
