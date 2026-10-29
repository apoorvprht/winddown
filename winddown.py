#!/usr/bin/env python3
"""winddown: one command to end the developer day.

Stashes uncommitted work, writes a 3-item TOMORROW.md, pauses Claude Code
until morning, and stops leftover background agents. Standard library only.
"""
import datetime as dt
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys

DEFAULT_UNTIL = "08:30"
STATE_DIR = os.environ.get("WINDDOWN_HOME", os.path.expanduser("~/.winddown"))
PAUSE_FILE = os.path.join(STATE_DIR, "pause.json")
SETTINGS_FILE = os.environ.get(
    "WINDDOWN_CLAUDE_SETTINGS", os.path.expanduser("~/.claude/settings.json")
)
TODO_RE = re.compile(r"\b(TODO|FIXME)\b[:\s]*(.*)")
USAGE = """usage: winddown [repo ...] [--until HH:MM] [--no-kill]
       winddown check          (Claude Code UserPromptSubmit hook)
       winddown resume         (end the pause now)
       winddown install-hook   (add the hook to ~/.claude/settings.json)"""


def git(repo, *args, check=False):
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, check=check
    )


def is_repo(path):
    return git(path, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"


def has_head(repo):
    return git(repo, "rev-parse", "--verify", "-q", "HEAD").returncode == 0


def changed_files(repo):
    out = git(repo, "status", "--porcelain", "-uall").stdout
    return [line[3:].split(" -> ")[-1] for line in out.splitlines() if line.strip()]


def todos_in_diff(repo):
    """TODO/FIXME lines added in uncommitted changes, as (file, line, text)."""
    diff = git(repo, "diff", "HEAD", "-U0").stdout if has_head(repo) else \
        git(repo, "diff", "--cached", "-U0").stdout + git(repo, "diff", "-U0").stdout
    found = todos_in_patch(diff)
    untracked = git(repo, "ls-files", "--others", "--exclude-standard").stdout
    for rel in untracked.splitlines():
        try:
            with open(os.path.join(repo, rel), encoding="utf-8") as fh:
                for n, text in enumerate(fh, 1):
                    m = TODO_RE.search(text)
                    if m:
                        found.append((rel, n, m.group(0).strip()))
        except (OSError, UnicodeDecodeError):
            continue
    return found


def todos_in_patch(diff):
    found = []
    current, lineno = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            lineno = int(m.group(1)) if m else 0
        elif line.startswith("+") and current:
            m = TODO_RE.search(line)
            if m:
                found.append((current, lineno, m.group(0).strip()))
            lineno += 1
    return found


def operation_in_progress(repo):
    """'merge', 'rebase', ... if git is mid-operation (stashing would fail)."""
    for marker, name in (("MERGE_HEAD", "merge"), ("rebase-merge", "rebase"),
                         ("rebase-apply", "rebase"), ("CHERRY_PICK_HEAD", "cherry-pick"),
                         ("REVERT_HEAD", "revert")):
        path = git(repo, "rev-parse", "--git-path", marker).stdout.strip()
        if os.path.exists(path if os.path.isabs(path) else os.path.join(repo, path)):
            return name
    return None


def stash_show(repo, ref, *args):
    """`git stash show` including untracked files (git >= 2.32), else without."""
    r = git(repo, "stash", "show", "--include-untracked", *args, ref)
    return r.stdout if r.returncode == 0 else git(repo, "stash", "show", *args, ref).stdout


def winddown_stashes(repo):
    """Winddown stashes, newest first, as (ref, label, files)."""
    out = git(repo, "stash", "list", "--format=%gd%x09%gs").stdout
    found = []
    for line in out.splitlines():
        ref, _, subject = line.partition("\t")
        m = re.search(r"winddown \d{4}-\d\d-\d\d( \d\d:\d\d)?", subject)
        if m:
            files = stash_show(repo, ref, "--name-only").split()
            found.append((ref, m.group(0), files))
    return found


def todays_commits(repo):
    if not has_head(repo):
        return []
    out = git(repo, "log", "--since=midnight", "--format=%s").stdout
    return [s for s in out.splitlines() if s.strip()]


def exclude_tomorrow(repo):
    """Keep TOMORROW.md out of git so it never shows up as a change."""
    path = git(repo, "rev-parse", "--git-path", "info/exclude").stdout.strip()
    if not os.path.isabs(path):
        path = os.path.join(repo, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = open(path).read() if os.path.exists(path) else ""
    if "TOMORROW.md" not in existing.split():
        with open(path, "a") as fh:
            fh.write(("" if existing.endswith("\n") or not existing else "\n") + "TOMORROW.md\n")


def short_list(items, n=3):
    shown = ", ".join(items[:n])
    return shown + (" +%d more" % (len(items) - n) if len(items) > n else "")


def build_tomorrow(files, todos, commits, stashes, operation):
    if operation:
        where = "in the middle of a %s, changes left in place." % operation
    elif files and not stashes:
        where = "editing %s, left in place." % short_list(files, 2)
    elif stashes:
        _, label, stashed_files = stashes[0]
        where = 'editing %s, stashed as "%s".' % (short_list(stashed_files, 2), label)
    elif commits:
        where = 'committed "%s".' % commits[0]
    else:
        where = "nothing in progress, clean tree."
    items = []
    if operation:
        items.append("Finish the %s in progress (`git status` shows what's left)" % operation)
    if stashes:
        ref, _, stashed_files = stashes[0]
        item = "Restore your work: `git stash pop --index %s` (%s)" % (
            ref, short_list(stashed_files))
        if len(stashes) > 1:
            item += "; %d older winddown stash%s in `git stash list`" % (
                len(stashes) - 1, "" if len(stashes) == 2 else "es")
        items.append(item)
    for f, n, text in todos:
        items.append("%s in %s:%d" % (text, f, n))
    if commits:
        items.append('Continue from today\'s last commit: "%s"' % commits[0])
    if not items:
        items.append("Pick one thing. Start small.")
    lines = ["# Tomorrow", "", "**Where you stopped:** " + where, ""]
    lines += ["%d. %s" % (i, item) for i, item in enumerate(items[:3], 1)]
    return "\n".join(lines) + "\n"


def close_repo(repo, label):
    """Returns True if work was stashed."""
    files = [f for f in changed_files(repo) if f != "TOMORROW.md"]
    todos = todos_in_diff(repo)
    commits = todays_commits(repo)
    operation = operation_in_progress(repo)
    stashed = False
    if files and operation:
        print("winddown: %s is in the middle of a %s, left changes in place."
              % (repo, operation), file=sys.stderr)
    elif files and not has_head(repo):
        print("winddown: %s has no commits yet, left changes in place." % repo,
              file=sys.stderr)
    elif files:
        r = git(repo, "stash", "push", "-u", "-m", label)
        stashed = r.returncode == 0 and "No local changes" not in r.stdout
        if not stashed:
            print("winddown: could not stash %s: %s" % (repo, r.stderr.strip()),
                  file=sys.stderr)
    stashes = winddown_stashes(repo) if has_head(repo) else []
    if not files and stashes:
        # Already wound down earlier: rebuild the list from the stash, don't lose it.
        todos = todos_in_patch(stash_show(repo, stashes[0][0], "-p", "-U0"))
    exclude_tomorrow(repo)
    with open(os.path.join(repo, "TOMORROW.md"), "w") as fh:
        fh.write(build_tomorrow(files, todos, commits, stashes, operation))
    return stashed


def resume_time(hhmm, now=None):
    now = now or dt.datetime.now()
    h, m = (int(x) for x in hhmm.split(":"))
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return t if t > now else t + dt.timedelta(days=1)


def write_pause(until):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PAUSE_FILE, "w") as fh:
        json.dump({"until": until.isoformat(timespec="minutes"),
                   "since": dt.datetime.now().isoformat(timespec="minutes")}, fh)


def read_pause():
    try:
        with open(PAUSE_FILE) as fh:
            return dt.datetime.fromisoformat(json.load(fh)["until"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def ancestors():
    pids, pid = set(), os.getpid()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)],
                             capture_output=True, text=True).stdout.strip()
        pid = int(out) if out.isdigit() else 1
    return pids


