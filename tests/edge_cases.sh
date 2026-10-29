#!/usr/bin/env bash
# Edge cases a real user hits: running twice, stacked stashes, staged files,
# a merge in progress, and reinstalling the hook. Real git, nothing mocked.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export WINDDOWN_HOME="$tmp/state" WINDDOWN_CLAUDE_SETTINGS="$tmp/claude/settings.json"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
wd() { python3 "$here/winddown.py" --no-kill "$@"; }
fail() { echo "FAIL: $*"; cat TOMORROW.md 2>/dev/null || true; exit 1; }
new_repo() {
  rm -rf "$tmp/r" && mkdir "$tmp/r" && cd "$tmp/r"
  git init -q -b main && git config commit.gpgsign false
  echo base > a.txt && git add a.txt && git commit -qm "base"
}

# 1. Running twice keeps "restore your work" and the TODO in TOMORROW.md.
new_repo
echo "# TODO: finish this" >> a.txt
wd . >/dev/null
wd . >/dev/null
grep -q 'git stash pop --index stash@{0}' TOMORROW.md || fail "rerun lost the restore item"
grep -q 'TODO: finish this in a.txt:2' TOMORROW.md || fail "rerun lost the TODO"
grep -q 'stashed as "winddown ' TOMORROW.md || fail "rerun lost where-you-stopped"
echo "ok   running twice keeps tomorrow's list"

# 2. Stacked stashes: the newest is restored, older ones are mentioned.
echo "day two" > b.txt
wd . >/dev/null
[[ $(git stash list | grep -c winddown) -eq 2 ]] || fail "expected 2 winddown stashes"
grep -q 'stash@{0}` (b.txt)' TOMORROW.md || fail "newest stash not first"
grep -q '1 older winddown stash in `git stash list`' TOMORROW.md || fail "older stash not mentioned"
echo "ok   stacked stashes are all accounted for"

# 3. The suggested command restores staged changes as staged.
new_repo
echo staged >> a.txt && git add a.txt
echo unstaged > c.txt
wd . >/dev/null
cmd=$(grep -o 'git stash pop --index stash@{[0-9]*}' TOMORROW.md)
eval "$cmd" >/dev/null
[[ "$(git diff --cached --name-only)" == "a.txt" ]] || fail "staging not restored by: $cmd"
[[ -f c.txt ]] || fail "untracked file not restored"
echo "ok   restore command keeps staged files staged"

# 4. A merge conflict is left alone and explained, not silently skipped.
new_repo
git checkout -qb other && echo theirs > a.txt && git commit -qam theirs
git checkout -q main && echo ours > a.txt && git commit -qam ours
git merge -q other >/dev/null 2>&1 || true
err=$(wd . 2>&1 >/dev/null)
[[ "$err" == *"in the middle of a merge"* ]] || fail "no merge warning: $err"
[[ -z "$(git stash list)" ]] || fail "stashed during a merge"
grep -q 'Finish the merge in progress' TOMORROW.md || fail "merge not in TOMORROW.md"
echo "ok   merge in progress is left in place and explained"

# 5. Reinstalling the hook keeps the original settings as the backup.
mkdir -p "$(dirname "$WINDDOWN_CLAUDE_SETTINGS")"
echo '{"model": "opus"}' > "$WINDDOWN_CLAUDE_SETTINGS"
python3 "$here/winddown.py" install-hook >/dev/null
python3 "$here/winddown.py" install-hook >/dev/null
[[ "$(cat "$WINDDOWN_CLAUDE_SETTINGS.winddown.bak")" == '{"model": "opus"}' ]] || fail "backup overwritten"
echo "ok   reinstalling the hook keeps the original backup"

echo "PASS: all edge cases"
