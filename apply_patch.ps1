$ErrorActionPreference = "Stop"
$targets = @(
  ".github\workflows\deploy-mailer.yml",
  "services\report-mailer",
  "docs\EMAIL_DELIVERY.md",
  "static\docs\email-setup.html",
  "site\docs\email-setup.html"
)
foreach ($target in $targets) {
  if (Test-Path $target) {
    Remove-Item $target -Recurse -Force
    Write-Host "Removed: $target"
  }
}
Write-Host "Patch cleanup completed. Return to GitHub Desktop, commit, and push."