def kill_background_claude():
    """Stop `claude` processes with no terminal, except our own process tree."""
    out = subprocess.run(["ps", "-axo", "pid=,tty=,comm="],
                         capture_output=True, text=True).stdout
    mine, killed = ancestors(), 0
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, tty, comm = int(parts[0]), parts[1], parts[2]
        if os.path.basename(comm) != "claude" or pid in mine:
            continue
        if tty not in ("?", "??"):
            continue  # attached to a terminal: someone may be looking at it
        try:
            os.kill(pid, signal.SIGTERM)
            killed += 1
        except OSError:
            pass
    return killed


def cmd_winddown(args):
    until, kill, repos = DEFAULT_UNTIL, True, []
    it = iter(args)
    for a in it:
        if a == "--until":
            until = next(it, "")
        elif a == "--no-kill":
            kill = False
        elif a in ("-h", "--help"):
            print(USAGE)
            return 0
        else:
            repos.append(a)
    if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", until):
        print("winddown: --until needs HH:MM, e.g. --until 09:00", file=sys.stderr)
        return 1
    label = "winddown %s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    closed = stashed = 0
    for path in repos or ["."]:
        path = os.path.abspath(path)
        if not is_repo(path):
            print("winddown: %s is not a git repo, skipped." % path, file=sys.stderr)
            continue
        root = git(path, "rev-parse", "--show-toplevel").stdout.strip()
        stashed += close_repo(root, label)
        closed += 1
    t = resume_time(until)
    write_pause(t)
    if kill:
        kill_background_claude()
    print("Closed %d repo%s, stashed %d, tomorrow's list is in TOMORROW.md. "
          "You're done until %s." % (closed, "" if closed == 1 else "s", stashed,
                                     t.strftime("%H:%M")))
    return 0


