#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
repo_url="${1:-}"
if [[ -z "$repo_url" ]]; then
  echo "用法: ./publish_to_github.sh https://github.com/你的账号/zero-carbon-park-observatory.git" >&2
  exit 2
fi
command -v git >/dev/null 2>&1 || { echo "未找到 Git。" >&2; exit 1; }
[[ -d .git ]] || git init
if ! git config user.name >/dev/null 2>&1; then
  read -r -p "请输入用于本次提交的 Git 用户名: " git_name
  git config user.name "$git_name"
fi
if ! git config user.email >/dev/null 2>&1; then
  read -r -p "请输入用于本次提交的 Git 邮箱: " git_email
  git config user.email "$git_email"
fi
git add .
if ! git diff --cached --quiet; then
  git commit -m "Initial public release"
fi
git branch -M main
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$repo_url"
else
  git remote add origin "$repo_url"
fi
git push -u origin main
echo "代码已推送。请在仓库 Settings -> Pages 中选择 GitHub Actions，然后运行发布工作流。"
