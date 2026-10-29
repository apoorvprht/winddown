#!/usr/bin/env bash
# End-to-end demo: real git repo, real stash, real hook exit codes. Nothing mocked.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export WINDDOWN_HOME="$tmp/state" WINDDOWN_CLAUDE_SETTINGS="$tmp/claude/settings.json"
wd() { python3 "$here/winddown.py" "$@"; }
fail() { echo "FAIL: $*"; exit 1; }

repo="$tmp/repo"
mkdir "$repo" && cd "$repo"
git init -q && git config user.email demo@example.com && git config user.name demo
echo "print('hi')" > app.py && git add app.py && git commit -qm "add app"
echo "# TODO: handle empty input" >> app.py
echo "notes" > scratch.txt

out="$(wd "$repo" --until 08:30 --no-kill)"
echo "$out"
[[ "$out" == "Closed 1 repo, stashed 1, tomorrow's list is in TOMORROW.md. You're done until 08:30." ]] || fail "summary line"
git stash list | grep -q "winddown $(date +%F)" || fail "stash missing"
[[ -z "$(git status --porcelain)" ]] || fail "working tree not clean"
[[ "$(git log --format=%s)" == "add app" ]] || fail "commits changed"
grep -q "Where you stopped" TOMORROW.md || fail "TOMORROW.md header"
grep -q "TODO: handle empty input in app.py:2" TOMORROW.md || fail "TODO item"
items=$(grep -cE '^[0-9]+\. ' TOMORROW.md); (( items >= 1 && items <= 3 )) || fail "item count $items"
[[ -f "$WINDDOWN_HOME/pause.json" ]] || fail "pause file"

set +e; msg="$(wd check 2>&1 >/dev/null)"; code=$?; set -e
[[ $code -eq 2 ]] || fail "check exit $code, want 2"
[[ "$msg" == *"Winddown active until 08:30"* ]] || fail "check message: $msg"

wd resume >/dev/null || fail "resume exit"
[[ ! -f "$WINDDOWN_HOME/pause.json" ]] || fail "pause not cleared"
wd check || fail "check after resume should exit 0"

git stash pop -q && grep -q TODO app.py && [[ -f scratch.txt ]] || fail "stash did not restore work"

mkdir -p "$(dirname "$WINDDOWN_CLAUDE_SETTINGS")"
echo '{"model": "opus", "hooks": {"Stop": []}}' > "$WINDDOWN_CLAUDE_SETTINGS"
wd install-hook >/dev/null && wd install-hook >/dev/null
python3 - "$WINDDOWN_CLAUDE_SETTINGS" <<'PY' || fail "hook merge"
import json, sys
s = json.load(open(sys.argv[1]))
assert s["model"] == "opus" and "Stop" in s["hooks"]
assert len(s["hooks"]["UserPromptSubmit"]) == 1
assert s["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"].endswith("winddown.py check")
PY
[[ -f "$WINDDOWN_CLAUDE_SETTINGS.winddown.bak" ]] || fail "settings backup"

echo "PASS: stash, TOMORROW.md, pause, check=2, resume=0, hook merge"