def cmd_check():
    until = read_pause()
    if until is None:
        return 0
    if dt.datetime.now() >= until:
        cmd_resume(quiet=True)
        return 0
    print("Winddown active until %s. Rest. Run `winddown resume` to override."
          % until.strftime("%H:%M"), file=sys.stderr)
    return 2


def cmd_resume(quiet=False):
    try:
        os.remove(PAUSE_FILE)
    except FileNotFoundError:
        pass
    if not quiet:
        print("Pause cleared. Welcome back.")
    return 0


def cmd_install_hook():
    # Absolute path: hooks run without your shell profile, so PATH can't be trusted.
    script = os.path.realpath(sys.argv[0])
    command = "python3 %s check" % shlex.quote(script)
    settings = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as fh:
                settings = json.load(fh)
        except ValueError:
            print("winddown: %s is not valid JSON, not touching it." % SETTINGS_FILE,
                  file=sys.stderr)
            return 1
    groups = settings.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    for g in groups:
        for h in g.get("hooks", []):
            if "winddown" in h.get("command", "") and h.get("command", "").endswith(" check"):
                print("Hook already installed in %s." % SETTINGS_FILE)
                return 0
    # Back up only when we're about to change it, so the backup is the pre-winddown file.
    if os.path.exists(SETTINGS_FILE):
        shutil.copy2(SETTINGS_FILE, SETTINGS_FILE + ".winddown.bak")
    groups.append({"hooks": [{"type": "command", "command": command}]})
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(settings, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, SETTINGS_FILE)
    print("Hook installed in %s (%s)." % (SETTINGS_FILE, command))
    return 0


def main(argv):
    if argv and argv[0] == "check":
        return cmd_check()
    if argv and argv[0] == "resume":
        return cmd_resume()
    if argv and argv[0] == "install-hook":
        return cmd_install_hook()
    return cmd_winddown(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
