#!/usr/bin/env python3
"""Run winddown for real in a throwaway HOME and save every command's output.

The output (demo/session.json) is what demo/render.swift turns into a video,
so the video shows real output, not typed-in text.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
home = tempfile.mkdtemp(prefix="winddown-demo-")
env = dict(os.environ, HOME=home, PATH=home + "/.local/bin:" + os.environ["PATH"],
           GIT_AUTHOR_NAME="Sam", GIT_AUTHOR_EMAIL="sam@example.com",
           GIT_COMMITTER_NAME="Sam", GIT_COMMITTER_EMAIL="sam@example.com")
env.pop("WINDDOWN_HOME", None)
env.pop("WINDDOWN_CLAUDE_SETTINGS", None)


def sh(cmd, cwd=home):
    r = subprocess.run(["bash", "-c", cmd], cwd=cwd, env=env, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.replace(os.path.realpath(home), "~").replace(home, "~")
    return out.rstrip("\n")


def write(path, text):
    path = os.path.join(home, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


# A realistic day: two repos, commits from today, unfinished work in both.
sh("bash %s/install.sh" % ROOT)
for name in ("api", "web"):
    sh("git init -q code/%s && git -C code/%s config commit.gpgsign false" % (name, name))
write("code/api/src/parser.py", "def parse(data):\n    return data.split(',')\n")
sh("git add -A && git commit -qm 'add CSV parser'", cwd=home + "/code/api")
write("code/api/src/parser.py",
      "def parse(data):\n    # TODO: handle empty input\n    return data.split(',')\n\n"
      "def parse_stream(lines):\n    for line in lines:\n        yield parse(line)\n")
sh("git add -A && git commit -qm 'add streaming parser'", cwd=home + "/code/api")
write("code/api/src/parser.py",
      "def parse(data):\n    # TODO: handle empty input\n    return data.split(',')\n\n"
      "def parse_stream(lines):\n    # FIXME: skips the last line\n    for line in lines[:-1]:\n"
      "        yield parse(line)\n")
write("code/api/tests/test_parser.py", "from src.parser import parse\n\n"
      "def test_basic():\n    assert parse('a,b') == ['a', 'b']\n")
write("code/web/index.html", "<h1>Dashboard</h1>\n")
sh("git add -A && git commit -qm 'dashboard shell'", cwd=home + "/code/web")
write("code/web/index.html", "<h1>Dashboard</h1>\n<!-- TODO: wire up chart -->\n")

api = home + "/code/api"
steps = []


def scene(caption, cmds, cwd=api, hold=2.5):
    out = []
    for c in cmds:
        out.append({"cmd": c, "out": sh(c, cwd=cwd)})
    steps.append({"kind": "scene", "caption": caption, "steps": out, "hold": hold})


steps.append({"kind": "title", "title": "winddown",
              "subtitle": "One command to end the developer day.",
              "body": "For developers running several Claude Code sessions who find it hard to stop.\n"
                      "AI makes each task faster, so we take on more, and the evenings go.",
              "hold": 4.5})
scene("19:45. Two repos, both with unfinished work.",
      ["git status --short", "git log --oneline --since=midnight"])
scene("One command closes the day.\n(--no-kill only so this recording does not stop the agent filming it.)",
      ["winddown --no-kill ~/code/api ~/code/web"], hold=3)
scene("Your work is stashed safely. Commits are untouched.",
      ["git status", "git stash list", "git log --oneline -1"])
scene("Tomorrow's list: at most 3 items, built from your real diff and commits.",
      ["cat TOMORROW.md"], hold=4.5)
scene("22:10. You open Claude Code for \"just one more thing\".\n"
      "Its UserPromptSubmit hook runs winddown check:",
      ["grep '\"command\"' ~/.claude/settings.json",
       "echo '{\"prompt\":\"one more fix\"}' | winddown check; echo \"exit code: $?\""],
      hold=4)
scene("Exit code 2 means Claude Code blocks the prompt. The evening stays yours.\n"
      "Next morning the pause lifts at 08:30 by itself. Or, any time:",
      ["winddown resume", "git stash pop -q && git status --short"], hold=3.5)
steps.append({"kind": "title", "title": "No alerts. No dashboards. No prompts.",
              "subtitle": "It runs once, prints one line, and gives the evening back.",
              "body": "github.com/apoorvprht/winddown",
              "hold": 5})

with open(os.path.join(ROOT, "demo", "session.json"), "w") as fh:
    json.dump(steps, fh, indent=2)
shutil.rmtree(home)
json.dump(steps, sys.stdout, indent=1)
