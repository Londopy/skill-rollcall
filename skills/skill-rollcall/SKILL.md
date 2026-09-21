---
name: skill-rollcall
description: Take a roll call of installed skills - see which are registered, which are new, which will never register and why, and fix or load them without restarting. Works in Claude Code, Codex, Cursor, Gemini CLI, Copilot, OpenCode and any other Agent Skills host. Use this whenever the user says reload skills, refresh skills, rescan skills, re-index skills, roll call, lint my skills, audit my skills, "I just installed a skill", "I just added/edited a SKILL.md", asks whether you can see a particular skill, asks why a skill is not showing up or not triggering, asks how much context their skills cost, asks which skills another agent can see, or wants a skills repo checked before publishing. Also use it after you yourself install or write a skill mid-session, to confirm it registered.
license: MIT
compatibility: Requires Python 3.10+. Read-only unless --fix --apply is passed.
metadata:
  author: Londopy
  version: "1.2.0"
---

# Skill roll call

Every agent that supports skills - Claude Code, Codex, Cursor, Gemini CLI, GitHub
Copilot, OpenCode, Amp, Cline and the rest - reads each `SKILL.md`'s frontmatter at
startup, and most watch the folders afterwards, so adds, edits and removals normally
show up within the session. None of them tell anyone *why* a folder was skipped, and
each reads a different set of folders. This skill rebuilds the same index from disk,
for the host you are running in, with the reasons attached, then repairs, lints or
audits on request.

The script is `scripts/rollcall.py` next to this file - run it from wherever this
skill was installed (`~/.claude/skills/skill-rollcall/`, `~/.agents/skills/skill-rollcall/`,
`~/.codex/skills/...`, `~/.cursor/skills/...`, or a project's `.agents/skills/`). It is
stdlib-only Python 3.10+ and read-only unless `--fix --apply` is passed.

## Which host

The script detects the host from the environment (`CLAUDECODE`, `CODEX_SANDBOX`,
`CURSOR_AGENT`, `GEMINI_CLI`) and scans that host's folders. If nothing identifies the
host it scans every known host's folders and labels each row with who reads it. Pass
`--agent` when you know better:

| Situation | Flag |
|---|---|
| You are the host and detection got it right (header says `host: <you>`) | nothing |
| Header says `host: all` and you know which agent you are | `--agent codex` (or claude, cursor, gemini, copilot, opencode, amp, goose, kiro, windsurf) |
| "what can Cursor see", "does Codex have this skill" | `--agent cursor`, `--agent codex` |
| "which skills do I have anywhere", comparing hosts | `--agent all` |

Each host's folders, per its docs: Claude Code `~/.claude/skills` and `.claude/skills`;
Codex `~/.agents/skills`, `~/.codex/skills` and `.agents/skills`; Cursor `~/.cursor/skills`
and `.agents/skills`; Gemini CLI `~/.gemini/skills`; Copilot `~/.copilot/skills`; OpenCode
`~/.config/opencode/skills`; every host walks `.agents/skills` (or its own project folder)
from the working directory up to the git root. Rows from the shared `.agents/skills`
convention say `agents`, because several hosts read it. Under `--agent all`, a skill that
appears in two hosts' folders is a copy, not a duplicate; the duplicate warning only fires
when one host would see both.

## Pick the mode from what the user asked

| The user says | Run |
|---|---|
| "do you see /x", "reload skills", "is it registered" | `--known <names>` |
| "why isn't it showing up", "it's not loading" | default (errors section) then `--fix` |
| "why isn't it triggering", "which should I trim", "how much context" | `--lint` |
| "is this skill safe", "scan these", anything after a bulk install | `--audit` |
| "check my skills repo before I publish" | `--skills-dir <repo>/skills --lint --audit --strict` |
| "does it work in Codex too", "will this load everywhere" | `--skills-dir <repo>/skills --agent all --lint` |

Flags combine. `--problems-only` drops the table when only findings matter; `--json`
when you need to process the result.

## Steps

1. Run it. For `--known`, pass the skill names from your own system context - the
   list your skill tool accepts (Claude Code's `Skill` tool, Codex's `$skill` menu,
   Cursor's `/skill` list). That turns "compare by eye" into a diff: rows become
   **registered** or **NEW**, and names the host lists but that no longer exist on disk
   are reported as stale.

2. Answer the question first, then summarize. If they asked about one skill, lead with
   that skill's line. Then, briefly:
   - **errors** - folders that will never register anywhere. Give the one-line fix each:
     add frontmatter, close it, add a `name`, move a nested folder up. If the script
     planned a fix, offer `--fix --apply`; show the dry run first so they can see the
     moves.
   - **warnings** - registers, but: no description (never auto-triggers), `name` not
     matching the folder or outside the Agent Skills spec (strict hosts skip it), a
     description over the spec's 1024 chars (hosts truncate it), duplicate names one
     host sees together, a skill Codex has switched off in `config.toml`, and under
     `--lint` the description-quality findings and Claude-only frontmatter other hosts
     ignore. These are why "it's installed but never fires".
   - **NEW** - on disk, not yet in your index. Usually it appears on the next turn.
     If they want it now, do step 3.
   - **audit** - `high` findings deserve a direct read of the file before the user
     runs that skill. `review` hits are phrases that are ordinary inside a security
     or prompt-testing skill (a jailbreak signature table will contain "ignore
     previous instructions"); read them in context and say what you found rather
     than just relaying the count. `info` is external hosts the skill references.

   Do not paste the whole table back when a few rows matter. Say the count, name
   the exceptions.

3. To use a NEW skill before the host registers it, read its `SKILL.md` and follow
   it. That is all any host's skill tool does: it puts the file body into context. Read
   any `scripts/` or `references/` it points to when the instructions call for them.
   Tell the user you loaded it manually so they know the slash or `$` form may lag.

4. If a skill is on disk with no errors and still not registered after another turn,
   the host is not watching that folder. Claude Code's `--bare` mode has no watcher;
   Codex says to restart when a change does not appear. `/clear` or a restart reruns
   discovery but wipes the conversation, so let them finish anything in flight. For a
   Claude Code plugin, changes to `hooks/`, `agents/` or `.mcp.json` need
   `/reload-plugins`; SKILL.md text does not.

5. If the user reports "/x isn't a command here" from the Claude desktop app but you
   have `x` in your own listing, the app's slash-command picker is stale, not the
   harness. Tell them to send the request as a plain message; do not suggest `/clear`
   for this.

## Related, not overlapping

Claude Code's `/skill-doctor` (2.1.252+) reports what each skill *costs* and how often
it is *used*. It does not say why a skill failed to register. When the user's real
question is "which skills should I turn off", point them there; the context-cost line
here is a rough stand-in for when `/skill-doctor` is unavailable or you are not in
Claude Code. The `skills` CLI (`npx skills ls`) lists what it installed, not what the
host loaded.

## What this cannot do

It cannot make the host rescan; only the host does that. Host detection is best effort:
it reads environment markers, and a host that sets none is reported as `all`, so pass
`--agent` when you know. It does not evaluate whether a description *will* trigger for
a given phrase - `--lint` catches the structural reasons a description under-triggers
(too short, no "use when", overlaps with a sibling), not the semantic ones. It does not
read Codex or Cursor plugin bundles, only skill folders. And `--audit` is a pattern scan,
not a verdict: a clean audit means nothing obvious was found, not that the skill is safe.
