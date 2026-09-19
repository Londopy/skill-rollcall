---
name: skill-rollcall
description: Take a roll call of installed skills - see which are registered, which are new, which will never register and why, and fix or load them without restarting. Use this whenever the user says reload skills, refresh skills, rescan skills, re-index skills, roll call, lint my skills, audit my skills, "I just installed a skill", "I just added/edited a SKILL.md", asks whether you can see a particular /skill, asks why a skill is not showing up or not triggering, asks how much context their skills cost, or wants a skills repo checked before publishing. Also use it after you yourself install or write a skill mid-session, to confirm it registered.
---

# Skill roll call

Claude Code reads every `SKILL.md`'s frontmatter at startup and watches the skills
folders afterwards, so adds, edits and removals normally show up within the session.
What it does not do is tell anyone *why* a folder was skipped. This skill rebuilds the
same index from disk with the reasons attached, then repairs, lints or audits on
request.

The script is at `scripts/rollcall.py` next to this file (installed as a skill that is
`~/.claude/skills/skill-rollcall/scripts/rollcall.py`). It is stdlib-only and read-only
unless `--fix --apply` is passed.

## Pick the mode from what the user asked

| The user says | Run |
|---|---|
| "do you see /x", "reload skills", "is it registered" | `--known <names>` |
| "why isn't it showing up", "it's not loading" | default (errors section) then `--fix` |
| "why isn't it triggering", "which should I trim", "how much context" | `--lint` |
| "is this skill safe", "scan these", anything after a bulk install | `--audit` |
| "check my skills repo before I publish" | `--skills-dir <repo>/skills --lint --audit --strict` |

Flags combine. `--problems-only` drops the table when only findings matter; `--json`
when you need to process the result.

## Steps

1. Run it. For `--known`, pass the skill names from your own system context - the
   list the `Skill` tool accepts. That turns "compare by eye" into a diff: rows
   become **registered** or **NEW**, and names the harness lists but that no longer
   exist on disk are reported as stale.

2. Answer the question first, then summarize. If they asked about one skill, lead with
   that skill's line. Then, briefly:
   - **errors** - folders that will never register. Give the one-line fix each:
     add frontmatter, close it, add a `name`, move a nested folder up. If the script
     planned a fix, offer `--fix --apply`; show the dry run first so they can see the
     moves.
   - **warnings** - registers, but: no description (never auto-triggers), `name` not
     matching the folder, duplicate names across scopes, and under `--lint` the
     description-quality findings. These are why "it's installed but never fires".
   - **NEW** - on disk, not yet in your index. Usually it appears on the next turn.
     If they want it now, do step 3.
   - **audit** - `high` findings deserve a direct read of the file before the user
     runs that skill. `review` hits are phrases that are ordinary inside a security
     or prompt-testing skill (a jailbreak signature table will contain "ignore
     previous instructions"); read them in context and say what you found rather
     than just relaying the count. `info` is external hosts the skill references.

   Do not paste the whole table back when a few rows matter. Say the count, name
   the exceptions.

3. To use a NEW skill before the harness registers it, read its `SKILL.md` and follow
   it. That is all the `Skill` tool does: it puts the file body into context. Read
   any `scripts/` or `references/` it points to when the instructions call for them.
   Tell the user you loaded it manually so they know the slash form may lag.

4. If the user reports "/x isn't a command here" from the desktop app but you have
   `x` in your own listing, the app's slash-command picker is stale, not the harness.
   Tell them to send the request as a plain message; do not suggest `/clear` for this.

5. If a skill is on disk with no errors and still not registered after another turn,
   the watcher is probably not running. That is the case in `--bare` mode. `/clear`
   reruns discovery but wipes the conversation, so let them finish anything in
   flight. For a plugin, changes to `hooks/`, `agents/` or `.mcp.json` need
   `/reload-plugins`; SKILL.md text does not.

## Related, not overlapping

`/skill-doctor` (Claude Code 2.1.252+) reports what each skill *costs* and how often
it is *used*. It does not say why a skill failed to register. When the user's real
question is "which skills should I turn off", point them there; the context-cost line
here is a rough stand-in for when `/skill-doctor` is unavailable.

## What this cannot do

It cannot make the harness rescan; only the harness does that. It does not evaluate
whether a description *will* trigger for a given phrase - `--lint` catches the
structural reasons a description under-triggers (too short, no "use when", overlaps
with a sibling), not the semantic ones. And `--audit` is a pattern scan, not a
verdict: a clean audit means nothing obvious was found, not that the skill is safe.
