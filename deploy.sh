#!/usr/bin/env bash
# Build the site and publish it to the gh-pages branch, which GitHub Pages serves.
# Usage: ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"
node build_site.js _site

wt=$(mktemp -d)
trap 'git worktree remove --force "$wt" 2>/dev/null || true' EXIT
if git ls-remote --exit-code --heads origin gh-pages >/dev/null 2>&1; then
  git fetch -q --depth 1 origin gh-pages
  git worktree add -q -B gh-pages "$wt" FETCH_HEAD
else
  git worktree add -q --orphan -b gh-pages "$wt"
fi

# replace the branch content with the fresh build
find "$wt" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a _site/. "$wt"/
git -C "$wt" add -A
if git -C "$wt" diff --cached --quiet; then echo "no changes to deploy"; exit 0; fi
git -C "$wt" commit -q -m "Deploy $(git rev-parse --short HEAD)" ${DEPLOY_TRAILER:+-m "$DEPLOY_TRAILER"}
git -C "$wt" push -u origin gh-pages
