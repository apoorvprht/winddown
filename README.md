# winddown

AI makes each task faster, so we take on more, and the breaks and evenings disappear: compression burnout. winddown is for developers who run several Claude Code sessions at once and find it hard to stop.

One command closes the day: your work is stashed safely, tomorrow's first three steps are written down, and Claude Code stays paused until morning.

It's the **"A shutdown command"** idea from the hackathon brief: one command that saves your open work, writes tomorrow's list and pauses your agents until morning. It came out of Claude Conversations at Toast, Dublin, where the room named compression burnout as the problem to fix first.

## What you see

**[Watch the 65-second demo](demo/winddown-demo.mp4)**, made from a real run in sample repos (`demo/record.py` captures it, `demo/render.swift` renders it).

```
$ winddown ~/code/api ~/code/web
Closed 2 repos, stashed 2, tomorrow's list is in TOMORROW.md. You're done until 08:30.
```

`~/code/api/TOMORROW.md`:

```markdown
# Tomorrow

**Where you stopped:** editing src/parser.py, tests/test_parser.py, stashed as "winddown 2026-10-29".

1. Restore your work: `git stash pop` (src/parser.py, tests/test_parser.py)
2. TODO: handle empty input in src/parser.py:42
3. Continue from today's last commit: "add streaming parser"
```

If you open Claude Code later that evening and type a prompt, it's blocked:

```
Winddown active until 08:30. Rest. Run `winddown resume` to override.
```

At 08:30 the pause lifts by itself. You don't need to do anything.

## Quickstart

```bash
git clone <this repo URL> winddown && cd winddown
./install.sh                 # copies winddown to ~/.local/bin and adds the Claude Code hook
winddown ~/code/api ~/code/web   # at the end of the day (no args = current repo)
```

You need Python 3.8+ and git, on macOS or Linux. There's nothing else to install.

Every evening after that, it's one command. In the morning, open `TOMORROW.md` and run `git stash pop`. To start earlier than 08:30: `winddown resume`. For a different morning: `winddown --until 09:15`.

To uninstall: delete `~/.local/bin/winddown` and the `winddown check` entry under `UserPromptSubmit` in `~/.claude/settings.json` (a backup from before the install is at `settings.json.winddown.bak`).

## What it does and doesn't do

**Does**

- In each repo with uncommitted changes, runs `git stash push -u -m "winddown <date>"`. Committed work and branches are never touched.
- Writes `TOMORROW.md` in each repo: one "Where you stopped" line, then at most 3 items built from the stash, `TODO`/`FIXME` lines in today's uncommitted diff, and today's commits. The file is added to `.git/info/exclude`, so it never shows up as a change.
- Writes `~/.winddown/pause.json` with a resume time (next 08:30, or `--until HH:MM`).
- Sends SIGTERM to `claude` processes that have no terminal attached (leftover background agents). Its own process tree and any `claude` running in a terminal are left alone. Use `--no-kill` to skip this step.
- `winddown check` is a Claude Code `UserPromptSubmit` hook: while paused it prints `Winddown active until HH:MM. Rest. Run `winddown resume` to override.` and exits 2, which blocks the prompt.
- `winddown resume` clears the pause. It always works, so you are never locked out.
- `winddown install-hook` merges the hook into `~/.claude/settings.json`, keeps your other settings, writes a backup to `settings.json.winddown.bak`, and does nothing if the hook is already there.

**Doesn't**

- It doesn't commit, push, or pop stashes for you. In the morning, `git stash pop` is item 1 on the list.
- It doesn't stash repos with no commits yet (git can't). It leaves those changes in place and says so.
- It doesn't block Claude Code sessions already mid-task. The hook stops new prompts. Background agents are only stopped if they have no terminal.
- It doesn't send notifications, track time, or phone home. It runs locally, Python 3 standard library only.
- The TOMORROW.md items are simple heuristics, not a summary written by an AI.

## How this gives time back

- **No alerts, no prompts, no dashboard.** It runs once, prints one line, and exits.
- **It removes the end-of-day decisions.** You don't have to work out what to commit, where to leave notes, or whether you can do one more thing. The command makes those calls.
- **Starting tomorrow is cheap.** Three items and a "where you stopped" line replace the fifteen minutes of working out what you were doing.
- **The evening goes back to you.** The hook means opening Claude Code at 22:00 gets you a reminder to rest, not a new task. If you really need it, one command overrides it.

## Test

```bash
bash tests/demo.sh
```

The demo builds a real temp git repo, runs winddown, and checks the stash, TOMORROW.md, the pause file, `check` exiting 2, `resume` exiting 0, and the settings merge. It uses temp state dirs and `--no-kill`, so your real `~/.winddown` and `~/.claude/settings.json` are left alone.

## License

MIT
