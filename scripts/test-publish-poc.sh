#!/usr/bin/env bash
# Regression tests for scripts/publish-poc.sh.
#
#   scripts/test-publish-poc.sh
#
# The bug these exist for: the frozen-path listing piped into `head -20`. head closes the pipe once it has 20 lines,
# the writer takes SIGPIPE, and because the script runs under `set -o pipefail` the whole publish died with exit 141.
# It only showed up when a folder published more than 20 frozen paths for the first time, which is exactly the moment
# a POC's recorded evidence first lands in the repository.
#
# Each test builds a throwaway repository with a bare origin, so nothing here touches a real remote.
set -euo pipefail
cd "$(dirname "$0")/.."
SCRIPT="$PWD/scripts/publish-poc.sh"
# The script runs under the same bash as these tests: `/bin/bash scripts/test-publish-poc.sh` tests bash 3.2.
echo "bash: $BASH ($BASH_VERSION)"
pass=0
fail=0

ok()   { printf '  ok   %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '  FAIL %s\n' "$1"; fail=$((fail + 1)); }
check() { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (expected $1, got $2)"; fi; }

# A repository with `n` frozen files staged through the script's own --from copy.
scaffold() {
  local n=$1 dir
  dir=$(mktemp -d)
  git init -q --bare "$dir/origin.git"
  git clone -q "$dir/origin.git" "$dir/repo"
  mkdir -p "$dir/repo/scripts" "$dir/work"
  cp "$SCRIPT" "$dir/repo/scripts/publish-poc.sh"
  cp -R "$(dirname "$SCRIPT")/vendor" "$dir/repo/scripts/vendor"
  git -C "$dir/repo" -c user.email=t@local -c user.name=test add -A
  git -C "$dir/repo" -c user.email=t@local -c user.name=test commit -q -m "init"
  git -C "$dir/repo" push -q origin HEAD:main
  git -C "$dir/repo" branch -q -M main
  git -C "$dir/repo" branch -q --set-upstream-to=origin/main main 2>/dev/null || true
  mkdir -p "$dir/work"
  printf 'runs/**\n' > "$dir/work/.publish-frozen"
  mkdir -p "$dir/work/runs"
  local i=1
  while [ "$i" -le "$n" ]; do
    printf 'evidence %s\n' "$i" > "$dir/work/runs/file$i.json"
    i=$((i + 1))
  done
  printf '%s\n' "$dir"
}

run_publish() {           # run_publish <dir> [extra args...]; prints the exit code
  local dir=$1; shift
  local code=0
  ( cd "$dir/repo" && mkdir -p poc && "$BASH" scripts/publish-poc.sh poc \
      --from "$dir/work" --message "poc: evidence" --checks "true" "$@" >"$dir/out.log" 2>&1 ) || code=$?
  printf '%s\n' "$code"
}

echo "frozen-path listing under set -o pipefail"

for n in 5 20 21 150; do
  dir=$(scaffold "$n")
  code=$(run_publish "$dir" --allow-frozen --dry-run)
  check 0 "$code" "$n frozen path(s), --allow-frozen --dry-run exits 0"
  if grep -q "warning: $n frozen path(s)" "$dir/out.log"; then
    ok "$n frozen path(s): the count is reported"
  else
    bad "$n frozen path(s): count missing from the output"
  fi
  shown=$(grep -cE '^     [AMD]  ' "$dir/out.log" || true)
  expected=$([ "$n" -gt 20 ] && echo 20 || echo "$n")
  check "$expected" "$shown" "$n frozen path(s): at most 20 lines listed"
  if [ "$n" -gt 20 ]; then
    if grep -q "and $((n - 20)) more" "$dir/out.log"; then
      ok "$n frozen path(s): the remainder is counted"
    else
      bad "$n frozen path(s): no '… and N more' line"
    fi
  fi
  rm -rf "$dir"
done

echo "the frozen guard still refuses without --allow-frozen"
dir=$(scaffold 25)
code=$(run_publish "$dir" --dry-run)
if [ "$code" -ne 0 ] && grep -q "would change (rule 11)" "$dir/out.log"; then
  ok "25 frozen path(s) without --allow-frozen: refused, non-zero"
else
  bad "25 frozen path(s) without --allow-frozen: expected a refusal, got exit $code"
fi
rm -rf "$dir"

echo "a .publish-frozen that cannot be read fails loudly instead of disabling the guard"
dir=$(scaffold 30)
rm "$dir/work/.publish-frozen" && mkdir "$dir/work/.publish-frozen"
code=$(run_publish "$dir" --allow-frozen --dry-run)
if [ "$code" -ne 0 ] && grep -q "not a readable file" "$dir/out.log"; then
  ok "an unreadable .publish-frozen makes the publish fail, not pass quietly"
else
  bad "an unreadable .publish-frozen was ignored (exit $code)"
fi
rm -rf "$dir"

echo "no .publish-frozen at all is legitimate: no frozen rules, no warning"
dir=$(scaffold 30)
rm "$dir/work/.publish-frozen"
code=$(run_publish "$dir" --dry-run)
if [ "$code" -eq 0 ] && ! grep -q "frozen path(s)" "$dir/out.log"; then
  ok "a folder with no .publish-frozen publishes without a frozen warning"
else
  bad "a folder with no .publish-frozen behaved unexpectedly (exit $code)"
fi
rm -rf "$dir"

echo "a failing check still fails the publish"
dir=$(scaffold 3)
code=0
( cd "$dir/repo" && mkdir -p poc && "$BASH" scripts/publish-poc.sh poc --from "$dir/work" \
    --message "poc: evidence" --checks "false" --allow-frozen --dry-run >"$dir/out.log" 2>&1 ) || code=$?
if [ "$code" -ne 0 ]; then ok "a failing --checks command fails the publish"; else bad "a failing --checks command was ignored"; fi
rm -rf "$dir"

echo "hygiene gate: no local path, host name or address reaches main"

dir=$(scaffold 2)
printf '{"command": "/Users/jane/ws/run.py"}\n' > "$dir/work/runs/leak.json"
code=$(run_publish "$dir" --allow-frozen --dry-run)
check 1 "$code" "a staged file with a home path is refused"
if grep -q "local path or identity" "$dir/out.log"; then ok "the refusal names the reason"; else bad "the refusal names the reason"; fi
rm -rf "$dir"

dir=$(scaffold 2)
printf '/Users/jane/\n' > "$dir/work/.publish-hygiene-allow"
printf '{"doc": "an example path /Users/jane/ in a tutorial"}\n' > "$dir/work/runs/example.json"
code=$(run_publish "$dir" --allow-frozen --dry-run)
check 0 "$code" "an intended match listed in .publish-hygiene-allow passes"
rm -rf "$dir"

dir=$(scaffold 2)
printf '{"command": "/Users/jane/ws/run.py"}\n' > "$dir/repo/poc-old.json"
mkdir -p "$dir/repo/poc/runs" && mv "$dir/repo/poc-old.json" "$dir/repo/poc/runs/old.json"
git -C "$dir/repo" -c user.email=t@local -c user.name=test add -A
git -C "$dir/repo" -c user.email=t@local -c user.name=test commit -q -m "a leak from before the gate"
cp "$dir/repo/poc/runs/old.json" "$dir/work/runs/renamed.json"
code=$(run_publish "$dir" --allow-frozen --dry-run)
check 1 "$code" "a renamed file with a home path is refused"
rm -rf "$dir"

dir=$(scaffold 2)
printf '{"command": "/Users/jane/ws/run.py"}\n' > "$dir/work/runs/r\303\251sum\303\251.json"
code=$(run_publish "$dir" --allow-frozen --dry-run)
check 1 "$code" "a non-ASCII file name with a home path is refused"
rm -rf "$dir"

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
