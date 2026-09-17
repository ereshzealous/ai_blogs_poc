#!/usr/bin/env bash
# Publish one POC folder to main. See PUBLISHING.md for the rules this enforces.
#
#   scripts/publish-poc.sh <folder> --message "<folder>: what changed" [options]
#
#   --from <dir>        copy this working copy into the folder first (each .gitignore is honoured)
#   --message <text>    commit subject and body; must start with "<folder>:"
#   --message-file <f>  read the message from a file instead
#   --checks <cmd>      run this in the folder before committing (default: <folder>/scripts/publish-checks.sh)
#   --no-checks         skip the checks, for a docs-only change
#   --dry-run           do everything except commit and push
set -euo pipefail

die() { printf '\nrefusing to publish: %s\n' "$1" >&2; exit 1; }
step() { printf '\n== %s\n' "$1"; }

[ $# -ge 1 ] || die "usage: scripts/publish-poc.sh <folder> --message \"<folder>: what changed\" [--from <dir>] [--checks <cmd>] [--dry-run]"
folder=${1%/}; shift
from=""; message=""; message_file=""; checks=""; run_checks=1; dry_run=0
while [ $# -gt 0 ]; do
  case "$1" in
    --from) from=${2:?--from needs a directory}; shift 2 ;;
    --message) message=${2:?--message needs text}; shift 2 ;;
    --message-file) message_file=${2:?--message-file needs a file}; shift 2 ;;
    --checks) checks=${2:?--checks needs a command}; shift 2 ;;
    --no-checks) run_checks=0; shift ;;
    --dry-run) dry_run=1; shift ;;
    *) die "unknown option: $1" ;;
  esac
done

repo=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$repo"
[ -d "$folder" ] || die "no folder $folder in $repo (rule 1: publish into your own POC folder)"
if [ -n "$message_file" ]; then message=$(cat "$message_file"); fi
[ -n "$message" ] || die "no commit message (--message or --message-file)"
case "$message" in
  "$folder":*) : ;;
  *) die "the subject must start with \"$folder:\" (rule 5)" ;;
esac
if printf '%s' "$message" | grep -qiE "co-authored-by:.*(claude|anthropic|copilot|chatgpt)|generated with \[?(claude|chatgpt)"; then
  die "the message credits an AI assistant as an author (rule 6)"
fi

step "1/6 working tree"
outside=$(git status --porcelain | grep -v -E "^.. ?\"?$folder/" || true)
[ -z "$outside" ] || die "changes outside $folder (rule 1):
$outside"

if [ -n "$from" ]; then
  step "2/6 copying $from -> $folder/"
  [ -d "$from" ] || die "--from $from is not a directory"
  rsync -a --delete --filter=':- .gitignore' --exclude .git/ "${from%/}/" "$folder/"
else
  step "2/6 copying: skipped (no --from; using what is already in $folder/)"
fi

step "3/6 staging $folder/ only"
git add -A -- "$folder"
staged=$(git diff --cached --name-only)
[ -n "$staged" ] || die "nothing to publish in $folder/"
stray=$(printf '%s\n' "$staged" | grep -v "^$folder/" || true)
[ -z "$stray" ] || die "staged files outside $folder (rule 1):
$stray"
printf '   %s file(s) staged\n' "$(printf '%s\n' "$staged" | wc -l | tr -d ' ')"
outside=$(git status --porcelain | grep -v -E "^.. ?\"?$folder/" || true)
[ -z "$outside" ] || die "the copy wrote outside $folder (rule 7):
$outside"

step "4/6 checks"
if [ "$run_checks" -eq 0 ]; then
  echo "   skipped (--no-checks)"
else
  if [ -z "$checks" ] && [ -x "$folder/scripts/publish-checks.sh" ]; then checks="./scripts/publish-checks.sh"; fi
  [ -n "$checks" ] || die "no checks to run (rule 4): pass --checks \"<command>\", add $folder/scripts/publish-checks.sh, or use --no-checks"
  echo "   $checks"
  ( cd "$folder" && eval "$checks" ) || die "the checks failed (rule 4)"
fi

step "5/6 commit"
if [ "$dry_run" -eq 1 ]; then
  echo "   --dry-run: nothing committed. Staged changes:"
  git diff --cached --stat | tail -5
  exit 0
fi
printf '%s\n' "$message" | git commit --quiet --file -
echo "   $(git rev-parse --short HEAD)  $(git log -1 --format=%s)"

step "6/6 rebase onto origin/main and push"
git fetch --quiet origin
if [ -n "$(git log --oneline HEAD..origin/main)" ]; then
  git rebase --quiet origin/main || { git rebase --abort 2>/dev/null || true; die "rebase onto origin/main failed; your commit is still here, resolve and run git push yourself"; }
  echo "   rebased onto $(git rev-parse --short origin/main)"
else
  echo "   already up to date with origin/main"
fi
git push --quiet origin HEAD:main
printf '\npublished %s  %s\n' "$(git rev-parse --short HEAD)" "$(git log -1 --format=%s)"
