param(
  [Parameter(Mandatory=$true)]
  [string]$RepositoryUrl
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "未找到 Git。请先安装 Git for Windows。"
}
if (-not (Test-Path ".git")) {
  git init
}
if (-not (git config user.name)) {
  $gitName = Read-Host "请输入用于本次提交的 Git 用户名"
  git config user.name $gitName
}
if (-not (git config user.email)) {
  $gitEmail = Read-Host "请输入用于本次提交的 Git 邮箱"
  git config user.email $gitEmail
}
git add .
git diff --cached --quiet
$hasChanges = $LASTEXITCODE -ne 0
if ($hasChanges) {
  git commit -m "Initial public release"
}
git branch -M main
$origin = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0) {
  git remote set-url origin $RepositoryUrl
} else {
  git remote add origin $RepositoryUrl
}
git push -u origin main
Write-Host "代码已推送。请在仓库 Settings -> Pages 中选择 GitHub Actions，然后运行发布工作流。"
